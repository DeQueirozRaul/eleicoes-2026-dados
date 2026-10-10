"""Resultados e mapa: o 1º turno de 2026 município a município.

Seções: placar nacional; mapa de quem ficou à frente em cada município;
municípios que mudaram de lado desde 2022; brancos, nulos e abstenção;
quociente eleitoral (Deputado Federal); voto dividido Presidente × Governador.

Lê só arquivos pequenos de app/dados/ (resultados_*.parquet e
resultados_malha.json), gerados por scripts/site_resultados.py.
"""

from __future__ import annotations

import json
import unicodedata

import comum
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

UF_NOMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins", "ZZ": "Exterior",
}
FONTE_2026 = "TSE, resultados do 1º turno de 2026 (resultados.tse.jus.br)"
FONTE_MAPA = f"{FONTE_2026}; malha municipal do IBGE"
FONTE_HISTORICO = "TSE, Portal de Dados Abertos (2002 a 2022) e resultados de 2026 (resultados.tse.jus.br)"

# Tons claros das duas cores de identidade. Junto com as cores cheias, o
# conjunto de 4 cores passou na checagem de daltonismo (diferença entre todos os pares).
VIOLETA_CLARO = "#a99eea"
VERDE_AGUA_CLARO = "#86cdb0"
LIMITE_ESCALA = 60  # pontos: diferenças maiores ficam com a cor mais escura


# --- dados -------------------------------------------------------------------
placar = comum.ler("resultados_placar")
municipios = comum.ler("resultados_municipios")
_finalistas = placar.nsmallest(2, "posicao")
A, B = sorted(_finalistas["nm_urna"])  # ordem alfabética: A = VIOLETA, B = VERDE_AGUA
CORES = comum.cores_finalistas([A, B])
NUMERO = dict(zip(_finalistas["nm_urna"], _finalistas["nr_candidato"]))
PARTIDO = dict(zip(_finalistas["nm_urna"], _finalistas["sg_partido"]))


@st.cache_resource(show_spinner=False)
def malha() -> tuple[dict, dict]:
    """Geometria dos municípios ({código IBGE: feição}) e a caixa (lon/lat mín./máx.) de cada um."""
    geo = json.loads((comum.DADOS / "resultados_malha.json").read_text(encoding="utf-8"))
    feicoes, caixas = {}, {}
    for f in geo["features"]:
        g = f["geometry"]
        poligonos = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        xs = [x for p in poligonos for x, _ in p[0]]
        ys = [y for p in poligonos for _, y in p[0]]
        feicoes[f["id"]] = f
        caixas[f["id"]] = (min(xs), min(ys), max(xs), max(ys))
    return feicoes, caixas


def geojson_de(codigos) -> dict:
    feicoes, _ = malha()
    return {"type": "FeatureCollection", "features": [feicoes[c] for c in codigos]}


# --- pequenos auxiliares -------------------------------------------------------
def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def escolher_area(chave: str, rotulo: str = "Mostrar no mapa") -> str | None:
    """Seletor "Brasil / UF". Devolve None para o Brasil ou a sigla da UF."""
    ufs = sorted((uf for uf in UF_NOMES if uf != "ZZ"), key=lambda uf: sem_acento(UF_NOMES[uf]))
    opcoes = ["Brasil"] + [f"{UF_NOMES[uf]} ({uf})" for uf in ufs]
    escolha = st.selectbox(rotulo, opcoes, key=chave)
    return None if escolha == "Brasil" else escolha[-3:-1]


def na_area(uf: str | None) -> pd.DataFrame:
    return municipios if uf is None else municipios[municipios["uf"] == uf]


def nome_area(uf: str | None) -> str:
    return "Brasil" if uf is None else UF_NOMES[uf]


def quadrado(cor: str) -> str:
    """Quadradinho colorido para pôr ao lado de um nome (a cor marca, o texto fica na cor do texto)."""
    return f"<span style='color:{cor};font-size:1.1em'>■</span>"


def titulo(texto: str, como_ler: str | None = None) -> None:
    """Título do gráfico (o que ele mostra) e, se precisar, uma frase de como ler."""
    st.markdown(f"**{texto}**")
    if como_ler:
        st.caption(como_ler)


def figura_mapa(tracos: list, codigos, altura: int, legenda: bool = False, rodape: int = 8) -> go.Figure:
    """Mapa sem fundo (só os municípios), enquadrado nos `codigos` mostrados."""
    _, caixas = malha()
    lista = [caixas[c] for c in codigos]
    x0, y0 = min(c[0] for c in lista), min(c[1] for c in lista)
    x1, y1 = max(c[2] for c in lista), max(c[3] for c in lista)
    folga_x, folga_y = 0.02 * (x1 - x0), 0.02 * (y1 - y0)
    fig = go.Figure(tracos)
    comum.estilo(fig, altura=altura, legenda=legenda)
    fig.update_geos(visible=False, projection_type="mercator", bgcolor="rgba(0,0,0,0)",
                    lonaxis_range=[x0 - folga_x, x1 + folga_x], lataxis_range=[y0 - folga_y, y1 + folga_y])
    fig.update_layout(margin=dict(l=0, r=0, t=40 if legenda else 0, b=rodape), dragmode=False)
    return fig


def contorno(uf: str | None) -> dict:
    """Linha entre municípios: bem fina no Brasil inteiro, mais visível numa UF."""
    return dict(marker_line_color="white", marker_line_width=0.15 if uf is None else 0.6)


