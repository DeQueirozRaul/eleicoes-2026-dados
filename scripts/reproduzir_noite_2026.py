"""A noite de 25/10/2026 reproduzida com os dados oficiais: o que a prorrogação mudou na projeção.

A projeção ao vivo errou no começo da noite (docs/previsao.md). Três perguntas, três testes:

1. **Coleta ou modelo?** O histórico de totalização do TSE diz, para cada zona, quando
   e quanto foi totalizado. Com ele, a projeção roda de novo como se a coleta tivesse
   sido perfeita (sem recusas do servidor nem arquivos atrasados). O erro que sobra é
   do modelo.
2. **A ordem de chegada atrapalhou?** O detalhe por seção traz a hora em que cada seção
   entrou na totalização nos dois turnos. Os votos do 2º turno são reproduzidos na
   ordem do 1º turno (uma noite normal, sem prorrogação) e comparados com a ordem real.
3. **Quantas urnas ficaram abertas depois das 17h e o comparecimento mudou?** Os boletins
   de urna trazem a hora em que cada urna foi encerrada (na hora local; convertida para
   Brasília pelo fuso do município).

Antes:
    python scripts/baixar_boletins.py --ano 2026 --turno 2
O histórico e o detalhe por seção são baixados aqui. Salva os arquivos noite_2026_*.parquet
do site e imprime os números de docs/previsao.md.

    python scripts/reproduzir_noite_2026.py
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.ao_vivo import MINIMO_APURADO, Parametros, projetar  # noqa: E402

BRUTOS = RAIZ / "dados" / "brutos"
HISTORICO = BRUTOS / "historico_2026_2t"
HISTORICO_URL = ("https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/historicototalizacao/"
                 "Historico_Totalizacao_Presidente_BR_2T_2026.zip")
DETALHE = BRUTOS / "secoes_2026_presidente.parquet"
DETALHE_URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_secao/detalhe_votacao_secao_2026.zip"
BOLETINS = BRUTOS / "bweb_2026_2t"
DADOS_SITE = RAIZ / "app" / "dados"
SAIDA = RAIZ / "dados" / "apuracao"

DIA_1T, DIA_2T = "2026-10-04", "2026-10-25"
RECOMECO = pd.Timestamp(f"{DIA_2T} 19:00")    # a divulgação voltou às 19h01
MARCOS = (0.05, 0.10, 0.25, 0.50, 0.75)
REGIAO = {**dict.fromkeys(["AC", "AM", "AP", "PA", "RO", "RR", "TO"], "Norte"),
          **dict.fromkeys(["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"], "Nordeste"),
          **dict.fromkeys(["DF", "GO", "MS", "MT"], "Centro-Oeste"),
          **dict.fromkeys(["ES", "MG", "RJ", "SP"], "Sudeste"),
          **dict.fromkeys(["PR", "RS", "SC"], "Sul"), "ZZ": "Exterior"}
# horas a somar à hora local para chegar à de Brasília; AM e PE têm municípios em dois fusos
FUSO = {"AC": 2, "AM": 1, "RR": 1, "RO": 1, "MT": 1, "MS": 1}


# --- dados ------------------------------------------------------------------------------
def baixar() -> None:
    if not any(HISTORICO.glob("*.csv")):
        HISTORICO.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(requests.get(HISTORICO_URL, timeout=600).content)) as zf:
            for nome in zf.namelist():
                if nome.lower().endswith(".csv"):
                    (HISTORICO / nome).write_bytes(zf.read(nome))
    if not DETALHE.exists():
        zip_tmp = BRUTOS / "detalhe_votacao_secao_2026.zip"
        with requests.get(DETALHE_URL, stream=True, timeout=1200) as r, open(zip_tmp, "wb") as f:
            r.raise_for_status()
            for bloco in r.iter_content(8 * 1024 * 1024):
                f.write(bloco)
        with zipfile.ZipFile(zip_tmp) as zf:
            csv = Path(zf.extract("detalhe_votacao_secao_2026_BR.csv", BRUTOS))
        zip_tmp.unlink()
        duckdb.sql(f"""
            copy (
                select NR_TURNO::int as turno, SG_UF as uf, lpad(CD_MUNICIPIO, 5, '0') as cd_municipio_tse,
                       NR_ZONA::int as zona, NR_SECAO::int as secao, QT_APTOS::int as qt_aptos,
                       QT_COMPARECIMENTO::int as qt_comparecimento, QT_VOTOS_NOMINAIS::int as qt_nominais,
                       strptime(DT_RECEBIMENTO_BU_HOR_TSE, '%d/%m/%Y %H:%M:%S') as recebido,
                       try_strptime(DT_PRIM_TOT_PARCIAL_HOR_TSE, '%d/%m/%Y %H:%M:%S') as totalizado
                from read_csv('{csv}', delim = ';', encoding = 'latin-1', all_varchar = true)
                where CD_CARGO = '1'
            ) to '{DETALHE}' (format parquet)
        """)
        csv.unlink()


def carregar(con, nr_a: int, nr_b: int) -> None:
    """eventos: o acumulado de cada zona depois de cada totalização (histórico do TSE);
    zonas: o tamanho de cada uma; secoes: votos do 2º turno, horários e comparecimento por seção."""
    con.execute(f"""
        create or replace view historico as
        select * from read_csv('{HISTORICO}/*.csv', delim = ';', encoding = 'latin-1', all_varchar = true)
    """)
    con.execute(f"""
        create or replace table eventos as
        select SG_UF as uf, lpad(CD_MUNICIPIO, 5, '0') as cd_municipio_tse, NR_ZONA::int as zona,
               strptime(DT_TOTALIZACAO, '%d/%m/%Y %H:%M:%S') as momento,
               max(QT_SECOES_TOT_ACUMULADO::int) as secoes, max(QT_APTOS_TOT_ACUMULADO::int) as aptos,
               coalesce(max(QT_VOTOS_TOTAL_ACUMULADO::int) filter (where NR_VOTAVEL = '{nr_a}'), 0) as qt_a,
               coalesce(max(QT_VOTOS_TOTAL_ACUMULADO::int) filter (where NR_VOTAVEL = '{nr_b}'), 0) as qt_b
        from historico
        group by all
    """)
    con.execute("""
        create or replace table zonas as
        select distinct SG_UF as uf, lpad(CD_MUNICIPIO, 5, '0') as cd_municipio_tse, NR_ZONA::int as zona,
               QT_SECOES_ZONA::int as qt_secoes, QT_APTOS_ZONA::int as qt_aptos
        from historico
    """)
    con.execute(f"""
        create or replace table secoes as
        with bu as (
            select SG_UF as uf, lpad(CD_MUNICIPIO, 5, '0') as cd_municipio_tse, NR_ZONA::int as zona,
                   NR_SECAO::int as secao, any_value(QT_APTOS::int) as qt_aptos,
                   coalesce(sum(QT_VOTOS::int) filter (where NR_VOTAVEL = '{nr_a}'), 0) as qt_a,
                   coalesce(sum(QT_VOTOS::int) filter (where NR_VOTAVEL = '{nr_b}'), 0) as qt_b,
                   min(DT_ENCERRAMENTO::timestamp) as encerramento_local
            from read_parquet('{BOLETINS}/*.parquet')
            group by all
        ),
        t1 as (select * from read_parquet('{DETALHE}') where turno = 1),
        t2 as (select * from read_parquet('{DETALHE}') where turno = 2)
        select bu.*, t1.totalizado as totalizado_1t, t2.totalizado as totalizado_2t,
               t1.qt_aptos as qt_aptos_1t, t1.qt_comparecimento as qt_comparecimento_1t,
               t2.qt_comparecimento as qt_comparecimento_2t
        from bu
        left join t1 using (uf, cd_municipio_tse, zona, secao)
        left join t2 using (uf, cd_municipio_tse, zona, secao)
    """)


# --- a projeção, momento a momento ------------------------------------------------------
def retratos_historico(con, momentos: list[pd.Timestamp]) -> pd.DataFrame:
    """O que o TSE tinha divulgado em cada município em cada momento (o último acumulado de cada zona)."""
    con.register("momentos", pd.DataFrame({"momento": momentos}))
    return con.sql("""
        with grade as (select m.momento, z.* from momentos m cross join zonas z)
        select g.momento, g.uf, g.cd_municipio_tse,
               sum(g.qt_secoes) as qt_secoes, sum(coalesce(e.secoes, 0)) as qt_secoes_apuradas,
               sum(g.qt_aptos) as qt_aptos, sum(coalesce(e.aptos, 0)) as qt_aptos_apurados,
               sum(coalesce(e.qt_a, 0)) as qt_a, sum(coalesce(e.qt_b, 0)) as qt_b
        from grade g
        asof left join eventos e
          on g.uf = e.uf and g.cd_municipio_tse = e.cd_municipio_tse and g.zona = e.zona and g.momento >= e.momento
        group by all
    """).df()


def retratos_secoes(con, tempo: str, momentos: list[pd.Timestamp]) -> pd.DataFrame:
    """O mesmo, montado seção por seção: cada seção entra no momento `tempo` (uma expressão SQL)."""
    con.register("momentos", pd.DataFrame({"momento": momentos}))
    return con.sql(f"""
        with s as (select *, {tempo} as entra from secoes),
        acumulado as (
            select uf, cd_municipio_tse, entra,
                   sum(count(*)) over w as secoes, sum(sum(qt_aptos)) over w as aptos,
                   sum(sum(qt_a)) over w as qt_a, sum(sum(qt_b)) over w as qt_b
            from s group by uf, cd_municipio_tse, entra
            window w as (partition by uf, cd_municipio_tse order by entra)
        ),
        municipios as (
            select uf, cd_municipio_tse, count(*) as qt_secoes, sum(qt_aptos) as qt_aptos from s group by all
        ),
        grade as (select m.momento, mu.* from momentos m cross join municipios mu)
        select g.momento, g.uf, g.cd_municipio_tse, g.qt_secoes, coalesce(a.secoes, 0) as qt_secoes_apuradas,
               g.qt_aptos, coalesce(a.aptos, 0) as qt_aptos_apurados,
               coalesce(a.qt_a, 0) as qt_a, coalesce(a.qt_b, 0) as qt_b
        from grade g
        asof left join acumulado a
          on g.uf = a.uf and g.cd_municipio_tse = a.cd_municipio_tse and g.momento >= a.entra
    """).df()


def projetar_noite(retratos: pd.DataFrame, prior: pd.DataFrame, parametros: Parametros, pct_final: float,
                   cenarios: int = 3000) -> pd.DataFrame:
    """Roda a projeção ao vivo em cada momento, com a mesma regra do site (publica a partir de 5%)."""
    linhas = []
    for momento, estado in retratos.groupby("momento"):
        estado = estado.merge(prior, on=["uf", "cd_municipio_tse"], how="left")
        estado["logit_prior"] = estado["logit_prior"].fillna(0.0)
        estado["taxa_validos"] = estado["taxa_validos"].fillna(estado["taxa_validos"].median())
        validos = estado["qt_a"].sum() + estado["qt_b"].sum()
        linha = {"momento": momento,
                 "pct_secoes": estado["qt_secoes_apuradas"].sum() / estado["qt_secoes"].sum(),
                 "pct_secoes_projecao": estado["qt_aptos_apurados"].sum() / estado["qt_aptos"].sum(),
                 "pct_a_apurado": estado["qt_a"].sum() / validos if validos else np.nan}
        if linha["pct_secoes_projecao"] >= MINIMO_APURADO:
            with np.errstate(over="ignore"):
                p = projetar(estado, parametros, cenarios=cenarios, semente=1)
            linha.update(pct_a_mediana=p.pct_a_mediana, pct_a_inferior=p.pct_a_inferior,
                         pct_a_superior=p.pct_a_superior, prob_a_vence=p.prob_a_vence)
        linhas.append(linha)
        if linha["pct_secoes"] >= 0.999:
            break
    r = pd.DataFrame(linhas)
    r = r[r["pct_a_apurado"].notna()].reset_index(drop=True)
    for coluna in ("pct_a_mediana", "pct_a_inferior", "pct_a_superior", "prob_a_vence"):
        if coluna not in r:
            r[coluna] = np.nan
    r["pct_a_final"] = pct_final
    r["erro_projecao_pp"] = (r["pct_a_mediana"] - pct_final) * 100
    r["erro_placar_pp"] = (r["pct_a_apurado"] - pct_final) * 100
    r["final_no_intervalo"] = (r["pct_a_inferior"].le(pct_final) & r["pct_a_superior"].ge(pct_final)).where(
        r["pct_a_mediana"].notna())
    return r


def erros_nos_marcos(versoes: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Erro do placar e da projeção quando cada versão da noite chegou a 5%, 10%, 25%, 50% e 75% das seções."""
    linhas = []
    for versao, r in versoes.items():
        pub = r[r["pct_a_mediana"].notna() & (r["pct_secoes"] <= 0.995)]
        for marco in MARCOS:
            linha = r[(r["pct_secoes"] >= marco) & r["pct_a_mediana"].notna()].iloc[0]
            linhas.append({"versao": versao, "marco": marco, "momento": linha["momento"],
                           "erro_placar_pp": linha["erro_placar_pp"], "erro_projecao_pp": linha["erro_projecao_pp"],
                           "final_no_intervalo": bool(linha["final_no_intervalo"]),
                           "cobertura": pub["final_no_intervalo"].astype(float).mean()})
    return pd.DataFrame(linhas)


