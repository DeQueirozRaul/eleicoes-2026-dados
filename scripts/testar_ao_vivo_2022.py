"""Testa a previsão ao vivo reproduzindo as apurações de 2022.

Para cada turno, a apuração é reproduzida seção por seção (na hora em que cada
boletim chegou ao TSE) e, a cada 2 minutos, a previsão ao vivo é recalculada e
comparada com o resultado final.

- 2º turno: a previsão de antes da eleição vem do modelo de 2º turno treinado
  só com 2002 a 2018.
- 1º turno: o alvo é o placar entre LULA e JAIR BOLSONARO; a previsão de antes
  é o mapa do 2º turno de 2018 (mesmos lados), com incerteza nacional grande,
  já que esse mapa não diz nada sobre o nível nacional de 2022.

Antes: scripts/baixar_boletins_2022.py --turno 1/2 e scripts/reproduzir_apuracao_2022.py.

    python scripts/testar_ao_vivo_2022.py --turno 2
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.ao_vivo import Parametros, projetar  # noqa: E402
from eleicoes.modelo_2t import ajustar, logit, preparar, prever_municipios  # noqa: E402

SAIDA = RAIZ / "dados" / "apuracao"
INICIO = {1: "2022-10-02 17:02", 2: "2022-10-30 17:02"}
CHAVE = ["uf", "cd_municipio_tse"]


def priors(con, turno: int) -> tuple[pd.DataFrame, Parametros]:
    """Previsão de antes da eleição para cada município (sem usar 2022)."""
    dados = preparar(con.sql("select * from transicao_turnos").df())
    modelo = ajustar(dados[dados["ano"] < 2022])
    base = Parametros(sigma_uf=modelo.sigma_uf, sigma_mun=modelo.sigma_mun, c_tamanho=modelo.c_tamanho)
    if turno == 2:
        df = dados[dados["ano"] == 2022].copy()
        E = float(df["E"].iloc[0])
        df["logit_prior"] = prever_municipios(modelo, df, modelo.k * E)
        df["taxa_validos"] = df["qt_validos_1t"] / df["qt_aptos"]
        return df[CHAVE + ["logit_prior", "taxa_validos"]], replace(
            base, tau_nacional=modelo.tau * np.sqrt(1 + E ** 2 / modelo.soma_e2))
    # 1º turno: A (LULA, PT) corresponde ao lado do PT em 2018, que era o B de 2018
    df = con.sql("""
        select uf, cd_municipio_tse,
               qt_b_2t / (qt_a_2t + qt_b_2t) as pct_lado_pt,
               (qt_a_2t + qt_b_2t) / qt_aptos as taxa_validos
        from transicao_turnos where ano = 2018 and qt_a_2t + qt_b_2t > 0
    """).df()
    df["logit_prior"] = logit(df["pct_lado_pt"])
    return df[CHAVE + ["logit_prior", "taxa_validos"]], replace(base, tau_nacional=0.5)


def reproduzir(secoes: pd.DataFrame, prior: pd.DataFrame, parametros: Parametros, inicio: str,
               cenarios: int = 1500) -> pd.DataFrame:
    final = secoes["qt_a"].sum() / (secoes["qt_a"].sum() + secoes["qt_b"].sum())
    municipios = secoes.groupby(CHAVE, as_index=False)["qt_aptos"].sum().merge(prior, on=CHAVE, how="left")
    sem_prior = municipios["logit_prior"].isna()
    municipios.loc[sem_prior, "logit_prior"] = 0.0
    municipios.loc[sem_prior, "taxa_validos"] = municipios["taxa_validos"].median()

    linhas = []
    for momento in pd.date_range(inicio, periods=105, freq="2min"):
        apurado = (secoes[secoes["dt_totalizacao"] <= momento].groupby(CHAVE, as_index=False)
                   .agg(qt_aptos_apurados=("qt_aptos", "sum"), qt_a=("qt_a", "sum"), qt_b=("qt_b", "sum")))
        estado = municipios.merge(apurado, on=CHAVE, how="left").fillna(
            {"qt_aptos_apurados": 0, "qt_a": 0, "qt_b": 0})
        linhas.append({"momento": momento, **vars(projetar(estado, parametros, cenarios=cenarios, semente=1))})
    r = pd.DataFrame(linhas).assign(pct_a_final=final)
    r["erro_projecao_pp"] = (r["pct_a_mediana"] - final) * 100
    r["erro_placar_pp"] = (r["pct_a_apurado"] - final) * 100
    r["final_no_intervalo"] = r["pct_a_inferior"].le(final) & r["pct_a_superior"].ge(final)
    return r


def resumo(r: pd.DataFrame) -> dict:
    depois = r[r["pct_secoes"] >= 0.02]
    marcos = {}
    for alvo in (0.05, 0.10, 0.25, 0.50, 0.75):
        linha = r.iloc[(r["pct_secoes"] - alvo).abs().argmin()]
        marcos[f"erro_{int(alvo * 100)}pct"] = round(float(linha["erro_projecao_pp"]), 2)
        marcos[f"placar_{int(alvo * 100)}pct"] = round(float(linha["erro_placar_pp"]), 2)
    perto = r[(r["erro_projecao_pp"].abs() < 0.5) & (r["pct_secoes"] >= 0.02)]
    return {
        "cobertura_90": round(float(depois["final_no_intervalo"].mean()), 2),
        **marcos,
        "menos_de_0_5pt_desde": f"{perto.iloc[0]['pct_secoes']:.1%}" if len(perto) else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--turno", type=int, choices=[1, 2], default=2)
    parser.add_argument("--sigma-restante-nacional", type=float)
    parser.add_argument("--sigma-restante-uf", type=float)
    args = parser.parse_args()

    con = duckdb.connect(str(RAIZ / "dados" / "eleicoes.duckdb"), read_only=True)
    secoes = con.sql(f"select * from secoes_2022 where turno = {args.turno} order by dt_totalizacao").df()
    prior, parametros = priors(con, args.turno)
    con.close()
    ajustes = {k: v for k, v in {"sigma_restante_nacional": args.sigma_restante_nacional,
                                 "sigma_restante_uf": args.sigma_restante_uf}.items() if v is not None}
    parametros = replace(parametros, **ajustes)

    r = reproduzir(secoes, prior, parametros, INICIO[args.turno])
    SAIDA.mkdir(parents=True, exist_ok=True)
    r.to_csv(SAIDA / f"teste_ao_vivo_2022_{args.turno}t.csv", index=False)
    print(f"Turno {args.turno} | resultado final de A: {r['pct_a_final'].iloc[0]:.4%} | {parametros}")
    print(r.iloc[::6].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(resumo(r))


if __name__ == "__main__":
    np.seterr(over="ignore")
    main()
