"""Prepara os dados das páginas Início, Previsão do 2º turno, Apuração ao vivo e
Votos no número errado do site.

Não baixa nada: lê o que as outras etapas já calcularam (dados/eleicoes.duckdb,
dados/modelo/, dados/apuracao/ e dados/nulos/) e grava arquivos pequenos em
app/dados/, que vão para o git e são lidos pelo site.

    python scripts/site_base.py
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "dados"
DESTINO = RAIZ / "app" / "dados"


def gravar(tabela: pd.DataFrame, nome: str) -> None:
    caminho = DESTINO / f"{nome}.parquet"
    tabela.to_parquet(caminho, index=False)
    print(f"  {caminho.relative_to(RAIZ)}: {len(tabela)} linhas, {caminho.stat().st_size / 1024:.0f} KB")


def resumo_1t_2026(con: duckdb.DuckDBPyConnection) -> None:
    candidatos = con.sql("""
        select nm_urna, sg_partido, nr_candidato, sum(qt_votos)::bigint as qt_votos
        from votos_presidente where ano = 2026 and turno = 1
        group by all order by nm_urna
    """).df()
    candidatos["pct_validos"] = candidatos["qt_votos"] / candidatos["qt_votos"].sum()
    gravar(candidatos, "inicio_presidente_1t_2026")

    comparecimento = con.sql("""
        select ano, turno, sum(qt_aptos)::bigint as qt_aptos, sum(qt_comparecimento)::bigint as qt_comparecimento,
               sum(qt_abstencoes)::bigint as qt_abstencoes, sum(qt_brancos)::bigint as qt_brancos,
               sum(qt_nulos)::bigint as qt_nulos, sum(qt_validos)::bigint as qt_validos
        from comparecimento_presidente where ano = 2026 and turno = 1 group by all
    """).df()
    gravar(comparecimento, "inicio_comparecimento_1t_2026")


def previsao() -> None:
    modelo = DADOS / "modelo"
    resumo = json.loads((modelo / "previsao_2026.json").read_text(encoding="utf-8"))
    variantes = pd.DataFrame([{"variante": nome, **valores} for nome, valores in resumo["sensibilidade"].items()])
    variantes.insert(0, "finalista_a", resumo["finalista_a"])
    variantes.insert(1, "finalista_b", resumo["finalista_b"])
    gravar(variantes, "previsao_nacional")

    gravar(pd.read_csv(modelo / "previsao_2026_uf.csv"), "previsao_uf")
    gravar(pd.read_csv(modelo / "validacao_historica.csv"), "previsao_validacao")
    gravar(pd.read_csv(modelo / "cenarios_transferencia_2026.csv"), "previsao_cenarios")
    gravar(pd.read_csv(modelo / "validacao_transferencia.csv"), "previsao_validacao_transferencia")
    origem = pd.read_csv(modelo / "origem_eleitores_eliminados_2026.csv").rename(columns={"Unnamed: 0": "candidato"})
    gravar(origem, "previsao_origem_eliminados")


def apuracao_2022() -> None:
    for turno in (1, 2):
        teste = pd.read_csv(DADOS / "apuracao" / f"teste_ao_vivo_2022_{turno}t.csv", parse_dates=["momento"])
        gravar(teste, f"apuracao_2022_{turno}t")


def nulos() -> None:
    disputas = pd.read_csv(DADOS / "nulos" / "disputas_governador.csv")
    gravar(disputas, "nulos_todas_disputas")
    apertadas = pd.read_csv(DADOS / "nulos" / "nulos_disputas_apertadas.csv")
    apertadas = apertadas.merge(disputas[["ano", "turno", "uf", "votos_validos", "mais_votado", "pct_mais_votado",
                                          "pct_para_mudar"]], on=["ano", "turno", "uf"])
    # total de votos para Governador em cada disputa, contado no RDV (para a % de anulados)
    totais = []
    for _, d in apertadas.iterrows():
        rdv = pd.read_parquet(DADOS / "nulos" / "rdv" / f"{d['ano']}_{d['turno']}t_{d['uf']}.parquet")
        totais.append(int(rdv.loc[rdv["cargo"] == 3, "qt"].sum()))
    apertadas["votos_governador_rdv"] = totais
    gravar(apertadas, "nulos_disputas_apertadas")


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DADOS / "eleicoes.duckdb"), read_only=True)
    print("Início")
    resumo_1t_2026(con)
    con.close()
    print("Previsão do 2º turno")
    previsao()
    # estas duas dependem das etapas do modo completo (rodar_tudo.py --completo);
    # sem elas, o site continua usando os arquivos que já estão em app/dados/
    print("Apuração de 2022")
    if (DADOS / "apuracao" / "teste_ao_vivo_2022_2t.csv").exists():
        apuracao_2022()
    else:
        print("  pulado: rode antes scripts/testar_ao_vivo_2022.py (modo completo)")
    print("Votos no número errado")
    if (DADOS / "nulos" / "nulos_disputas_apertadas.csv").exists():
        nulos()
    else:
        print("  pulado: rode antes scripts/nulos_disputas_apertadas.py (modo completo)")


if __name__ == "__main__":
    main()
