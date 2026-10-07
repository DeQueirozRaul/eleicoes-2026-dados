"""Reproduz a apuração do 2º turno de 2022 seção por seção e confere com o
histórico oficial de totalização do TSE.

Cada seção entra na contagem no momento em que o boletim de urna chegou ao TSE
(DT_BU_RECEBIDO). Se a curva reproduzida bater com o histórico oficial, essa
reprodução serve para testar a previsão ao vivo "como se fosse aquela noite".

Antes: scripts/baixar_boletins_2022.py --turno 2 e scripts/montar_base.py.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import duckdb
import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
HISTORICO_URL = ("https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2022/"
                 "Historico_Totalizacao_Presidente_BR_2T_2022.zip")
HISTORICO = RAIZ / "dados" / "brutos" / "Historico_Totalizacao_Presidente_BR_2T_2022.csv"
SAIDA = RAIZ / "dados" / "apuracao"


def baixar_historico() -> None:
    if HISTORICO.exists():
        return
    conteudo = requests.get(HISTORICO_URL, timeout=120).content
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        nome = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        HISTORICO.write_bytes(zf.read(nome))


def curva_oficial(con) -> pd.DataFrame:
    return con.sql(f"""
        select strptime(trim(DT_TOTALIZACAO), '%d/%m/%Y %H:%M:%S') as momento,
               replace(trim(PE_SECOES_TOT_ACUMULADO), ',', '.')::double as pct_secoes,
               replace(trim(LULA_PE_VOTOS_TOT_ACUMULADO), ',', '.')::double as pct_a
        from read_csv('{HISTORICO}', delim = ';', encoding = 'latin-1', all_varchar = true)
        order by momento
    """).df()


def curva_reproduzida(con, momentos: pd.Series) -> pd.DataFrame:
    con.register("momentos", pd.DataFrame({"momento": momentos}))
    return con.sql("""
        with total as (select count(*) as secoes from secoes_2022 where turno = 2)
        select m.momento,
               count(s.secao) / any_value(total.secoes) as pct_secoes,
               sum(s.qt_a) / nullif(sum(s.qt_a + s.qt_b), 0) as pct_a
        from momentos m
        cross join total
        left join (select * from secoes_2022 where turno = 2) s on s.dt_totalizacao <= m.momento
        group by m.momento
        order by m.momento
    """).df()


def main() -> None:
    import os
    os.chdir(RAIZ)
    baixar_historico()
    SAIDA.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(RAIZ / "dados" / "eleicoes.duckdb"))
    for arquivo in sorted((RAIZ / "sql" / "apuracao").glob("*.sql")):
        con.execute(arquivo.read_text(encoding="utf-8"))

    oficial = curva_oficial(con)
    amostra = oficial[oficial["momento"].dt.second % 30 == 0].drop_duplicates("momento")
    reproduzida = curva_reproduzida(con, amostra["momento"])
    comparacao = amostra.merge(reproduzida, on="momento", suffixes=("_oficial", "_reproduzida"))
    comparacao.to_csv(SAIDA / "comparacao_curva_2022.csv", index=False)

    dif_secoes = (comparacao["pct_secoes_reproduzida"] - comparacao["pct_secoes_oficial"]).abs() * 100
    dif_a = (comparacao["pct_a_reproduzida"] - comparacao["pct_a_oficial"]).abs() * 100
    print(f"{len(comparacao)} momentos comparados")
    print(f"% de seções apuradas: diferença média {dif_secoes.mean():.2f} pt, máxima {dif_secoes.max():.2f} pt")
    print(f"% de LULA no placar:  diferença média {dif_a.mean():.3f} pt, máxima {dif_a.max():.3f} pt")
    marcos = comparacao.iloc[(comparacao["pct_secoes_oficial"].to_numpy()[:, None]
                              - [0.1, 0.25, 0.5, 0.75, 0.9, 0.99]).__abs__().argmin(axis=0)]
    print(marcos.to_string(index=False, float_format=lambda v: f"{v:.4f}"))


if __name__ == "__main__":
    sys.exit(main())