# --- prorrogação, chegada e comparecimento ----------------------------------------------
def prorrogacao(con) -> pd.DataFrame:
    """Urnas por hora de encerramento (Brasília) e o comparecimento nos dois turnos."""
    secoes = con.sql("""
        select uf, cd_municipio_tse, qt_aptos, qt_aptos_1t, qt_comparecimento_1t, qt_comparecimento_2t,
               encerramento_local
        from secoes where uf <> 'ZZ' and encerramento_local is not null
    """).df()
    secoes["fuso"] = secoes["uf"].map(FUSO).fillna(0).astype(int)
    hora_local = secoes["encerramento_local"].dt.hour + secoes["encerramento_local"].dt.minute / 60
    mediana = hora_local.groupby([secoes["uf"], secoes["cd_municipio_tse"]]).transform("median")
    # AM: municípios do oeste ficam 2 h atrás de Brasília; PE: Fernando de Noronha, 1 h à frente
    secoes.loc[(secoes["uf"] == "AM") & (mediana < 15.5), "fuso"] = 2
    secoes.loc[(secoes["uf"] == "PE") & (mediana >= 17.5) & (mediana < 18.5), "fuso"] = -1
    brasilia = secoes["encerramento_local"] + pd.to_timedelta(secoes["fuso"], unit="h")
    minutos = (brasilia - pd.Timestamp(f"{DIA_2T} 17:00")).dt.total_seconds() / 60
    secoes["encerramento"] = pd.cut(minutos, [-np.inf, 30, 90, np.inf],
                                    labels=["até 17h30", "entre 17h30 e 18h30", "depois de 18h30"])
    g = secoes.groupby("encerramento", observed=False).agg(
        secoes=("qt_aptos", "size"), qt_aptos=("qt_aptos", "sum"), qt_aptos_1t=("qt_aptos_1t", "sum"),
        qt_comparecimento_1t=("qt_comparecimento_1t", "sum"), qt_comparecimento_2t=("qt_comparecimento_2t", "sum"))
    g["pct_secoes"] = g["secoes"] / g["secoes"].sum()
    g["comparecimento_1t"] = g["qt_comparecimento_1t"] / g["qt_aptos_1t"]
    g["comparecimento_2t"] = g["qt_comparecimento_2t"] / g["qt_aptos"]
    g["variacao_pp"] = (g["comparecimento_2t"] - g["comparecimento_1t"]) * 100
    return g.reset_index()


