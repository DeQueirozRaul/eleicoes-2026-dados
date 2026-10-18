"""Coleta os resultados ao vivo do TSE e salva um retrato (snapshot) a cada varredura.

Uma varredura:
  1. baixa o andamento de cada UF (28 arquivos pequenos);
  2. compara com a varredura anterior e só baixa o resultado por candidato
     dos municípios que mudaram (economiza milhares de downloads por minuto);
  3. salva tudo em Parquet, com a hora da coleta, para dar pra "reprisar" a
     apuração depois e para alimentar a previsão ao vivo.

Exemplos:
    # uma varredura só (ex.: baixar o 1º turno de 2026 já totalizado)
    python scripts/coletar_ao_vivo.py --eleicao 6257 --cargo 1

    # noite do 2º turno: varre a cada 60 s até a totalização terminar
    python scripts/coletar_ao_vivo.py --eleicao 6258 --cargo 1 --intervalo 60
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eleicoes.tse_ao_vivo import FUSO_BRASILIA, UFS, ClienteTSE  # noqa: E402

PASTA_PADRAO = Path(__file__).resolve().parents[1] / "dados" / "ao_vivo"


def varrer(cliente: ClienteTSE, eleicao: int, cargo: int, ufs: list[str],
           anterior: dict, paralelos: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Faz uma varredura e devolve (andamento, resumos, candidatos, estado).

    Uma UF ou um município que o TSE recusar nesta varredura (ex.: 403 passageiro)
    não derruba a coleta: fica como estava e é pedido de novo na próxima."""
    andamentos = [a for uf in ufs if (a := andamento_ou_nada(cliente, eleicao, uf)) is not None]
    if not andamentos:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), anterior
    andamento = pd.concat(andamentos, ignore_index=True)

    municipios = andamento[andamento["tp_abrangencia"] == "mun"]
    novos = {
        (m.uf, m.cd_abrangencia): (m.qt_secoes_totalizadas, m.dt_totalizacao)
        for m in municipios.itertuples()
    }
    mudaram = [
        chave for chave, valor in novos.items()
        if valor[0] > 0 and anterior.get(chave) != valor
    ]

    alvos = [("br", "")] + [(uf, "") for uf in ufs] + mudaram
    resumos, candidatos = cliente.resultados(eleicao, cargo, alvos, paralelos=paralelos)

    # só conta como "já baixado" o município cujo resultado chegou de fato
    baixados = set() if resumos.empty else set(zip(resumos["uf"], resumos["cd_municipio_tse"]))
    estado = {**anterior, **novos}
    for chave in mudaram:
        if chave not in baixados:
            if chave in anterior:
                estado[chave] = anterior[chave]
            else:
                del estado[chave]
    return andamento, resumos, candidatos, estado


def andamento_ou_nada(cliente: ClienteTSE, eleicao: int, uf: str) -> pd.DataFrame | None:
    try:
        return cliente.andamento(eleicao, uf)
    except requests.RequestException as erro:
        print(f"   {uf}: o TSE recusou o andamento ({erro}); tento de novo na próxima varredura")
        return None


def salvar(pasta: Path, momento: datetime, andamento: pd.DataFrame,
           resumos: pd.DataFrame, candidatos: pd.DataFrame) -> Path:
    destino = pasta / momento.strftime("%Y%m%dT%H%M%S")
    destino.mkdir(parents=True, exist_ok=True)
    carimbo = pd.Timestamp(momento)
    for nome, tabela in (("andamento", andamento), ("resumo", resumos), ("candidatos", candidatos)):
        if not tabela.empty:
            tabela.assign(dt_coleta=carimbo).to_parquet(destino / f"{nome}.parquet", index=False)
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ciclo", default="ele2026")
    parser.add_argument("--eleicao", type=int, default=6257, help="6257 = Presidente 1º turno 2026; 6258 = 2º turno")
    parser.add_argument("--cargo", type=int, default=1, help="1 = Presidente, 3 = Governador")
    parser.add_argument("--ufs", nargs="*", default=UFS)
    parser.add_argument("--intervalo", type=int, default=0, help="segundos entre varreduras (0 = só uma)")
    parser.add_argument("--paralelos", type=int, default=6)
    parser.add_argument("--saida", type=Path, default=PASTA_PADRAO)
    args = parser.parse_args()

    cliente = ClienteTSE(ciclo=args.ciclo)
    pasta = args.saida / f"e{args.eleicao}_c{args.cargo}"
    estado: dict = {}

    while True:
        inicio = time.monotonic()
        momento = datetime.now(FUSO_BRASILIA)
        try:
            andamento, resumos, candidatos, estado = varrer(
                cliente, args.eleicao, args.cargo, [uf.lower() for uf in args.ufs], estado, args.paralelos
            )
        except Exception as erro:  # noqa: BLE001 - na noite da eleição, o coletor não pode parar
            print(f"{momento:%H:%M:%S} falha na varredura ({type(erro).__name__}: {erro}); tento de novo")
            if not args.intervalo:
                raise
            time.sleep(args.intervalo)
            continue
        if andamento.empty:
            print(f"{momento:%H:%M:%S} nenhum dado publicado ainda para a eleição {args.eleicao}")
        else:
            destino = salvar(pasta, momento, andamento, resumos, candidatos)
            ufs = andamento[andamento["tp_abrangencia"] == "uf"]
            pct = ufs["qt_secoes_totalizadas"].sum() / max(ufs["qt_secoes"].sum(), 1)
            n_mun = resumos["cd_municipio_tse"].ne("").sum() if not resumos.empty else 0
            print(f"{momento:%H:%M:%S} {pct:6.2%} das seções totalizadas | "
                  f"{n_mun} municípios atualizados | {time.monotonic() - inicio:5.1f}s -> {destino}")
            if not args.intervalo or (pct >= 1 and not n_mun):
                break
        if not args.intervalo:
            break
        time.sleep(max(0, args.intervalo - (time.monotonic() - inicio)))


if __name__ == "__main__":
    main()