# --- textos formatados (guardados para não refazer a cada clique) --------------
@st.cache_data(show_spinner=False)
def tabela_resultado(uf: str | None) -> pd.DataFrame:
    d = na_area(uf)
    pa, pb = d[f"pct_{NUMERO[A]}"], d[f"pct_{NUMERO[B]}"]
    saida = pd.DataFrame({
        "Município": d["nm_municipio"],
        "UF": d["uf"],
        "Mais votado": d["mais_votado"].where(d["mais_votado"] != "empate", "empate: " + d["empatados"].fillna("")),
        f"{A} (% dos votos válidos)": pa.map(comum.pct),
        f"{B} (% dos votos válidos)": pb.map(comum.pct),
        f"Diferença entre {A} e {B}": (pa - pb).map(comum.pontos),
        "Votos válidos": d["qt_validos"].map(comum.numero),
    })
    return saida.sort_values(["UF", "Município"], key=lambda s: s.map(sem_acento))


@st.cache_data(show_spinner=False)
def textos_hover_resultado(uf: str | None) -> list[list[str]]:
    d = na_area(uf)
    linhas = []
    for r in d.itertuples():
        pa, pb = getattr(r, f"pct_{NUMERO[A]}"), getattr(r, f"pct_{NUMERO[B]}")
        # a mesma medida da cor do mapa: a diferença entre os dois mais votados do país
        if r.mais_votado == "empate":
            frase = f"Empate: {comum.numero(getattr(r, f'votos_{NUMERO[A]}'))} votos para cada um"
        elif r.mais_votado in (A, B):
            frase = f"{r.mais_votado} à frente por {comum.pontos(pa - pb)}"
        else:
            frase = f"Mais votado: {r.mais_votado} ({comum.pct(r.pct_mais_votado)})"
        if r.mais_votado != "empate" and r.segundo not in (A, B):
            frase += f"<br>2º lugar: {r.segundo} ({comum.pct(r.pct_segundo)})"
        linhas.append([r.nm_municipio, r.uf, comum.pct(pa), comum.pct(pb), frase])
    return linhas


# =============================================================================
comum.cabecalho(
    "Resultados e mapa",
    "O 1º turno de 4 de outubro de 2026, município a município, e o que mudou desde 2022.",
)
st.markdown(
    "Nesta página: [placar](#placar) · [mapa](#mapa) · [quem mudou de lado](#mudou-de-lado) · "
    "[brancos, nulos e abstenção](#brancos-nulos-e-abstencao) · [quociente eleitoral](#quociente-eleitoral) · "
    "[voto dividido](#voto-dividido)"
)

# --- 1. placar nacional ---------------------------------------------------------
st.header("Placar do 1º turno para Presidente", anchor="placar")
serie = comum.ler("resultados_comparecimento_serie")
total_2026 = serie[(serie["ano"] == 2026) & (serie["turno"] == 1)].iloc[0]
_por_nome = placar.set_index("nm_urna")
pct_a, pct_b = _por_nome.loc[A, "pct_validos"], _por_nome.loc[B, "pct_validos"]
st.markdown(
    f"Nenhum candidato passou de 50% dos votos válidos, então os dois mais votados disputam o 2º turno "
    f"em 25 de outubro: **{A}** ({PARTIDO[A]}), com **{comum.pct(pct_a)}** dos votos válidos, e "
    f"**{B}** ({PARTIDO[B]}), com **{comum.pct(pct_b)}**. A diferença entre os dois foi de "
    f"{comum.pontos(pct_a - pct_b)} ({comum.numero(abs(_por_nome.loc[A, 'qt_votos'] - _por_nome.loc[B, 'qt_votos']))} votos)."
)
c1, c2, c3, c4 = st.columns(4)
with c1:
    comum.cartao("Eleitores aptos a votar", comum.numero(total_2026["qt_aptos"]), "no Brasil e no exterior")
with c2:
    comum.cartao("Foram votar", comum.numero(total_2026["qt_comparecimento"]),
                 f"{comum.pct(total_2026['qt_comparecimento'] / total_2026['qt_aptos'])} do eleitorado")
with c3:
    comum.cartao("Votos válidos", comum.numero(total_2026["qt_validos"]), "dados a algum candidato")
with c4:
    comum.cartao("Brancos e nulos", comum.numero(total_2026["qt_brancos"] + total_2026["qt_nulos"]),
                 f"{comum.pct(total_2026['pct_brancos'] + total_2026['pct_nulos'])} de quem foi votar")

ordem = placar.sort_values("qt_votos")
# nome numa linha e partido e % na outra: cabe na tela do celular
# abaixo de 1%, duas casas decimais (senão os menores apareceriam como "0,0%")
rotulos = [f"{r.nm_urna}<br>{r.sg_partido} · {comum.pct(r.pct_validos, 1 if r.pct_validos >= 0.01 else 2)}"
           for r in ordem.itertuples()]
fig = go.Figure(go.Bar(
    x=100 * ordem["pct_validos"], y=rotulos, orientation="h", marker_color=comum.SERIE, width=0.55,
    customdata=[comum.numero(v) for v in ordem["qt_votos"]],
    hovertemplate="%{y}<br>%{customdata} votos<extra></extra>",
))
comum.estilo(fig, altura=50 + 40 * len(ordem), legenda=False)
fig.update_xaxes(showgrid=True, gridcolor=comum.GRADE, range=[0, 50], tickvals=[0, 20, 40],
                 ticktext=["0%", "20%", "40%"], tickangle=0)
fig.update_yaxes(showgrid=False, tickfont=dict(size=12))
titulo("Votos de cada candidato a Presidente, em % dos votos válidos",
       "Do mais votado (no alto) para o menos votado: é o resultado da eleição. Todos com a mesma cor. "
       "Inclui os votos do exterior.")