def chegada(con) -> pd.DataFrame:
    """Parte do eleitorado de cada região já totalizada quando o país chegou a 10% e a 25% das seções,
    nos dois turnos de 2026."""
    linhas = []
    for turno, coluna in ((1, "totalizado_1t"), (2, "totalizado_2t")):
        s = con.sql(f"select uf, qt_aptos, {coluna} as t from secoes where {coluna} is not null").df()
        s["regiao"] = s["uf"].map(REGIAO)
        s = s.sort_values("t")
        for marco in (0.10, 0.25):
            limite = s["t"].iloc[int(len(s) * marco)]
            ate = s[s["t"] <= limite]
            por_regiao = s.groupby("regiao")["qt_aptos"].sum()
            apurado = ate.groupby("regiao")["qt_aptos"].sum().reindex(por_regiao.index, fill_value=0)
            for regiao in por_regiao.index:
                linhas.append({"turno": turno, "marco": marco, "regiao": regiao,
                               "pct_regiao_apurada": apurado[regiao] / por_regiao[regiao],
                               "parte_do_apurado": apurado[regiao] / apurado.sum(),
                               "parte_do_eleitorado": por_regiao[regiao] / por_regiao.sum()})
    return pd.DataFrame(linhas)


def ritmo(con) -> pd.DataFrame:
    """Minutos entre o início da totalização e cada marco, nos dois turnos."""
    linhas = []
    for turno, coluna, inicio in ((1, "totalizado_1t", f"{DIA_1T} 17:00"), (2, "totalizado_2t", f"{DIA_2T} 19:00")):
        t = con.sql(f"select {coluna} as t from secoes where {coluna} is not null order by t").df()["t"]
        for marco in (0.10, 0.25, 0.50, 0.90, 0.99):
            momento = t.iloc[int(len(t) * marco)]
            linhas.append({"turno": turno, "marco": marco, "momento": momento,
                           "minutos": (momento - pd.Timestamp(inicio)).total_seconds() / 60})
    return pd.DataFrame(linhas)


