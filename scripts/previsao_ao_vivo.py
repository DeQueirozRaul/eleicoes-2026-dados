"""Previsão ao vivo na noite do 2º turno de 2026.

Roda junto com o coletor: a cada rodada, lê o retrato mais recente de cada
município salvo por scripts/coletar_ao_vivo.py, calcula a projeção e salva
uma linha em dados/ao_vivo/previsao_e{eleicao}.csv.

    # terminal 1
    python scripts/coletar_ao_vivo.py --eleicao 6258 --cargo 1 --intervalo 60
    # terminal 2
    python scripts/previsao_ao_vivo.py --eleicao 6258 --intervalo 60

Antes: scripts/montar_base.py (a previsão de antes da eleição vem do modelo de
2º turno treinado com 2002 a 2022).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.ao_vivo import Parametros, estado_do_coletor, projetar  # noqa: E402
from eleicoes.modelo_2t import ajustar, preparar, prever_municipios  # noqa: E402
from eleicoes.tse_ao_vivo import FUSO_BRASILIA  # noqa: E402

ANO = 2026


def preparar_prior() -> tuple[pd.DataFrame, Parametros, dict]:
    con = duckdb.connect(str(RAIZ / "dados" / "eleicoes.duckdb"), read_only=True)
    dados = preparar(con.sql("select * from transicao_turnos").df())
    finalistas = con.sql(f"select finalista, nr_candidato, nm_urna from finalistas where ano = {ANO}").df()
    con.close()
    modelo = ajustar(dados)
    df = dados[dados["ano"] == ANO].copy()
    E = float(df["E"].iloc[0])
    df["logit_prior"] = prever_municipios(modelo, df, modelo.k * E)
    df["taxa_validos"] = df["qt_validos_1t"] / df["qt_aptos"]
    parametros = Parametros(tau_nacional=modelo.tau * np.sqrt(1 + E ** 2 / modelo.soma_e2),
                            sigma_uf=modelo.sigma_uf, sigma_mun=modelo.sigma_mun, c_tamanho=modelo.c_tamanho)
    nomes = finalistas.set_index("finalista").to_dict("index")
    return df[["uf", "cd_municipio_tse", "logit_prior", "taxa_validos"]], parametros, nomes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--eleicao", type=int, default=6258)
    parser.add_argument("--cargo", type=int, default=1)
    parser.add_argument("--intervalo", type=int, default=0, help="segundos entre projeções (0 = só uma)")
    args = parser.parse_args()

    prior, parametros, nomes = preparar_prior()
    pasta = RAIZ / "dados" / "ao_vivo" / f"e{args.eleicao}_c{args.cargo}"
    saida = RAIZ / "dados" / "ao_vivo" / f"previsao_e{args.eleicao}.csv"
    a, b = nomes["A"], nomes["B"]

    while True:
        if any(pasta.glob("*/andamento.parquet")):
            estado = estado_do_coletor(pasta.as_posix(), int(a["nr_candidato"]), int(b["nr_candidato"]), prior)
            p = projetar(estado, parametros, cenarios=4000)
            agora = datetime.now(FUSO_BRASILIA)
            linha = pd.DataFrame([{"momento": agora.isoformat(timespec="seconds"), **vars(p)}])
            linha.to_csv(saida, mode="a", header=not saida.exists(), index=False)
            if not p.publicavel:
                print(f"{agora:%H:%M:%S} apurado {p.pct_secoes:6.2%} | aguardando 5% apurado para projetar")
            else:
                print(f"{agora:%H:%M:%S} apurado {p.pct_secoes:6.2%} | placar: {a['nm_urna']} {p.pct_a_apurado:.2%} | "
                      f"projeção: {a['nm_urna']} {p.pct_a_mediana:.2%} [{p.pct_a_inferior:.2%}, {p.pct_a_superior:.2%}] "
                      f"chance {p.prob_a_vence:.0%}; {b['nm_urna']} {1 - p.pct_a_mediana:.2%} chance {1 - p.prob_a_vence:.0%}")
        else:
            print(f"aguardando dados do coletor em {pasta}")
        if not args.intervalo:
            break
        time.sleep(args.intervalo)


if __name__ == "__main__":
    np.seterr(over="ignore")
    main()
