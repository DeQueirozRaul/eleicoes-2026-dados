"""Prepara o 2º turno de 2026 (25/10) para as páginas "Resultados e mapa" e "Mapa do DF".

Fontes:
- boletins de urna do 2º turno de 2026 e de 2022, Presidente (scripts/baixar_boletins.py --ano 2026 --turno 2
  e --turno 2): votos, eleitores e comparecimento de cada seção;
- votação por seção do DF em 2026 (Governador no 2º turno), baixada aqui:
  https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_2026_DF.zip
- resultado oficial do TSE (resultados.tse.jus.br) para conferir as somas;
- locais de votação e regiões administrativas do DF, como em scripts/site_df.py.

Grava em app/dados/:
- resultados_2t.parquet: uma linha por município (e cidade do exterior), com o 2º turno de 2026, o 1º turno
  de 2026 e o 2º turno de 2022;
- acrescenta as disputas pres_2026_2t e gov_2026_2t a df_disputas, df_regioes e df_locais.

    python scripts/site_2t.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import site_df  # noqa: E402
from eleicoes.tse_ao_vivo import ClienteTSE  # noqa: E402
from eleicoes.tse_arquivos import extrair_do_zip  # noqa: E402

BRUTOS = RAIZ / "dados" / "brutos"
DADOS_SITE = RAIZ / "app" / "dados"
PARTIDO = {22: "PL", 13: "PT"}          # os mesmos dois números nos 2º turnos de 2022 e 2026
NOMES_2026 = {22: "FLAVIO BOLSONARO", 13: "LULA"}


def votos_por_municipio(con, pasta: Path) -> pd.DataFrame:
    """Soma os boletins de urna de cada município (uma linha por seção e candidato no boletim)."""
    return con.sql(f"""
        with secao as (
            select SG_UF as uf, lpad(CD_MUNICIPIO, 5, '0') as cd_municipio_tse, NR_ZONA, NR_SECAO,
                   any_value(QT_APTOS::int) as qt_aptos, any_value(QT_COMPARECIMENTO::int) as qt_comparecimento,
                   coalesce(sum(QT_VOTOS::int) filter (where NR_VOTAVEL = '22'), 0) as votos_22,
                   coalesce(sum(QT_VOTOS::int) filter (where NR_VOTAVEL = '13'), 0) as votos_13,
                   coalesce(sum(QT_VOTOS::int) filter (where NR_VOTAVEL = '95'), 0) as qt_brancos,
                   coalesce(sum(QT_VOTOS::int) filter (where NR_VOTAVEL = '96'), 0) as qt_nulos
            from read_parquet('{pasta}/*.parquet')
            group by all
        )
        select uf, cd_municipio_tse, sum(qt_aptos) as qt_aptos, sum(qt_comparecimento) as qt_comparecimento,
               sum(votos_22) as votos_22, sum(votos_13) as votos_13,
               sum(qt_brancos) as qt_brancos, sum(qt_nulos) as qt_nulos
        from secao group by all
    """).df()


def lado(votos_22: pd.Series, votos_13: pd.Series) -> pd.Series:
    return pd.Series(["empate" if a == b else PARTIDO[22] if a > b else PARTIDO[13]
                      for a, b in zip(votos_22, votos_13)], index=votos_22.index)


def resultados_2t(con) -> pd.DataFrame:
    m = votos_por_municipio(con, BRUTOS / "bweb_2026_2t")
    m22 = votos_por_municipio(con, BRUTOS / "bweb_2022_2t")[["uf", "cd_municipio_tse", "votos_22", "votos_13"]]
    m = m.merge(m22.rename(columns={"votos_22": "votos_22_2022", "votos_13": "votos_13_2022"}),
                on=["uf", "cd_municipio_tse"], how="left")
    primeiro = pd.read_parquet(DADOS_SITE / "resultados_municipios.parquet")[
        ["uf", "cd_municipio_tse", "cd_municipio_ibge", "nm_municipio", "mais_votado", "pct_22", "pct_13"]]
    m = m.merge(primeiro.rename(columns={"mais_votado": "mais_votado_1t", "pct_22": "pct_22_1t",
                                         "pct_13": "pct_13_1t"}), on=["uf", "cd_municipio_tse"], how="left")
    m["qt_validos"] = m["votos_22"] + m["votos_13"]
    m["pct_22"] = m["votos_22"] / m["qt_validos"]
    m["pct_13"] = m["votos_13"] / m["qt_validos"]
    m["mais_votado"] = lado(m["votos_22"], m["votos_13"]).map(
        {PARTIDO[22]: NOMES_2026[22], PARTIDO[13]: NOMES_2026[13], "empate": "empate"})
    m["lado_2022"] = lado(m["votos_22_2022"].fillna(0), m["votos_13_2022"].fillna(0)).where(m["votos_22_2022"].notna())
    m["lado_2026"] = lado(m["votos_22"], m["votos_13"])
    m["transicao"] = [("sem resultado em 2022" if pd.isna(a) else f"{a} nas duas" if a == b
                       else f"{a} em 2022 → {b} em 2026") for a, b in zip(m["lado_2022"], m["lado_2026"])]
    # só onde se conhece o 1º turno (o exterior não está no arquivo do 1º turno por município)
    m["mudou_desde_o_1t"] = (m["mais_votado"] != m["mais_votado_1t"]) & m["mais_votado_1t"].notna()
    return m.sort_values(["uf", "cd_municipio_tse"]).reset_index(drop=True)


def conferir_brasil(m: pd.DataFrame) -> None:
    oficial = ClienteTSE().resultado(6258, 1, "br")
    numeros = oficial.candidatos.set_index(oficial.candidatos["nr_candidato"].astype(int))["qt_votos"]
    for nr in (22, 13):
        print(f"  {NOMES_2026[nr]}: soma dos municípios − oficial = {int(m[f'votos_{nr}'].sum()) - int(numeros[nr])}")


def df_2t() -> None:
    """Presidente e Governador no 2º turno, por região administrativa e local de votação do DF."""
    site_df.baixar()
    governador = site_df.BRUTOS / "governador_2026_2t.parquet"
    if not governador.exists():
        csv = site_df.BRUTOS / "votacao_secao_2026_DF.csv"
        extrair_do_zip(f"{site_df.CDN}/votacao_secao/votacao_secao_2026_DF.zip", "votacao_secao_2026_DF.csv", csv)
        duckdb.sql(f"""
            copy (select * from read_csv('{csv.as_posix()}', encoding = 'latin-1', delim = ';', all_varchar = true)
                  where CD_CARGO = '3' and NR_TURNO = '2')
            to '{governador.as_posix()}' (format parquet)
        """)
        csv.unlink()
    ras, geometrias = site_df.regioes_administrativas()
    secoes = {2026: site_df.locais(2026, ras, geometrias)}

    bweb = pd.read_parquet(BRUTOS / "bweb_2026_2t" / "DF.parquet")
    gov = pd.read_parquet(governador)
    votos = {
        "pres_2026_2t": pd.DataFrame({"zona": bweb["NR_ZONA"].astype(int), "secao": bweb["NR_SECAO"].astype(int),
                                      "nr": bweb["NR_VOTAVEL"].astype(int), "qt": bweb["QT_VOTOS"].astype(int)}),
        "gov_2026_2t": pd.DataFrame({"zona": gov["NR_ZONA"].astype(int), "secao": gov["NR_SECAO"].astype(int),
                                     "nr": gov["NR_VOTAVEL"].astype(int), "qt": gov["QT_VOTOS"].astype(int)}),
    }
    presenca = bweb.drop_duplicates(["NR_ZONA", "NR_SECAO"])
    presenca = {2026: pd.DataFrame({"zona": presenca["NR_ZONA"].astype(int), "secao": presenca["NR_SECAO"].astype(int),
                                    "qt_aptos": presenca["QT_APTOS"].astype(int),
                                    "qt_comparecimento": presenca["QT_COMPARECIMENTO"].astype(int)})}

    linhas = []
    cliente = ClienteTSE()
    for chave, titulo, eleicao, cargo in (("pres_2026_2t", "Presidente, 2º turno de 2026", 6258, 1),
                                          ("gov_2026_2t", "Governador, 2º turno de 2026", 6260, 3)):
        c = cliente.resultado(eleicao, cargo, "df").candidatos.sort_values("qt_votos", ascending=False)
        linhas.append({"disputa": chave, "titulo": titulo, "ano": 2026,
                       "nr_a": int(c.iloc[0]["nr_candidato"]), "nm_a": c.iloc[0]["nm_urna"],
                       "qt_a_oficial": int(c.iloc[0]["qt_votos"]),
                       "nr_b": int(c.iloc[1]["nr_candidato"]), "nm_b": c.iloc[1]["nm_urna"],
                       "qt_b_oficial": int(c.iloc[1]["qt_votos"]),
                       "qt_validos_oficial": int(c["qt_votos"].sum()),
                       "numeros_validos": [int(n) for n in c["nr_candidato"]]})
    novas = pd.DataFrame(linhas)
    locais_df, regioes = site_df.agregar(novas, votos, presenca, secoes, ras)

    # acrescenta (ou troca) as duas disputas nos arquivos do site
    for nome, tabela in (("df_disputas", novas.drop(columns="numeros_validos")), ("df_regioes", regioes),
                         ("df_locais", locais_df)):
        caminho = DADOS_SITE / f"{nome}.parquet"
        antes = pd.read_parquet(caminho)
        antes = antes[~antes["disputa"].isin(novas["disputa"])]
        juntas = pd.concat([antes, tabela], ignore_index=True)
        for coluna in ("zona", "nr_local"):
            if coluna in juntas:
                juntas[coluna] = juntas[coluna].astype("Int64")
        juntas.to_parquet(caminho, index=False)
        print(f"  {caminho.relative_to(RAIZ)}: {len(juntas)} linhas")


def main() -> int:
    con = duckdb.connect()
    m = resultados_2t(con)
    conferir_brasil(m)
    m.to_parquet(DADOS_SITE / "resultados_2t.parquet", index=False)
    print(f"resultados_2t: {len(m)} municípios; mudaram de lado desde o 1º turno: {int(m['mudou_desde_o_1t'].sum())}")
    print(m["transicao"].value_counts().to_string())
    df_2t()
    return 0


if __name__ == "__main__":
    sys.exit(main())