def primeiras_secoes(con, prior: pd.DataFrame, momento: pd.Timestamp) -> pd.DataFrame:
    """Nos municípios que já tinham votos divulgados em `momento`: quanto o % de A nas seções já apuradas
    e no resultado final desses mesmos municípios ficou acima ou abaixo do previsto antes da eleição
    (pontos, ponderado pelos votos já apurados), por região."""
    e = retratos_historico(con, [momento]).merge(prior, on=["uf", "cd_municipio_tse"])
    fim = con.sql("select uf, cd_municipio_tse, sum(qt_a) as fa, sum(qt_b) as fb from secoes group by all").df()
    c = e[e["qt_a"] + e["qt_b"] > 0].merge(fim, on=["uf", "cd_municipio_tse"])
    previsto = 1 / (1 + np.exp(-c["logit_prior"]))
    c["dif_parcial"] = (c["qt_a"] / (c["qt_a"] + c["qt_b"]) - previsto) * 100
    c["dif_final"] = (c["fa"] / (c["fa"] + c["fb"]) - previsto) * 100
    c["votos"] = c["qt_a"] + c["qt_b"]
    c["regiao"] = c["uf"].map(REGIAO)
    linhas = []
    for regiao, d in [*c.groupby("regiao"), ("Brasil", c)]:
        linhas.append({"momento": momento, "regiao": regiao, "municipios": len(d), "votos": int(d["votos"].sum()),
                       "dif_parcial_pp": np.average(d["dif_parcial"], weights=d["votos"]),
                       "dif_final_pp": np.average(d["dif_final"], weights=d["votos"])})
    return pd.DataFrame(linhas)