comum.mostrar(
    fig, chave="placar", fonte=FONTE_2026,
    tabela=pd.DataFrame({
        "Candidato": placar["nm_urna"], "Partido": placar["sg_partido"],
        "Votos": placar["qt_votos"].map(comum.numero),
        "% dos votos válidos": placar["pct_validos"].map(lambda v: comum.pct(v, 2)),
    }),
)

# --- 2. mapa ----------------------------------------------------------------------
st.header("Quem ficou à frente em cada município", anchor="mapa")
exterior = comum.ler("resultados_comparecimento_uf").set_index("uf").loc["ZZ"]
st.markdown(
    f"Cada município tem a cor de quem teve mais votos entre {quadrado(CORES[A])} **{A}** e "
    f"{quadrado(CORES[B])} **{B}**. Quanto mais escura a cor, maior a vantagem. A vantagem é medida em "
    "**pontos**: a diferença entre as duas porcentagens de votos válidos (ex.: 55% contra 40% = 15 pontos).",
    unsafe_allow_html=True,
)


@st.fragment
def secao_mapa() -> None:
    uf = escolher_area("area_mapa")
    d = na_area(uf)
    col_mapa, col_lado = st.columns([2.3, 1], gap="large")

    with col_lado:
        st.markdown(f"**{nome_area(uf)}**")
        if uf is None:
            pa, pb = pct_a, pct_b
            nota = "com o exterior"
        else:
            validos = d["qt_validos"].sum()
            pa, pb = d[f"votos_{NUMERO[A]}"].sum() / validos, d[f"votos_{NUMERO[B]}"].sum() / validos
            nota = "soma dos municípios"
        for nome, pct in ((A, pa), (B, pb)):
            n = int((d["mais_votado"] == nome).sum())
            comum.cartao(nome, comum.pct(pct), f"dos votos válidos; à frente em {comum.numero(n)} "
                         f"{'município' if n == 1 else 'municípios'}", cor=CORES[nome])
        empates = d[d["mais_votado"] == "empate"]
        outros = d[~d["mais_votado"].isin([A, B, "empate"])]
        extras = []
        if len(empates):
            extras.append(f"Empate exato em {len(empates)}: "
                          + ", ".join(f"{r.nm_municipio} ({r.uf})" for r in empates.itertuples()) + ".")
        if len(outros):
            extras.append(f"Outro candidato à frente em {len(outros)} (em cinza no mapa).")
        total = f"{comum.numero(len(d))} {'município' if len(d) == 1 else 'municípios'}"
        if uf == "DF":
            extras.append("O Distrito Federal é um município só; o resultado por região administrativa está "
                          "na página Mapa do DF.")
        st.caption(" ".join(extras + [f"% dos votos válidos: {nota}. Total: {total}."]))

    with col_mapa:
        dois = d[d["mais_votado"].isin([A, B, "empate"])]
        z = (100 * (dois[f"pct_{NUMERO[B]}"] - dois[f"pct_{NUMERO[A]}"])).round(1)
        hover = textos_hover_resultado(uf)
        posicao = {c: i for i, c in enumerate(d["cd_municipio_ibge"])}
        modelo = ("<b>%{customdata[0]} (%{customdata[1]})</b><br>"
                  f"{A}: %{{customdata[2]}}<br>{B}: %{{customdata[3]}}<br>%{{customdata[4]}}<extra></extra>")
        tracos = [go.Choropleth(
            geojson=geojson_de(dois["cd_municipio_ibge"]), locations=dois["cd_municipio_ibge"], z=z,
            zmin=-LIMITE_ESCALA, zmax=LIMITE_ESCALA, zmid=0, colorscale=comum.DIVERGENTE,
            customdata=[hover[posicao[c]] for c in dois["cd_municipio_ibge"]], hovertemplate=modelo,
            colorbar=dict(
                orientation="h", x=0.5, xanchor="center", y=0, yanchor="top", len=0.9, thickness=10,
                outlinewidth=0, tickvals=[-60, -40, -20, 0, 20, 40, 60],
                ticktext=["60 pontos", "40", "20", "0", "20", "40", "60 pontos"],
                tickfont=dict(color=comum.MUDO, size=11),
                title=dict(text=f"◀ {A} à frente  ·  {B} à frente ▶", side="top",
                           font=dict(color=comum.TINTA_2, size=12)),
            ),
            **contorno(uf),
        )]
        if len(outros):
            tracos.append(go.Choropleth(
                geojson=geojson_de(outros["cd_municipio_ibge"]), locations=outros["cd_municipio_ibge"],
                z=[0] * len(outros), colorscale=[[0, comum.APAGADO], [1, comum.APAGADO]], showscale=False,
                customdata=[hover[posicao[c]] for c in outros["cd_municipio_ibge"]], hovertemplate=modelo,
                **contorno(uf),
            ))
        fig = figura_mapa(tracos, d["cd_municipio_ibge"], altura=600 if uf is None else 520, rodape=78)
        titulo(f"Vantagem de quem ficou à frente, em pontos — {nome_area(uf)}",
               "Passe o mouse (ou toque) num município para ver os números. Diferenças acima de "
               f"{LIMITE_ESCALA} pontos têm a cor mais escura.")
        comum.mostrar(fig, tabela=tabela_resultado(uf), fonte=FONTE_MAPA, chave="mapa_resultado")
    st.caption(
        f"Os votos do exterior ({comum.numero(exterior['qt_validos'])} votos válidos) entram no total "
        "nacional, mas não aparecem no mapa."
    )


