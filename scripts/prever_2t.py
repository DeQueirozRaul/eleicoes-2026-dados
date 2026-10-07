"""Valida o modelo de 2º turno nas eleições passadas e gera a previsão de 2026.

1. Validação "deixa uma de fora": para cada eleição de 2002 a 2022, treina com
   as outras cinco e prevê aquela, comparando com o resultado real.
2. Treina com as seis eleições e simula o 2º turno de 2026.
3. Testes de sensibilidade: o que muda com escolhas diferentes de modelo.

Saídas em dados/modelo/. Antes, rode scripts/montar_base.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.modelo_2t import ajustar, erro_municipal, logistica, preparar, simular  # noqa: E402

SAIDA = RAIZ / "dados" / "modelo"
ANO_ALVO = 2026


def validar(dados: pd.DataFrame, finalistas: pd.DataFrame, cenarios: int) -> pd.DataFrame:
    linhas = []
    for ano in sorted(dados.loc[dados["y"].notna(), "ano"].unique()):
        modelo = ajustar(dados[dados["ano"] != ano])
        df = dados[dados["ano"] == ano]
        r = simular(modelo, df, cenarios=cenarios).resumo()
        real = float(logistica(df["Y"].iloc[0]))
        nomes = finalistas[finalistas["ano"] == ano].set_index("finalista")["nm_urna"]
        linhas.append({
            "ano": int(ano), "finalista_a": nomes["A"], "finalista_b": nomes["B"],
            "pct_a_real": real, "pct_a_previsto": r["pct_a_mediana"],
            "pct_a_inferior": r["pct_a_inferior"], "pct_a_superior": r["pct_a_superior"],
            "prob_a_vence": r["prob_a_vence"],
            "erro_nacional_pp": (r["pct_a_mediana"] - real) * 100,
            "real_dentro_do_intervalo": r["pct_a_inferior"] <= real <= r["pct_a_superior"],
            "erro_municipal_pp": erro_municipal(modelo, df),
        })
    return pd.DataFrame(linhas)


def main() -> None:
    con = duckdb.connect(str(RAIZ / "dados" / "eleicoes.duckdb"), read_only=True)
    dados = preparar(con.sql("select * from transicao_turnos").df())
    finalistas = con.sql("select * from finalistas").df()
    municipios = con.sql("select uf, cd_municipio_tse, nm_municipio, regiao from municipios").df()
    con.close()
    SAIDA.mkdir(parents=True, exist_ok=True)

    validacao = validar(dados, finalistas, cenarios=5000)
    validacao.to_csv(SAIDA / "validacao_historica.csv", index=False)

    alvo = dados[dados["ano"] == ANO_ALVO]
    nomes = finalistas[finalistas["ano"] == ANO_ALVO].set_index("finalista")["nm_urna"]
    modelo = ajustar(dados)
    sim = simular(modelo, alvo, cenarios=20_000)

    sensibilidade = {
        "modelo principal": sim.resumo(),
        "sem a eleição de 2006 no treino": simular(ajustar(dados[dados["ano"] != 2006]), alvo, 10_000).resumo(),
        "mudança igual em todos os municípios": simular(ajustar(dados, termos=()), alvo, 10_000).resumo(),
    }

    por_municipio = sim.por_municipio.merge(municipios, on=["uf", "cd_municipio_tse"], how="left")
    por_municipio.to_parquet(SAIDA / f"previsao_{ANO_ALVO}_municipios.parquet", index=False)
    sim.por_uf.to_csv(SAIDA / f"previsao_{ANO_ALVO}_uf.csv", index=False)
    resultado = {
        "ano": ANO_ALVO,
        "finalista_a": nomes["A"], "finalista_b": nomes["B"],
        "previsao": sim.resumo(),
        "sensibilidade": sensibilidade,
        "modelo": modelo.resumo(),
    }
    (SAIDA / f"previsao_{ANO_ALVO}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")

    pd.set_option("display.width", 200)
    print("Validação (cada eleição prevista com o modelo treinado nas outras):")
    print(validacao.round(4).to_string(index=False))
    print(f"\nModelo treinado em {modelo.anos_treino}:")
    print(json.dumps(modelo.resumo(), indent=2))
    print(f"\nPrevisão {ANO_ALVO} ({nomes['A']} = A, {nomes['B']} = B):")
    for nome, r in sensibilidade.items():
        print(f"  {nome:38s} A: {r['pct_a_mediana']:.2%} "
              f"[{r['pct_a_inferior']:.2%}, {r['pct_a_superior']:.2%}]  P(A vence) = {r['prob_a_vence']:.0%}")


if __name__ == "__main__":
    np.seterr(over="ignore")
    main()