def primeira_secao(con) -> pd.DataFrame:
    """Em cada município (com 5 seções ou mais), quanto o % de A na primeira seção totalizada ficou acima
    ou abaixo do resultado final do próprio município: na ordem real do 2º turno e na do 1º turno."""
    s = con.sql("""
        select uf, cd_municipio_tse, qt_aptos, qt_a, qt_b, totalizado_1t, totalizado_2t
        from secoes where uf <> 'ZZ' and totalizado_1t is not null and totalizado_2t is not null
    """).df()
    s["votos"] = s["qt_a"] + s["qt_b"]
    grupo = s.groupby(["uf", "cd_municipio_tse"])
    s["pct_municipio"] = grupo["qt_a"].transform("sum") / grupo["votos"].transform("sum")
    s["secoes"] = grupo["votos"].transform("size")
    linhas = []
    for nome, coluna in (("ordem do 2º turno (real)", "totalizado_2t"), ("ordem do 1º turno", "totalizado_1t")):
        primeira = s[(s.groupby(["uf", "cd_municipio_tse"])[coluna].rank(method="first") == 1) & (s["secoes"] >= 5)]
        primeira = primeira[primeira["votos"] > 0]
        linhas.append({"ordem": nome, "municipios": len(primeira),
                       "dif_pp": ((primeira["qt_a"] / primeira["votos"] - primeira["pct_municipio"]) * 100).mean()})
    return pd.DataFrame(linhas)