secao_mapa()

# --- 3. mudou de lado -----------------------------------------------------------
st.header("Municípios que mudaram de lado desde 2022", anchor="mudou-de-lado")
pa_, pb_ = PARTIDO[A], PARTIDO[B]
candidatos_2022 = (municipios.groupby("partido_2022")["mais_votado_2022"].first()
                   .drop("empate", errors="ignore").to_dict())
st.markdown(
    "Comparação do partido do candidato a Presidente mais votado em cada município no 1º turno de 2022 e "
    "no de 2026. Os candidatos desses partidos eram, em 2022, "
    f"{' e '.join(f'{c} ({p})' for p, c in sorted(candidatos_2022.items(), key=lambda kv: kv[1]))}; "
    f"em 2026, {A} ({pa_}) e {B} ({pb_})."
)
contagem = municipios["transicao"].value_counts()
de_a_para_b = int(contagem.get(f"{pa_} em 2022 → {pb_} em 2026", 0))
de_b_para_a = int(contagem.get(f"{pb_} em 2022 → {pa_} em 2026", 0))
m1, m2 = st.columns(2)
with m1:
    comum.cartao(f"Passaram do {pa_} para o {pb_}",
                 f"{comum.numero(de_a_para_b)} {'município' if de_a_para_b == 1 else 'municípios'}",
                 f"mais votado do {pa_} em 2022 e do {pb_} em 2026", cor=CORES[B])
with m2:
    comum.cartao(f"Passaram do {pb_} para o {pa_}",
                 f"{comum.numero(de_b_para_a)} {'município' if de_b_para_a == 1 else 'municípios'}",
                 f"mais votado do {pb_} em 2022 e do {pa_} em 2026", cor=CORES[A])

# categorias do mapa: (rótulo da transição, texto da legenda, cor)
CATEGORIAS = [
    (f"{pa_} nas duas", f"{pa_} nas duas eleições", VIOLETA_CLARO),
    (f"{pb_} em 2022 → {pa_} em 2026", f"Passou do {pb_} para o {pa_}", comum.VIOLETA),
    (f"{pb_} nas duas", f"{pb_} nas duas eleições", VERDE_AGUA_CLARO),
    (f"{pa_} em 2022 → {pb_} em 2026", f"Passou do {pa_} para o {pb_}", comum.VERDE_AGUA),
]
CONHECIDAS = {c[0] for c in CATEGORIAS}

# tabela das transições: as quatro combinações dos dois partidos sempre aparecem (mesmo com zero),
# em ordem alfabética; depois empates e o município novo
pares = (municipios.assign(antes=municipios["partido_2022"].fillna("município novo"))
         .groupby(["antes", "partido_mais_votado"]).size())
for antes in (pa_, pb_):
    for depois in (pa_, pb_):
        pares.loc[(antes, depois)] = pares.get((antes, depois), 0)
pares = pares.sort_index(key=lambda s: s.map(lambda p: (p not in (pa_, pb_), p)))
titulo("Partido do candidato a Presidente mais votado em cada município, em 2022 e em 2026")
st.dataframe(pd.DataFrame({
    "2022": pares.index.get_level_values(0),
    "2026": pares.index.get_level_values(1),
    "Mudou?": ["não" if a == b else "sim" if {a, b} <= {pa_, pb_} else "—" for a, b in pares.index],
    "Municípios": pares.map(comum.numero).values,
}), hide_index=True)
st.caption(
    "Empate = os dois primeiros tiveram exatamente o mesmo número de votos. "
    "Município novo: Boa Esperança do Norte (MT), instalado em 2025 (não existia em 2022)."
)


@st.cache_data(show_spinner=False)
def tabela_transicao(uf: str | None) -> pd.DataFrame:
    d = na_area(uf)
    return pd.DataFrame({
        "Município": d["nm_municipio"], "UF": d["uf"],
        "Mais votado em 2022": ["— (município novo)" if pd.isna(n) else "empate" if n == "empate" else f"{n} ({p})"
                                for n, p in zip(d["mais_votado_2022"], d["partido_2022"])],
        "Mais votado em 2026": [f"empate ({e})" if n == "empate" else f"{n} ({p})"
                                for n, p, e in zip(d["mais_votado"], d["partido_mais_votado"], d["empatados"])],
        "Mudou?": d["transicao"].map(lambda t: "não" if "nas duas" in t else
                                     "sim" if t in CONHECIDAS else "—"),
    }).sort_values(["UF", "Município"], key=lambda s: s.map(sem_acento))


