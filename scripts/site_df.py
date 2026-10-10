"""Prepara a página "Mapa do DF": como votou cada região administrativa e cada
local de votação do Distrito Federal.

Fontes:
- Limites das 35 regiões administrativas (RAs): IPE-DF (antiga Codeplan), camada
  "Regiões Administrativas do Distrito Federal", domínio público, pelo WFS do
  catálogo https://catalogo.ipe.df.gov.br/layers/geonode:regioes_administrativas
- Locais de votação com latitude e longitude, por seção (TSE, eleitorado por local
  de votação 2022 e 2026):
  https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_locais_votacao/
- Votos por seção:
  - Presidente 2026: arquivo gerado por scripts/site_conferencia.py (votação por seção do TSE);
  - Governador 2026: https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_2026_DF.zip
  - Presidente 2022: boletins de urna baixados por scripts/baixar_boletins_2022.py.

Cada local de votação é ligado à RA pelo ponto (latitude e longitude) dentro do
polígono da RA. Grava em app/dados/: df_ras.json (polígonos simplificados),
df_regioes.parquet, df_locais.parquet e df_disputas.parquet.

    python scripts/site_df.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import requests
from shapely.geometry import MultiPolygon, Point, Polygon, mapping, shape
from shapely.geometry.polygon import orient
from shapely.strtree import STRtree

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.tse_arquivos import extrair_do_zip  # noqa: E402

BRUTOS = RAIZ / "dados" / "brutos" / "df"
DESTINO = RAIZ / "app" / "dados"
CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"
WFS_RAS = ("https://catalogo.ipe.df.gov.br/geoserver/ows?service=WFS&version=1.0.0&request=GetFeature"
           "&typeName=geonode:regioes_administrativas&outputFormat=application/json&srsName=EPSG:4326")


# --- downloads ---------------------------------------------------------------
def baixar() -> None:
    BRUTOS.mkdir(parents=True, exist_ok=True)
    ras = BRUTOS / "ras.json"
    if not ras.exists():
        resposta = requests.get(WFS_RAS, timeout=120)
        resposta.raise_for_status()
        ras.write_bytes(resposta.content)
    arquivos = [
        (f"{CDN}/eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip", "eleitorado_local_votacao_2026_DF.csv",
         "locais_2026.parquet", "SG_UF = 'DF' and NR_TURNO = '1'"),
        (f"{CDN}/eleitorado_locais_votacao/eleitorado_local_votacao_2022.zip", "eleitorado_local_votacao_2022.csv",
         "locais_2022.parquet", "SG_UF = 'DF' and NR_TURNO = '1'"),
        (f"{CDN}/votacao_secao/votacao_secao_2026_DF.zip", "votacao_secao_2026_DF.csv",
         "governador_2026.parquet", "CD_CARGO = '3'"),
    ]
    for url, membro, saida, filtro in arquivos:
        if (BRUTOS / saida).exists():
            continue
        csv = BRUTOS / membro
        if not csv.exists():
            print(f"  baixando {membro}", flush=True)
            extrair_do_zip(url, membro, csv)
        # guarda só as linhas do DF que interessam e apaga o CSV grande
        duckdb.sql(f"""
            copy (select * from read_csv('{csv.as_posix()}', encoding = 'latin-1', delim = ';', all_varchar = true)
                  where {filtro})
            to '{(BRUTOS / saida).as_posix()}' (format parquet)
        """)
        csv.unlink()


# --- regiões administrativas ----------------------------------------------------
def regioes_administrativas() -> tuple[list[dict], list]:
    dados = json.loads((BRUTOS / "ras.json").read_text(encoding="utf-8"))
    ras = [{"ra": f["properties"]["ra_nome"], "ra_codigo": f["properties"]["ra_codigo"],
            "geometria": shape(f["geometry"])} for f in dados["features"]]
    return ras, [r["geometria"] for r in ras]


def ra_de_cada_ponto(lat: pd.Series, lon: pd.Series, ras: list[dict], geometrias: list) -> list[str | None]:
    """RA que contém cada ponto; se o ponto cair fora de todas (coordenada imprecisa
    na divisa), fica a RA mais próxima, desde que a menos de ~2 km."""
    arvore = STRtree(geometrias)
    saida = []
    for y, x in zip(lat, lon):
        if pd.isna(y) or pd.isna(x):
            saida.append(None)
            continue
        ponto = Point(x, y)
        dentro = [i for i in arvore.query(ponto) if geometrias[i].contains(ponto)]
        if dentro:
            saida.append(ras[dentro[0]]["ra"])
            continue
        i = arvore.nearest(ponto)
        saida.append(ras[i]["ra"] if geometrias[i].distance(ponto) < 0.02 else None)
    return saida


def gravar_poligonos(ras: list[dict]) -> None:
    features = []
    for r in ras:
        simples = r["geometria"].simplify(0.0006, preserve_topology=True)
        # o mapa do Plotly (d3-geo) espera o anel externo no sentido horário; no
        # sentido contrário, o polígono vira "o globo inteiro menos a RA"
        partes = simples.geoms if isinstance(simples, MultiPolygon) else [simples]
        simples = MultiPolygon([orient(Polygon(q.exterior, q.interiors), sign=-1.0) for q in partes])
        geo = mapping(simples)
        geo = json.loads(json.dumps(geo), parse_float=lambda v: round(float(v), 4))
        features.append({"type": "Feature", "id": r["ra"], "geometry": geo,
                         "properties": {"ra": r["ra"], "ra_codigo": r["ra_codigo"]}})
    caminho = DESTINO / "df_ras.json"
    caminho.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False,
                                  separators=(",", ":")), encoding="utf-8")
    print(f"  {caminho.relative_to(RAIZ)}: {caminho.stat().st_size / 1024:.0f} KB")


# --- locais e votos ---------------------------------------------------------------
def locais(ano: int, ras: list[dict], geometrias: list) -> pd.DataFrame:
    """Uma linha por seção: zona, seção, local de votação, bairro, coordenadas e RA."""
    bruto = pd.read_parquet(BRUTOS / f"locais_{ano}.parquet")
    secoes = pd.DataFrame({
        "zona": bruto["NR_ZONA"].astype(int), "secao": bruto["NR_SECAO"].astype(int),
        "nr_local": bruto["NR_LOCAL_VOTACAO"].astype(int), "nm_local": bruto["NM_LOCAL_VOTACAO"].str.strip(),
        "bairro": bruto["NM_BAIRRO"].str.strip(),
        "lat": pd.to_numeric(bruto["NR_LATITUDE"].str.replace(",", "."), errors="coerce"),
        "lon": pd.to_numeric(bruto["NR_LONGITUDE"].str.replace(",", "."), errors="coerce"),
    }).drop_duplicates(["zona", "secao"])
    secoes.loc[(secoes["lat"] > -10) | (secoes["lat"] < -20), ["lat", "lon"]] = np.nan   # -1 = sem coordenada
    pontos = secoes.drop_duplicates(["zona", "nr_local"])[["zona", "nr_local", "lat", "lon"]].copy()
    pontos["ra"] = ra_de_cada_ponto(pontos["lat"], pontos["lon"], ras, geometrias)
    return secoes.merge(pontos[["zona", "nr_local", "ra"]], on=["zona", "nr_local"], how="left")


def votos_2026(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    """Votos por seção nas disputas de 2026 (colunas: zona, secao, nr, qt)."""
    pres = pd.read_parquet(RAIZ / "dados" / "brutos" / "conferencia" / "votos_secao_presidente_2026_1t.parquet")
    pres = pres[pres["uf"] == "DF"]
    gov = pd.read_parquet(BRUTOS / "governador_2026.parquet")
    return {
        "pres_2026_1t": pd.DataFrame({"zona": pres["zona"].astype(int), "secao": pres["secao"].astype(int),
                                      "nr": pres["nr_votavel"].astype(int), "qt": pres["qt_votos"].astype(int)}),
        "gov_2026_1t": pd.DataFrame({"zona": gov["NR_ZONA"].astype(int), "secao": gov["NR_SECAO"].astype(int),
                                     "nr": gov["NR_VOTAVEL"].astype(int), "qt": gov["QT_VOTOS"].astype(int)}),
    }


def votos_2022() -> dict[str, pd.DataFrame]:
    saida = {}
    for turno in (1, 2):
        bweb = pd.read_parquet(RAIZ / "dados" / "brutos" / f"bweb_2022_{turno}t" / "DF.parquet")
        saida[f"pres_2022_{turno}t"] = pd.DataFrame({
            "zona": bweb["NR_ZONA"].astype(int), "secao": bweb["NR_SECAO"].astype(int),
            "nr": bweb["NR_VOTAVEL"].astype(int), "qt": bweb["QT_VOTOS"].astype(int)})
    return saida


def comparecimento(con: duckdb.DuckDBPyConnection) -> dict[int, pd.DataFrame]:
    """Aptos e comparecimento por seção (2026: detalhe por seção; 2022: boletins do 1º turno)."""
    det = pd.read_parquet(RAIZ / "dados" / "brutos" / "conferencia" / "detalhe_secao_presidente_2026_1t.parquet")
    det = det[det["uf"] == "DF"]
    bweb = pd.read_parquet(RAIZ / "dados" / "brutos" / "bweb_2022_1t" / "DF.parquet").drop_duplicates(
        ["NR_ZONA", "NR_SECAO"])
    return {
        2026: pd.DataFrame({"zona": det["zona"].astype(int), "secao": det["secao"].astype(int),
                            "qt_aptos": det["qt_aptos"].astype(int),
                            "qt_comparecimento": det["qt_comparecimento"].astype(int)}),
        2022: pd.DataFrame({"zona": bweb["NR_ZONA"].astype(int), "secao": bweb["NR_SECAO"].astype(int),
                            "qt_aptos": bweb["QT_APTOS"].astype(int),
                            "qt_comparecimento": bweb["QT_COMPARECIMENTO"].astype(int)}),
    }


def disputas(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Os dois mais votados no DF em cada disputa, e os números de todos os candidatos
    (para separar votos válidos de brancos, nulos e candidaturas anuladas)."""
    linhas = []
    for chave, titulo, ano, turno in [("pres_2026_1t", "Presidente, 1º turno de 2026", 2026, 1),
                                      ("pres_2022_1t", "Presidente, 1º turno de 2022", 2022, 1),
                                      ("pres_2022_2t", "Presidente, 2º turno de 2022", 2022, 2)]:
        c = con.sql(f"""select nr_candidato as nr, nm_urna, sum(qt_votos)::bigint as qt from votos_presidente
                        where ano = {ano} and turno = {turno} and uf = 'DF' group by all order by qt desc""").df()
        linhas.append((chave, titulo, ano, c))
    gov = pd.read_parquet(RAIZ / "dados" / "base" / "governador_uf.parquet").query("uf == 'DF' and ano == 2026")
    gov = gov.rename(columns={"nr_candidato": "nr", "qt_votos": "qt"}).sort_values("qt", ascending=False)
    linhas.append(("gov_2026_1t", "Governador, 1º turno de 2026", 2026, gov[["nr", "nm_urna", "qt"]]))
    return pd.DataFrame([{
        "disputa": chave, "titulo": titulo, "ano": ano,
        "nr_a": int(c.iloc[0]["nr"]), "nm_a": c.iloc[0]["nm_urna"], "qt_a_oficial": int(c.iloc[0]["qt"]),
        "nr_b": int(c.iloc[1]["nr"]), "nm_b": c.iloc[1]["nm_urna"], "qt_b_oficial": int(c.iloc[1]["qt"]),
        "qt_validos_oficial": int(c["qt"].sum()),
        "numeros_validos": [int(n) for n in c["nr"]],
    } for chave, titulo, ano, c in linhas])


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    print("Baixando o que falta", flush=True)
    baixar()
    ras, geometrias = regioes_administrativas()
    gravar_poligonos(ras)
    con = duckdb.connect(str(RAIZ / "dados" / "eleicoes.duckdb"), read_only=True)
    tabela_disputas = disputas(con)
    votos = {**votos_2026(con), **votos_2022()}
    presenca = comparecimento(con)
    con.close()

    secoes = {ano: locais(ano, ras, geometrias) for ano in (2022, 2026)}
    for ano, s in secoes.items():
        sem_ra = s["ra"].isna().mean()
        print(f"  locais {ano}: {len(s.drop_duplicates(['zona', 'nr_local']))} locais, {len(s)} seções, {sem_ra:.2%} das seções sem RA")

    por_local, por_ra = [], []
    for _, d in tabela_disputas.iterrows():
        v = votos[d["disputa"]]
        v = v[v["nr"].isin(d["numeros_validos"])]
        por_secao = v.pivot_table(index=["zona", "secao"], columns="nr", values="qt", aggfunc="sum", fill_value=0)
        resumo = pd.DataFrame({"qt_a": por_secao.get(d["nr_a"], 0), "qt_b": por_secao.get(d["nr_b"], 0),
                               "qt_validos": por_secao.sum(axis=1)}).reset_index()
        # conferência: a soma das seções tem de bater com o resultado oficial do DF
        for coluna, oficial in (("qt_a", "qt_a_oficial"), ("qt_b", "qt_b_oficial"), ("qt_validos", "qt_validos_oficial")):
            diferenca = int(resumo[coluna].sum()) - int(d[oficial])
            print(f"  {d['disputa']}: {coluna} seções − oficial = {diferenca}")
        resumo = resumo.merge(presenca[d["ano"]], on=["zona", "secao"], how="left")
        resumo = resumo.merge(secoes[d["ano"]], on=["zona", "secao"], how="left")
        resumo["disputa"] = d["disputa"]
        soma = ["qt_a", "qt_b", "qt_validos", "qt_aptos", "qt_comparecimento"]
        por_local.append(resumo.groupby(["disputa", "zona", "nr_local", "nm_local", "bairro", "ra"], dropna=False)
                         .agg(**{c: (c, "sum") for c in soma}, lat=("lat", "first"), lon=("lon", "first"))
                         .reset_index())
        por_ra.append(resumo.groupby(["disputa", "ra"], dropna=False)[soma].sum().reset_index())

    locais_df = pd.concat(por_local, ignore_index=True)
    locais_df[["zona", "nr_local"]] = locais_df[["zona", "nr_local"]].astype("Int64")
    regioes = pd.concat(por_ra, ignore_index=True)
    regioes["ra"] = regioes["ra"].fillna("Sem localização")
    codigos = {r["ra"]: r["ra_codigo"] for r in ras}
    regioes["ra_codigo"] = regioes["ra"].map(codigos)

    tabela_disputas = tabela_disputas.drop(columns="numeros_validos")
    for nome, tabela in (("df_disputas", tabela_disputas), ("df_regioes", regioes), ("df_locais", locais_df)):
        caminho = DESTINO / f"{nome}.parquet"
        tabela.to_parquet(caminho, index=False)
        print(f"  {caminho.relative_to(RAIZ)}: {len(tabela)} linhas, {caminho.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