def vies_do_comparecimento(con, prior: pd.DataFrame) -> float:
    """Quanto a projeção erraria (em pontos), antes de qualquer voto, só por esperar o comparecimento do
    1º turno: cada município com o resultado final certo, mas pesado pelos votos válidos esperados."""
    m = con.sql("""
        select uf, cd_municipio_tse, sum(qt_aptos) as qt_aptos, sum(qt_a) as qt_a, sum(qt_b) as qt_b
        from secoes group by all
    """).df().merge(prior, on=["uf", "cd_municipio_tse"], how="inner")
    m = m[m["qt_a"] + m["qt_b"] > 0]
    pct = m["qt_a"] / (m["qt_a"] + m["qt_b"])
    esperado = m["qt_aptos"] * m["taxa_validos"]
    real = m["qt_a"] + m["qt_b"]
    return float(((pct * esperado).sum() / esperado.sum() - (pct * real).sum() / real.sum()) * 100)


# --- main --------------------------------------------------------------------------------
def main() -> int:
    config = json.loads((DADOS_SITE / "ao_vivo_config.json").read_text(encoding="utf-8"))
    a, b = config["finalistas"]["A"], config["finalistas"]["B"]
    prior = pd.read_parquet(DADOS_SITE / "ao_vivo_prior.parquet")
    parametros = Parametros(**config["parametros"])
    baixar()
    con = duckdb.connect()
    carregar(con, a["nr_candidato"], b["nr_candidato"])
    final = con.execute("select sum(qt_a), sum(qt_b) from secoes").fetchall()[0]
    pct_final = final[0] / (final[0] + final[1])
    print(f"Resultado final pelos boletins: {a['nm_urna']} {pct_final:.4%}")

    # 1. coleta perfeita (histórico oficial), minuto a minuto como a gravação da noite
    momentos = [pd.Timestamp(f"{DIA_2T} 17:06:30")] + list(pd.date_range(RECOMECO, f"{DIA_2T} 22:00", freq="1min"))
    perfeita = projetar_noite(retratos_historico(con, momentos), prior, parametros, pct_final)
    # 2. a mesma noite montada seção por seção (confere a montagem) e 3. na ordem do 1º turno
    momentos = list(pd.date_range(RECOMECO, f"{DIA_2T} 23:59", freq="2min"))
    por_secao = projetar_noite(retratos_secoes(con, "totalizado_2t", momentos), prior, parametros, pct_final)
    ordem_1t = projetar_noite(
        retratos_secoes(con, f"timestamp '{DIA_2T} 19:00' + (totalizado_1t - timestamp '{DIA_1T} 17:00')", momentos),
        prior, parametros, pct_final)
    ao_vivo = pd.read_parquet(DADOS_SITE / "noite_2026_2t.parquet")

    SAIDA.mkdir(parents=True, exist_ok=True)
    perfeita.to_parquet(DADOS_SITE / "noite_2026_reproduzida.parquet", index=False)
    ordem_1t.to_parquet(DADOS_SITE / "noite_2026_ordem_1t.parquet", index=False)
    por_secao.to_csv(SAIDA / "noite_2026_por_secao.csv", index=False)
    erros = erros_nos_marcos({"ao vivo (gravação)": ao_vivo, "coleta perfeita": perfeita,
                              "montada seção por seção": por_secao, "na ordem do 1º turno": ordem_1t})
    erros.to_parquet(DADOS_SITE / "noite_2026_erros.parquet", index=False)
    print("\nErro do placar e da projeção (pontos) quando cada versão chegou a cada % das seções:")
    print(erros.pivot_table(index="marco", columns="versao", values=["erro_placar_pp", "erro_projecao_pp"])
          .to_string(float_format=lambda v: f"{v:+.2f}"))
    print(erros.groupby("versao")["cobertura"].first().to_string(float_format=lambda v: f"{v:.0%}"))
    for nome, r in {"coleta perfeita": perfeita, "na ordem do 1º turno": ordem_1t}.items():
        pub = r[r["pct_a_mediana"].notna() & (r["pct_secoes"] <= 0.995)]
        fora = pub[~pub["final_no_intervalo"].astype(bool)]
        print(f"{nome}: publicada desde {pub['momento'].iloc[0]:%H:%M} ({pub['pct_secoes'].iloc[0]:.1%} das seções); "
              f"fora da margem em {len(fora)} de {len(pub)}"
              + (f", até {fora['momento'].max():%H:%M} ({fora['pct_secoes'].max():.1%})" if len(fora) else ""))

    primeiras = primeiras_secoes(con, prior, perfeita.loc[perfeita["pct_a_mediana"].notna(), "momento"].iloc[0])
    primeiras.to_parquet(DADOS_SITE / "noite_2026_primeiras_secoes.parquet", index=False)
    print(f"\nNa primeira projeção publicada ({primeiras['momento'].iloc[0]:%H:%M}), % de {a['nm_urna']} menos o "
          "previsto antes da eleição, nos municípios que já tinham votos (pontos):")
    print(primeiras.to_string(index=False, float_format=lambda v: f"{v:+.2f}"))

    ps = primeira_secao(con)
    ps.to_parquet(DADOS_SITE / "noite_2026_primeira_secao.parquet", index=False)
    print(f"\n% de {a['nm_urna']} na primeira seção de cada município menos o do município (pontos):")
    print(ps.to_string(index=False, float_format=lambda v: f"{v:+.2f}"))

    p = prorrogacao(con)
    p.to_parquet(DADOS_SITE / "noite_2026_prorrogacao.parquet", index=False)
    print("\nUrnas por hora de encerramento (Brasília):")
    print(p.to_string(float_format=lambda v: f"{v:.4f}"))

    c = chegada(con)
    c.to_parquet(DADOS_SITE / "noite_2026_chegada.parquet", index=False)
    print("\nParte do eleitorado de cada região já totalizada quando o país chegou a 10% e 25% das seções:")
    print(c.pivot_table(index="regiao", columns=["marco", "turno"], values="pct_regiao_apurada")
          .to_string(float_format=lambda v: f"{v:.1%}"))
    rt = ritmo(con)
    rt.to_parquet(DADOS_SITE / "noite_2026_ritmo.parquet", index=False)
    print("\nMinutos do início da totalização até cada marco:")
    print(rt.pivot_table(index="marco", columns="turno", values="minutos").to_string(float_format=lambda v: f"{v:.0f}"))

    total = con.execute("select sum(qt_aptos), sum(qt_comparecimento_1t), sum(qt_comparecimento_2t), "
                        "avg((totalizado_2t < timestamp '2026-10-25 19:00')::int) from secoes").fetchall()[0]
    resumo = pd.DataFrame([{"pct_final": pct_final, "comparecimento_1t": total[1] / total[0],
                            "comparecimento_2t": total[2] / total[0],
                            "secoes_antes_das_19h": total[3],
                            "vies_comparecimento_pp": vies_do_comparecimento(con, prior),
                            "municipios_primeira_projecao": int(primeiras.loc[primeiras["regiao"] == "Brasil",
                                                                                "municipios"].iloc[0])}])
    resumo.to_parquet(DADOS_SITE / "noite_2026_resumo.parquet", index=False)
    print("\n" + resumo.T.to_string(header=False, float_format=lambda v: f"{v:.4f}"))
    return 0


if __name__ == "__main__":
    np.seterr(over="ignore")
    sys.exit(main())