@st.fragment
def secao_transicao() -> None:
    uf = escolher_area("area_transicao")
    d = na_area(uf)
    tabela = tabela_transicao(uf)
    hover = dict(zip(tabela.index, zip(tabela["Município"], tabela["UF"], tabela["Mais votado em 2022"],
                                       tabela["Mais votado em 2026"])))
    modelo = ("<b>%{customdata[0]} (%{customdata[1]})</b><br>2022: %{customdata[2]}<br>"
              "2026: %{customdata[3]}<extra></extra>")
    tracos = []
    restante = d[~d["transicao"].isin(CONHECIDAS)]
    for rotulo, legenda, cor in CATEGORIAS + [("outros", "Empate ou município novo", comum.APAGADO)]:
        parte = restante if rotulo == "outros" else d[d["transicao"] == rotulo]
        if rotulo == "outros" and parte.empty:
            continue
        if parte.empty:
            # categoria sem nenhum município: aparece na legenda com (0), com o mesmo destaque das outras
            tracos.append(go.Scattergeo(
                lon=[None], lat=[None], mode="markers", name=f"{legenda} (0)", showlegend=True,
                marker=dict(symbol="square", size=12, color=cor), hoverinfo="skip",
            ))
            continue
        tracos.append(go.Choropleth(
            geojson=geojson_de(parte["cd_municipio_ibge"]), locations=parte["cd_municipio_ibge"],
            z=[1] * len(parte), colorscale=[[0, cor], [1, cor]], showscale=False, showlegend=True,
            name=f"{legenda} ({comum.numero(len(parte))})",
            customdata=[hover[i] for i in parte.index], hovertemplate=modelo, **contorno(uf),
        ))
    fig = figura_mapa(tracos, d["cd_municipio_ibge"], altura=640 if uf is None else 560, legenda=True)
    fig.update_layout(legend=dict(orientation="h", y=1.0, yanchor="bottom", x=0, font=dict(size=12)),
                      margin=dict(t=70))
    titulo(f"Partido do mais votado para Presidente: 1º turno de 2022 e de 2026 — {nome_area(uf)}",
           "Cor clara: o mesmo partido nas duas eleições. Cor forte: mudou, com a cor de quem ficou à frente "
           "em 2026. Entre parênteses, o número de municípios.")
    comum.mostrar(fig, tabela=tabela, fonte=f"{FONTE_HISTORICO}; malha municipal do IBGE", chave="mapa_transicao")


secao_transicao()

with st.expander("Contagem por UF"):
    por_uf = (municipios.assign(t=lambda d: d["transicao"].where(d["transicao"].isin(CONHECIDAS), "outros"))
              .pivot_table(index="uf", columns="t", values="cd_municipio_tse", aggfunc="count", fill_value=0))
    tabela_uf = pd.DataFrame({"UF": [UF_NOMES[u] for u in por_uf.index],
                              "Municípios": por_uf.sum(axis=1).map(comum.numero).values})
    for rotulo, legenda, _ in sorted(CATEGORIAS, key=lambda c: c[1]):
        tabela_uf[legenda] = por_uf[rotulo].values if rotulo in por_uf else 0
    if "outros" in por_uf:
        tabela_uf["Empate ou município novo"] = por_uf["outros"].values
    st.dataframe(tabela_uf.sort_values("UF", key=lambda s: s.map(sem_acento)), hide_index=True)

# --- 4. brancos, nulos e abstenção ---------------------------------------------------
st.header("Brancos, nulos e abstenção", anchor="brancos-nulos-e-abstencao")
st.markdown(
    "**Abstenção** é quem não foi votar. Quem foi votar pode votar **em branco** (apertar a tecla BRANCO) "
    "ou **nulo** (digitar um número que não é de nenhum candidato). Brancos e nulos não contam para "
    "ninguém: o resultado é calculado só com os **votos válidos**."
)
por_uf_c = comum.ler("resultados_comparecimento_uf")


def grafico_serie(coluna: str, nome: str, maximo: float) -> go.Figure:
    fig = go.Figure()
    for turno, cor, traco in ((1, comum.SERIE, "solid"), (2, comum.MUDO, "dash")):
        s = serie[serie["turno"] == turno]
        fig.add_trace(go.Scatter(
            x=s["ano"], y=100 * s[coluna], name=f"{turno}º turno", mode="lines+markers",
            line=dict(color=cor, width=2, dash=traco), marker=dict(size=8, color=cor),
            hovertemplate=f"{nome}, %{{x}}, {turno}º turno: %{{y:.1f}}%<extra></extra>",
        ))
    comum.estilo(fig, altura=300)
    fig.update_xaxes(tickvals=sorted(serie["ano"].unique()), title=None, tickangle=0, tickfont=dict(size=11))
    fig.update_yaxes(ticksuffix="%", range=[0, maximo], rangemode="tozero")
    return fig


def tabela_serie(coluna: str) -> pd.DataFrame:
    t = serie.pivot_table(index="ano", columns="turno", values=coluna)
    return pd.DataFrame({"Ano": t.index.astype(str),
                         "1º turno": t[1].map(comum.pct).values,
                         "2º turno": t[2].map(lambda v: "—" if pd.isna(v) else comum.pct(v)).values})


st.subheader("De 2002 a 2026, no Brasil (com o exterior)")
st.caption("Em 2026 ainda não houve 2º turno (será em 25 de outubro).")
s1, s2, s3 = st.columns(3)
with s1:
    titulo("Abstenção (% do eleitorado)")
    comum.mostrar(grafico_serie("pct_abstencao", "Abstenção", 25), tabela=tabela_serie("pct_abstencao"),
                  fonte=FONTE_HISTORICO, chave="serie_abstencao")
with s2:
    titulo("Brancos (% de quem foi votar)")
    comum.mostrar(grafico_serie("pct_brancos", "Brancos", 8), tabela=tabela_serie("pct_brancos"),
                  fonte=FONTE_HISTORICO, chave="serie_brancos")
with s3:
    titulo("Nulos (% de quem foi votar)")
    comum.mostrar(grafico_serie("pct_nulos", "Nulos", 8), tabela=tabela_serie("pct_nulos"),
                  fonte=FONTE_HISTORICO, chave="serie_nulos")

