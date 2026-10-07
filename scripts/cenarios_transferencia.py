"""Cenários de transferência dos votos dos eliminados para o 2º turno de 2026.

1. Estima de que lado do 2º turno de 2022 vieram os eleitores de cada candidato
   eliminado em 2026 (inferência ecológica; três formas de agrupar os municípios
   para ver o quanto a estimativa depende dessa escolha).
2. Monta a grade de cenários: "fidelidade" = parte dos eleitores dos eliminados
   que vota no finalista do lado em que votou em 2022; "troca" = parte que vota
   no outro; o resto não vota válido.
3. Testa o método nas eleições de 2006 a 2022 (cada uma com o 2º turno anterior).

Saídas em dados/modelo/. Antes, rode scripts/montar_base.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.transferencia import (  # noqa: E402
    PARAMETROS, ajustar_transferencia, cenario, fontes_por_municipio, montar_matrizes,
    origem_dos_eleitores, prever_transferencia, transicoes_por_regiao,
)

SAIDA = RAIZ / "dados" / "modelo"
FIDELIDADES = [0.5, 0.6, 0.7, 0.8, 0.9]
TROCAS = [0.05, 0.10, 0.20, 0.30]


def agrupar(X: pd.DataFrame, Y: pd.DataFrame, tipo: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Troca a coluna `regiao` pelo agrupamento desejado (Brasil, Região ou UF).
    UFs com menos de 40 municípios ficam com a sua região."""
    X, Y = X.copy(), Y.copy()
    if tipo == "Brasil":
        grupo = np.full(len(X), "Brasil")
    elif tipo == "UF":
        ufs = X.index.get_level_values("uf")
        tamanho = pd.Series(ufs).value_counts()
        grupo = np.where(tamanho.reindex(ufs).to_numpy() >= 40, ufs, X["regiao"].to_numpy())
    else:
        grupo = X["regiao"].to_numpy()
    X["regiao"] = Y["regiao"] = grupo
    return X, Y


def fontes(composicao, finalistas, regioes, segundo_turno, ano, tipo="Região"):
    X, Y = agrupar(*montar_matrizes(composicao, finalistas, regioes, ano, ano - 4), tipo)
    origem = origem_dos_eleitores(X, Y, transicoes_por_regiao(X, Y))
    f = fontes_por_municipio(origem)
    f = f.merge(segundo_turno[segundo_turno["ano"] == ano].drop(columns="ano"),
                on=["uf", "cd_municipio_tse"], how="left")
    return origem, f


def pct_a(f: pd.DataFrame, a: str, b: str) -> float:
    return float(f[a].sum() / (f[a].sum() + f[b].sum()))


def main() -> None:
    con = duckdb.connect(str(RAIZ / "dados" / "eleicoes.duckdb"), read_only=True)
    composicao = con.sql("select * from composicao_eleitorado").df()
    finalistas = con.sql("select * from finalistas").df()
    regioes = con.sql("select uf, cd_municipio_tse, regiao from municipios").df()
    segundo_turno = con.sql("select ano, uf, cd_municipio_tse, qt_a_2t as A2, qt_b_2t as B2 from transicao_turnos").df()
    nomes = con.sql("select nr_candidato::varchar as nr, any_value(nm_urna) as nm from votos_presidente "
                    "where ano = 2026 group by all").df().set_index("nr")["nm"].to_dict()
    con.close()
    SAIDA.mkdir(parents=True, exist_ok=True)
    nome_a, nome_b = finalistas[finalistas["ano"] == 2026].set_index("finalista")["nm_urna"][["A", "B"]]
    pd.set_option("display.width", 200)

    # 1 e 2: origem dos eleitores e cenários, nas três formas de agrupar
    origens, grades = [], []
    for tipo in ["Região", "Brasil", "UF"]:
        origem, f = fontes(composicao, finalistas, regioes, segundo_turno, 2026, tipo)
        elim = origem[~origem["categoria"].isin(["A", "B", "BRANCO_NULO", "ABSTENCAO"])]
        tab = elim.pivot_table(index="categoria", columns="origem", values="qt", aggfunc="sum")
        tab.loc["TOTAL DOS ELIMINADOS"] = tab.sum()
        tab = tab.div(tab.sum(axis=1), axis=0)
        tab.index = [nomes.get(i, i) for i in tab.index]
        origens.append(tab.assign(agrupamento=tipo))
        for q in FIDELIDADES:
            for s in TROCAS:
                if q + s <= 1:
                    grades.append({"agrupamento": tipo, "fidelidade": q, "troca": s,
                                   "pct_a": cenario(f, q, s)})
    origens = pd.concat(origens).rename(columns={"lado_A": f"lado de {nome_a} (2022: JAIR BOLSONARO)",
                                                 "lado_B": f"lado de {nome_b} (2022: LULA)"})
    origens.to_csv(SAIDA / "origem_eleitores_eliminados_2026.csv")
    grades = pd.DataFrame(grades)
    grades.to_csv(SAIDA / "cenarios_transferencia_2026.csv", index=False)

    print("De que lado do 2º turno de 2022 vieram os eleitores dos eliminados (%):")
    print((origens.drop(columns="agrupamento") * 100).round(1).assign(agrupamento=origens["agrupamento"]).to_string())
    principal = grades[grades["agrupamento"] == "Região"].pivot(index="fidelidade", columns="troca", values="pct_a")
    print(f"\nCenários 2026 (% de {nome_a}; {nome_b} = 100 - valor), agrupamento por região:")
    print((principal * 100).round(2).to_string())
    print(f"Faixa em todos os cenários e agrupamentos: {grades['pct_a'].min():.2%} a {grades['pct_a'].max():.2%}")

    # 3: teste nas eleições passadas
    base = {ano: fontes(composicao, finalistas, regioes, segundo_turno, ano)[1] for ano in [2006, 2010, 2014, 2018, 2022]}
    ajustes = {ano: ajustar_transferencia(f) for ano, f in base.items()}
    linhas = []
    for ano, f in base.items():
        outros = pd.DataFrame({a: p for a, p in ajustes.items() if a != ano}).T.mean().to_dict()
        real = pct_a(f, "A2", "B2")
        loo = pct_a(prever_transferencia(f, outros), "A2_prev", "B2_prev")
        mesmo = pct_a(prever_transferencia(f, ajustes[ano]), "A2_prev", "B2_prev")
        linhas.append({"ano": ano, **{k: round(v, 3) for k, v in ajustes[ano].items()},
                       "pct_a_real": real, "pct_a_previsto_outros_anos": loo,
                       "erro_pp": (loo - real) * 100, "pct_a_ajuste_mesmo_ano": mesmo})
    validacao = pd.DataFrame(linhas)
    validacao.to_csv(SAIDA / "validacao_transferencia.csv", index=False)
    print("\nTeste nas eleições passadas (parâmetros ajustados em cada uma e previsão com a média das outras):")
    print(validacao.round(4).to_string(index=False))
    print("Parâmetros:", PARAMETROS)


if __name__ == "__main__":
    main()
