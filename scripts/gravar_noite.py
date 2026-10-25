"""Grava a noite do 2º turno: roda o mesmo acompanhamento do site (coleta e projeção)
a cada minuto e guarda cada rodada, para comparar depois a projeção com o
resultado final.

    python scripts/gravar_noite.py                          # 25/10/2026, até a apuração terminar
    python scripts/gravar_noite.py --eleicao 6257 --governador 6259 --ate 2026-10-25T08:30:00-03:00
                                                            # teste com o 1º turno (já apurado)

Grava em dados/ao_vivo/:
    noite_e{eleicao}.csv              uma linha por rodada: seções apuradas, placar oficial,
                                      projeção (mais provável, margem de 90%) e chance
    noite_governador_e{governador}.csv  placar oficial de Governador nas UFs com 2º turno
    noite_e{eleicao}_municipios.parquet votos e eleitorado apurado por município (a cada 10
                                      rodadas e no fim)

Se o processo cair, rodar de novo continua acrescentando linhas (a primeira rodada
depois de voltar baixa de novo todos os municípios que já apuraram).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.acompanhamento import Acompanhamento  # noqa: E402
from eleicoes.ao_vivo import Parametros  # noqa: E402
from eleicoes.tse_ao_vivo import FUSO_BRASILIA, ClienteTSE  # noqa: E402

DADOS_SITE = RAIZ / "app" / "dados"
SAIDA = RAIZ / "dados" / "ao_vivo"


def acrescentar(tabela: pd.DataFrame, caminho: Path) -> None:
    tabela.to_csv(caminho, mode="a", header=not caminho.exists(), index=False)


def placar_governador(cliente: ClienteTSE, eleicao: int, ufs: list[str], momento: datetime) -> pd.DataFrame:
    linhas = []
    for uf in ufs:
        try:
            r = cliente.resultado(eleicao, 3, uf)
        except requests.RequestException as erro:
            print(f"   governador {uf}: {erro}", flush=True)
            continue
        if r is None:
            continue
        secoes = r.resumo["qt_secoes_totalizadas"] / r.resumo["qt_secoes"] if r.resumo["qt_secoes"] else 0.0
        for c in r.candidatos.itertuples():
            linhas.append({"momento": momento.isoformat(timespec="seconds"), "uf": uf.upper(),
                           "pct_secoes": secoes, "nr_candidato": c.nr_candidato, "nm_urna": c.nm_urna,
                           "sg_partido": c.sg_partido, "qt_votos": c.qt_votos,
                           "dt_geracao": r.resumo["dt_geracao"]})
    return pd.DataFrame(linhas)


def main() -> int:
    config = json.loads((DADOS_SITE / "ao_vivo_config.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--eleicao", type=int, default=config["eleicao"])
    parser.add_argument("--governador", type=int, default=config.get("eleicao_governador", 6260))
    parser.add_argument("--intervalo", type=int, default=60)
    parser.add_argument("--ate", default="2026-10-26T04:00:00-03:00", help="para sozinho nesse horário")
    args = parser.parse_args()
    ate = datetime.fromisoformat(args.ate)

    SAIDA.mkdir(parents=True, exist_ok=True)
    arquivo = SAIDA / f"noite_e{args.eleicao}.csv"
    arquivo_gov = SAIDA / f"noite_governador_e{args.governador}.csv"
    arquivo_mun = SAIDA / f"noite_e{args.eleicao}_municipios.parquet"
    a, b = config["finalistas"]["A"], config["finalistas"]["B"]
    acomp = Acompanhamento(
        eleicao=args.eleicao, cargo=config["cargo"], nr_a=a["nr_candidato"], nr_b=b["nr_candidato"],
        prior=pd.read_parquet(DADOS_SITE / "ao_vivo_prior.parquet"), parametros=Parametros(**config["parametros"]),
        intervalo=args.intervalo, cenarios=3000)
    cliente_gov = ClienteTSE()
    print(f"Gravando a eleição {args.eleicao} ({a['nm_urna']} × {b['nm_urna']}) em {arquivo}; até {ate:%d/%m %H:%M}",
          flush=True)

    rodadas = encerradas = 0
    while datetime.now(FUSO_BRASILIA) < ate:
        inicio = time.monotonic()
        momento = datetime.now(FUSO_BRASILIA)
        try:
            rodada = acomp.rodar_uma_vez()
        except Exception as erro:  # noqa: BLE001 - a gravação não pode parar
            print(f"{momento:%H:%M:%S} falha na rodada ({type(erro).__name__}: {erro})", flush=True)
            rodada = None
        if rodada is not None:
            rodadas += 1
            linha = vars(rodada).copy()
            linha["momento"] = rodada.momento.isoformat(timespec="seconds")
            linha["gravado_em"] = momento.isoformat(timespec="seconds")
            acrescentar(pd.DataFrame([linha]), arquivo)
            projecao = ("—" if rodada.pct_a_mediana is None or np.isnan(rodada.pct_a_mediana)
                        else f"{rodada.pct_a_mediana:.2%} [{rodada.pct_a_inferior:.2%}, {rodada.pct_a_superior:.2%}]")
            placar = "—" if rodada.pct_a_oficial is None else f"{rodada.pct_a_oficial:.2%}"
            print(f"{momento:%H:%M:%S} seções {rodada.pct_secoes:7.2%} | placar {a['nm_urna']} {placar} | "
                  f"projeção {projecao} | falhas {rodada.falhas} | {time.monotonic() - inicio:4.1f}s", flush=True)
            if rodadas % 10 == 0:
                acomp.estado().to_parquet(arquivo_mun, index=False)
            encerradas = encerradas + 1 if acomp.encerrado else 0
        elif not acomp.publicado:
            print(f"{momento:%H:%M:%S} o TSE ainda não publicou a eleição {args.eleicao}", flush=True)

        governador = placar_governador(cliente_gov, args.governador, config.get("ufs_governador_2t", ["df"]), momento)
        if not governador.empty:
            acrescentar(governador, arquivo_gov)

        if encerradas >= 3:
            print("Apuração encerrada (100% das seções e nada mudou em 3 rodadas).", flush=True)
            break
        time.sleep(max(5.0, args.intervalo - (time.monotonic() - inicio)))

    if acomp.municipios:
        acomp.estado().to_parquet(arquivo_mun, index=False)
    print(f"Fim: {rodadas} rodadas gravadas em {arquivo}", flush=True)
    return 0


if __name__ == "__main__":
    np.seterr(over="ignore")
    sys.exit(main())