st.subheader("1º turno de 2026, por UF")
ufs_c = por_uf_c[por_uf_c["uf"] != "ZZ"].assign(nome=lambda d: d["uf"].map(UF_NOMES))
ext = por_uf_c[por_uf_c["uf"] == "ZZ"].iloc[0]
st.caption(
    f"No exterior, {comum.pct(ext['pct_abstencao'])} dos eleitores não foram votar; o exterior fica fora dos "
    f"gráficos para não achatar a escala. Média do Brasil: {comum.pct(total_2026['pct_abstencao'])} de abstenção "
    f"e {comum.pct(total_2026['pct_brancos'] + total_2026['pct_nulos'])} de brancos e nulos."
)


def barras_uf(valores: pd.Series, nome: str) -> go.Figure:
    d = ufs_c.assign(v=valores).sort_values("v")
    fig = go.Figure(go.Bar(
        x=100 * d["v"], y=d["nome"], orientation="h", marker_color=comum.SERIE, width=0.6,
        hovertemplate=f"%{{y}}: %{{x:.1f}}% {nome}<extra></extra>",
    ))
    comum.estilo(fig, altura=40 + 22 * len(d), legenda=False)
    fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor=comum.GRADE)
    fig.update_yaxes(showgrid=False, automargin=True, tickfont=dict(size=12))
    return fig


u1, u2 = st.columns(2, gap="large")
with u1:
    titulo("Abstenção, em % do eleitorado", "Da maior (no alto) para a menor.")
    comum.mostrar(
        barras_uf(ufs_c["pct_abstencao"], "de abstenção"), fonte=FONTE_2026, chave="uf_abstencao",
        tabela=ufs_c.sort_values("nome", key=lambda s: s.map(sem_acento)).assign(
            **{"UF": lambda d: d["nome"], "Eleitores": lambda d: d["qt_aptos"].map(comum.numero),
               "Não foram votar": lambda d: d["qt_abstencoes"].map(comum.numero),
               "Abstenção": lambda d: d["pct_abstencao"].map(comum.pct)})[
            ["UF", "Eleitores", "Não foram votar", "Abstenção"]],
    )
with u2:
    titulo("Brancos e nulos somados, em % de quem foi votar", "Do maior (no alto) para o menor.")
    comum.mostrar(
        barras_uf(ufs_c["pct_brancos"] + ufs_c["pct_nulos"], "de brancos e nulos"), fonte=FONTE_2026,
        chave="uf_brancos_nulos",
        tabela=ufs_c.sort_values("nome", key=lambda s: s.map(sem_acento)).assign(
            **{"UF": lambda d: d["nome"], "Foram votar": lambda d: d["qt_comparecimento"].map(comum.numero),
               "Brancos": lambda d: d["pct_brancos"].map(comum.pct),
               "Nulos": lambda d: d["pct_nulos"].map(comum.pct)})[["UF", "Foram votar", "Brancos", "Nulos"]],
    )

st.subheader("Municípios com maior e menor abstenção")
st.caption(
    "Lista descritiva dos 10 de cada ponta. Em municípios pequenos a porcentagem varia mais, porque poucas "
    "pessoas mudam muito a conta; o cadastro de eleitores também pode ter pessoas que se mudaram e não "
    "transferiram o título."
)


def lista_abstencao(d: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Município": d["nm_municipio"], "UF": d["uf"], "Eleitores": d["qt_aptos"].map(comum.numero),
        "Não foram votar": d["pct_abstencao"].map(comum.pct),
    })


l1, l2 = st.columns(2, gap="large")
with l1:
    st.markdown("**Maior abstenção**")
    st.dataframe(lista_abstencao(municipios.nlargest(10, "pct_abstencao")), hide_index=True)
with l2:
    st.markdown("**Menor abstenção**")
    st.dataframe(lista_abstencao(municipios.nsmallest(10, "pct_abstencao")), hide_index=True)

# --- 5. quociente eleitoral ------------------------------------------------------------
st.header("Quociente eleitoral: por que nem sempre o mais votado entra", anchor="quociente-eleitoral")
deputados = comum.ler("resultados_deputados")
dep_uf = comum.ler("resultados_deputados_uf")
sp = dep_uf.set_index("uf").loc["SP"]
st.markdown(
    "Para Deputado Federal a conta é feita primeiro por **partido** (ou federação de partidos), e só depois "
    "por candidato:\n"
    "1. Somam-se os votos válidos do estado e divide-se pelo número de vagas. O resultado é o **quociente "
    f"eleitoral**. Exemplo: em São Paulo, {comum.numero(sp['qt_validos'])} votos válidos ÷ {sp['vagas']} vagas "
    f"= {comum.numero(sp['quociente_eleitoral'])} votos.\n"
    "2. Cada partido soma os votos de todos os seus candidatos mais os votos só no número do partido "
    "(voto de legenda). Ele ganha uma vaga para cada quociente eleitoral que atingiu: é o **quociente "
    "partidário** (\"eleito por QP\").\n"
    "3. As vagas que sobram são distribuídas pelas **maiores médias** (\"eleito por média\"), com exigências "
    "mínimas de votação para o partido e para o candidato.\n"
    "4. Dentro de cada partido, as vagas vão para os seus candidatos **mais votados**.\n\n"
    "Por isso um candidato com muitos votos pode ficar de fora, se o partido dele não somou votos para mais "
    "uma vaga, e outro com menos votos pode entrar, puxado pelos votos do partido."
)
concluidas = dep_uf[dep_uf["totalizacao_final"]]
pendentes = dep_uf[~dep_uf["totalizacao_final"]]
com_casos = concluidas[concluidas["fora_com_mais_votos"] > 0]
st.markdown(
    f"Em 2026 são **{comum.numero(dep_uf['vagas'].sum())} vagas**. "
    f"Já estão definidos **{comum.numero(concluidas['eleitos'].sum())} eleitos**: "
    f"{comum.numero(concluidas['eleitos_qp'].sum())} pelo quociente partidário e "
    f"{comum.numero(concluidas['eleitos_media'].sum())} pelas médias. "
    f"Em **{len(com_casos)} das {len(concluidas)} UFs** com resultado final, pelo menos um candidato ficou de "
    f"fora tendo mais votos do que o eleito menos votado do mesmo estado."
)
if len(pendentes):
    st.info(
        "Ainda sem eleitos definidos: "
        + "; ".join(f"{UF_NOMES[r.uf]} ({r.vagas} vagas). Mensagem do TSE: \"{r.mensagem_tse}\" "
                    f"(arquivo de {r.dt_geracao})" for r in pendentes.itertuples())
        + ". Rodar de novo o script desta página atualiza quando o TSE concluir.",
        icon=":material/hourglass_top:",
    )

d_fora = concluidas.assign(nome=lambda d: d["uf"].map(UF_NOMES)).sort_values("fora_com_mais_votos")
fig = go.Figure(go.Bar(
    x=d_fora["fora_com_mais_votos"], y=d_fora["nome"], orientation="h", marker_color=comum.SERIE, width=0.6,
    customdata=list(zip(d_fora["menor_eleito"] + " (" + d_fora["partido_menor_eleito"] + ")",
                        d_fora["votos_menor_eleito"].map(comum.numero))),
    hovertemplate="%{y}: %{x} candidatos de fora com mais votos que %{customdata[0]}, "
                  "eleito com %{customdata[1]} votos<extra></extra>",
))
comum.estilo(fig, altura=40 + 22 * len(d_fora), legenda=False)
fig.update_xaxes(showgrid=True, gridcolor=comum.GRADE, title="candidatos")
fig.update_yaxes(showgrid=False, automargin=True, tickfont=dict(size=12))
titulo("Quantos candidatos ficaram de fora com mais votos do que o eleito menos votado da UF",
       "Só votos válidos: candidatos com votos anulados por estarem sub judice (candidatura em julgamento) "
       "não entram. Em cada UF, a régua é o eleito com menos votos daquele estado.")
tabela_dep = d_fora.sort_values("nome", key=lambda s: s.map(sem_acento))
comum.mostrar(
    fig, fonte="TSE, resultados de Deputado Federal do 1º turno de 2026 (resultados.tse.jus.br)", chave="dep_fora",
    tabela=pd.DataFrame({
        "UF": tabela_dep["nome"], "Vagas": tabela_dep["vagas"],
        "Quociente eleitoral (votos)": tabela_dep["quociente_eleitoral"].map(comum.numero),
        "Eleito com menos votos": tabela_dep["menor_eleito"] + " (" + tabela_dep["partido_menor_eleito"] + ")",
        "Votos do eleito": tabela_dep["votos_menor_eleito"].map(comum.numero),
        "Não eleito com mais votos": tabela_dep["maior_nao_eleito"] + " (" + tabela_dep["partido_maior_nao_eleito"] + ")",
        "Votos do não eleito": tabela_dep["votos_maior_nao_eleito"].map(comum.numero),
        "De fora com mais votos que o eleito menos votado": tabela_dep["fora_com_mais_votos"],
    }),
)


@st.fragment
def secao_deputados() -> None:
    opcoes = sorted(concluidas["uf"], key=lambda u: sem_acento(UF_NOMES[u]))
    uf = st.selectbox("Ver os candidatos de", opcoes, index=opcoes.index("DF") if "DF" in opcoes else 0,
                      format_func=lambda u: f"{UF_NOMES[u]} ({u})", key="uf_deputados")
    resumo = dep_uf.set_index("uf").loc[uf]
    c = deputados[(deputados["uf"] == uf) & deputados["voto_valido"]]
    n = 10
    eleitos = c[c["eleito"]].nsmallest(n, "qt_votos")
    fora = c[~c["eleito"]].nlargest(n, "qt_votos")
    d = pd.concat([eleitos, fora]).sort_values("qt_votos")
    fig = go.Figure()
    for eleito, nome_grupo, cor in ((True, "Eleito(a)", comum.SERIE), (False, "Não eleito(a)", comum.APAGADO)):
        g = d[d["eleito"] == eleito]
        fig.add_trace(go.Bar(
            x=g["qt_votos"], y=g["nm_urna"] + "<br>" + g["sg_partido"], orientation="h", name=nome_grupo,
            marker_color=cor, width=0.6, customdata=list(zip(g["qt_votos"].map(comum.numero), g["situacao"])),
            hovertemplate="%{y}<br>%{customdata[0]} votos · %{customdata[1]}<extra></extra>",
        ))
    comum.estilo(fig, altura=90 + 36 * len(d))
    fig.update_yaxes(categoryorder="array", categoryarray=list(d["nm_urna"] + "<br>" + d["sg_partido"]),
                     showgrid=False, automargin=True, tickfont=dict(size=12))
    fig.update_xaxes(showgrid=True, gridcolor=comum.GRADE, title="votos", tickformat=",d", nticks=4, tickangle=0)
    titulo(f"{UF_NOMES[uf]}: os {n} eleitos com menos votos e os {n} não eleitos com mais votos",
           f"{resumo['vagas']} vagas; quociente eleitoral de {comum.numero(resumo['quociente_eleitoral'])} votos. "
           "Barras do mais votado (no alto) para o menos votado; a cor diz se a pessoa foi eleita.")
    comum.mostrar(
        fig, fonte="TSE, resultados de Deputado Federal do 1º turno de 2026 (resultados.tse.jus.br)",
        chave="dep_uf",
        tabela=pd.DataFrame({
            "Candidato": d["nm_urna"], "Partido": d["sg_partido"],
            "Coligação ou federação": d["agrupamento"], "Votos": d["qt_votos"].map(comum.numero),
            "Situação": d["situacao"],
        }).iloc[::-1],
    )


secao_deputados()

# --- 6. voto dividido ---------------------------------------------------------------
st.header("Voto dividido: Presidente e Governador", anchor="voto-dividido")
if "lado" not in municipios.columns:
    comum.em_construcao("rode scripts/site_resultados.py sem --sem-governador para gerar esta parte.")
else:
    validos_lado = municipios[municipios["lado"] != "empate"]
    st.markdown(
        "Em cada município, olhamos o candidato a Presidente mais votado e o candidato a Governador mais "
        "votado no 1º turno. A regra, a mesma para todos: **o partido do presidenciável mais votado faz parte "
        "da coligação (ou federação) do candidato a Governador mais votado?** O Distrito Federal entra "
        "(também elege Governador); o exterior fica de fora, porque não vota para Governador."
    )
    resumo_lado = validos_lado["lado"].value_counts()
    linhas = []
    for nome in (A, B):
        g = validos_lado[validos_lado["mais_votado"] == nome]
        mesma = int((g["lado"] == "mesma coligação").sum())
        linhas.append(
            f"{quadrado(CORES[nome])} Onde **{nome}** foi o mais votado ({comum.numero(len(g))} municípios), "
            f"o Governador mais votado era da coligação do {PARTIDO[nome]} em **{comum.numero(mesma)}** "
            f"({comum.pct(mesma / len(g)) if len(g) else '—'})."
        )
    st.markdown("  \n".join(linhas), unsafe_allow_html=True)
    sem = validos_lado[validos_lado["lado"] == "partido sem candidato a Governador"]
    st.caption(
        f"No total, {comum.numero(resumo_lado.get('mesma coligação', 0))} municípios com Presidente e Governador "
        f"mais votados do mesmo lado e {comum.numero(resumo_lado.get('coligações diferentes', 0))} com lados "
        f"diferentes. Em {len(sem)} municípios o partido do presidenciável mais votado não estava em nenhuma "
        f"coligação com candidato a Governador ({', '.join(sorted(UF_NOMES[u] for u in sem['uf'].unique()))}). "
        f"Os {int((municipios['lado'] == 'empate').sum())} municípios com empate para Presidente ficam de fora."
    )

    por_uf_lado = (validos_lado.groupby("uf")["lado"].value_counts().unstack(fill_value=0)
                   .reindex(columns=["mesma coligação", "coligações diferentes",
                                     "partido sem candidato a Governador"], fill_value=0))
    por_uf_lado["total"] = por_uf_lado.sum(axis=1)
    por_uf_lado["pct"] = por_uf_lado["mesma coligação"] / por_uf_lado["total"]
    d = por_uf_lado.assign(nome=[UF_NOMES[u] for u in por_uf_lado.index]).sort_values("pct")
    fig = go.Figure(go.Bar(
        x=100 * d["pct"], y=d["nome"], orientation="h", marker_color=comum.SERIE, width=0.6,
        customdata=list(zip(d["mesma coligação"], d["total"])),
        hovertemplate="%{y}: %{x:.0f}% (%{customdata[0]} de %{customdata[1]} municípios)<extra></extra>",
    ))
    comum.estilo(fig, altura=40 + 22 * len(d), legenda=False)
    fig.update_xaxes(ticksuffix="%", range=[0, 100], showgrid=True, gridcolor=comum.GRADE)
    fig.update_yaxes(showgrid=False, automargin=True, tickfont=dict(size=12))
    titulo("Municípios em que o Governador mais votado é da coligação do partido do presidenciável mais votado, "
           "em % dos municípios da UF",
           "100% = em todos os municípios da UF os dois mais votados estavam do mesmo lado. O resultado depende "
           "de como os partidos se coligaram em cada estado.")
    tabela_lado = d.sort_values("nome", key=lambda s: s.map(sem_acento))
    comum.mostrar(
        fig, fonte="TSE, resultados do 1º turno de 2026 para Presidente e Governador (resultados.tse.jus.br)",
        chave="voto_dividido",
        tabela=pd.DataFrame({
            "UF": tabela_lado["nome"], "Municípios": tabela_lado["total"],
            "Mesma coligação": tabela_lado["mesma coligação"],
            "Coligações diferentes": tabela_lado["coligações diferentes"],
            "Partido do presidenciável sem candidato a Governador": tabela_lado["partido sem candidato a Governador"],
            "% mesma coligação": tabela_lado["pct"].map(comum.pct),
        }),
    )
    with st.expander("Ver município a município"):
        st.dataframe(pd.DataFrame({
            "Município": municipios["nm_municipio"], "UF": municipios["uf"],
            "Presidente: mais votado": (municipios["mais_votado"] + " (" + municipios["partido_mais_votado"] + ")")
                                       .where(municipios["mais_votado"] != "empate", "empate"),
            "Governador: mais votado": municipios["gov_mais_votado"] + " (" + municipios["gov_partido"] + ")",
            "Coligação do Governador": municipios["gov_coligacao"].str.replace("/", " / "),
            "Resultado da regra": municipios["lado"],
        }).sort_values(["UF", "Município"], key=lambda s: s.map(sem_acento)), hide_index=True)

comum.rodape(metodologia="scripts/site_resultados.py")
