import json

import comum
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

comum.cabecalho(
    "Mapa do Distrito Federal",
    "Como votou cada uma das 35 regiões administrativas e cada local de votação do DF, no 1º turno de 2026 e "
    "nas eleições de 2022.",
)

disputas = comum.ler("df_disputas").set_index("disputa")
regioes = comum.ler("df_regioes")
locais = comum.ler("df_locais")


@st.cache_data(show_spinner=False)
def poligonos() -> dict:
    return json.loads((comum.DADOS / "df_ras.json").read_text(encoding="utf-8"))


def com_percentuais(tabela: pd.DataFrame, d: pd.Series) -> pd.DataFrame:
    """Acrescenta o % de cada um dos dois (nos votos dos dois) e a diferença em pontos,
    sempre do 1º em ordem alfabética menos o 2º."""
    tabela = tabela.copy()
    primeiro, segundo = sorted([d["nm_a"], d["nm_b"]])
    col_primeiro = "qt_a" if primeiro == d["nm_a"] else "qt_b"
    col_segundo = "qt_b" if col_primeiro == "qt_a" else "qt_a"
    dois = (tabela["qt_a"] + tabela["qt_b"]).where(lambda x: x > 0)
    tabela["pct_primeiro"] = tabela[col_primeiro] / dois
    tabela["pct_segundo"] = tabela[col_segundo] / dois
    tabela["pct_primeiro_validos"] = tabela[col_primeiro] / tabela["qt_validos"].where(lambda x: x > 0)
    tabela["pct_segundo_validos"] = tabela[col_segundo] / tabela["qt_validos"].where(lambda x: x > 0)
    tabela["diferenca"] = tabela["pct_primeiro"] - tabela["pct_segundo"]
    tabela["comparecimento"] = tabela["qt_comparecimento"] / tabela["qt_aptos"].where(lambda x: x > 0)
    return tabela


# --- filtros ----------------------------------------------------------------------
ordem = ["pres_2026_1t", "gov_2026_1t", "pres_2022_2t", "pres_2022_1t"]
col1, col2 = st.columns([3, 2])
with col1:
    escolha = st.radio("Disputa", ordem, format_func=lambda k: disputas.loc[k, "titulo"], horizontal=True)
with col2:
    nivel = st.radio("Ver por", ["Região administrativa", "Local de votação"], horizontal=True)

d = disputas.loc[escolha]
primeiro, segundo = sorted([d["nm_a"], d["nm_b"]])
CORES = comum.cores_finalistas([primeiro, segundo])
ras = com_percentuais(regioes[(regioes["disputa"] == escolha) & (regioes["ra"] != "Sem localização")], d)
pontos = com_percentuais(locais[(locais["disputa"] == escolha) & locais["lat"].notna()], d)
total = com_percentuais(regioes[regioes["disputa"] == escolha].sum(numeric_only=True).to_frame().T, d).iloc[0]

# --- resumo ------------------------------------------------------------------------
c1, c2, c3 = st.columns(3)
for coluna, nome, chave in ((c1, primeiro, "pct_primeiro_validos"), (c2, segundo, "pct_segundo_validos")):
    with coluna:
        comum.cartao(f"{nome} no DF", comum.pct(total[chave]), "dos votos válidos", cor=CORES[nome])
lideres = (ras["diferenca"] > 0).sum()
with c3:
    comum.cartao("Regiões administrativas", f"{lideres} × {len(ras) - lideres}",
                 f"com {primeiro} à frente × com {segundo} à frente")

# --- mapa ----------------------------------------------------------------------------
# z positivo = vantagem do 2º em ordem alfabética (verde-água); negativo = do 1º (violeta)
limite = float(np.nanmax(np.abs(ras["diferenca"]))) if nivel == "Região administrativa" else 0.6
limite = max(round(limite + 0.05, 1), 0.1)
escala = dict(colorscale=comum.DIVERGENTE, cmin=-limite, cmax=limite)
barra = dict(orientation="h", x=0.5, xanchor="center", y=0, yanchor="top", len=0.8, thickness=10, outlinewidth=0,
             tickvals=[-limite, 0, limite],
             ticktext=[f"{comum.numero(100 * limite, 0)} pontos", "empate", f"{comum.numero(100 * limite, 0)} pontos"],
             tickfont=dict(color=comum.MUDO, size=11),
             title=dict(text=f"◀ {primeiro} à frente  ·  {segundo} à frente ▶", side="top",
                        font=dict(color=comum.TINTA_2, size=12)))

fig = go.Figure()
contorno = dict(marker=dict(line=dict(color="white", width=1)))
if nivel == "Região administrativa":
    fig.add_trace(go.Choropleth(
        geojson=poligonos(), locations=ras["ra"], featureidkey="properties.ra", z=-ras["diferenca"],
        colorscale=comum.DIVERGENTE, zmin=-limite, zmax=limite, colorbar=barra, **contorno,
        customdata=np.column_stack([ras["pct_primeiro_validos"], ras["pct_segundo_validos"], ras["qt_aptos"],
                                    ras["comparecimento"]]),
        hovertemplate="<b>%{location}</b><br>" + primeiro + ": %{customdata[0]:.1%}<br>" + segundo +
                      ": %{customdata[1]:.1%}<br>eleitores: %{customdata[2]:,.0f} · foram votar: "
                      "%{customdata[3]:.0%}<extra></extra>"))
else:
    fig.add_trace(go.Choropleth(
        geojson=poligonos(), locations=[f["id"] for f in poligonos()["features"]], featureidkey="properties.ra",
        z=[0] * len(poligonos()["features"]), colorscale=[[0, comum.NEUTRO], [1, comum.NEUTRO]], showscale=False,
        marker=dict(line=dict(color=comum.APAGADO, width=1)), hovertemplate="%{location}<extra></extra>"))
    fig.add_trace(go.Scattergeo(
        lat=pontos["lat"], lon=pontos["lon"], mode="markers",
        marker=dict(size=np.clip(np.sqrt(pontos["qt_validos"]) / 6, 5, 22), color=-pontos["diferenca"], **escala,
                    colorbar=barra, opacity=0.9, line=dict(color="white", width=1)),
        customdata=np.column_stack([pontos["nm_local"], pontos["ra"].fillna("—"), pontos["pct_primeiro_validos"],
                                    pontos["pct_segundo_validos"], pontos["qt_validos"]]),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>" + primeiro + ": %{customdata[2]:.1%}<br>" +
                      segundo + ": %{customdata[3]:.1%}<br>votos válidos: %{customdata[4]:,.0f}<extra></extra>"))
# enquadramento fixo no DF (o "fitbounds" do Plotly não funciona bem com polígonos próprios)
coordenadas = np.array([ponto for f in poligonos()["features"] for parte in f["geometry"]["coordinates"]
                        for anel in parte for ponto in anel])
(x0, y0), (x1, y1) = coordenadas.min(axis=0), coordenadas.max(axis=0)
fig.update_geos(visible=False, projection_type="mercator", bgcolor="rgba(0,0,0,0)",
                lonaxis_range=[x0 - 0.01, x1 + 0.01], lataxis_range=[y0 - 0.01, y1 + 0.01])
fig.update_layout(dragmode=False)
comum.estilo(fig, altura=620, legenda=False)
fig.update_layout(margin=dict(l=0, r=0, t=0, b=70))
st.markdown(f"**{d['titulo']}: diferença entre {primeiro} e {segundo}, por "
            f"{'região administrativa' if nivel == 'Região administrativa' else 'local de votação'}**")
comum.mostrar(
    fig,
    tabela=pd.DataFrame({
        "Região administrativa": ras["ra"],
        "Eleitores": ras["qt_aptos"].map(comum.numero),
        "Foram votar": ras["comparecimento"].map(comum.pct),
        f"{primeiro} (% dos válidos)": ras["pct_primeiro_validos"].map(comum.pct),
        f"{segundo} (% dos válidos)": ras["pct_segundo_validos"].map(comum.pct),
    }).sort_values("Região administrativa"),
    fonte="TSE (votação por seção e locais de votação); limites das regiões administrativas: IPE-DF.",
    chave="mapa_df",
)
st.caption(
    f"**Como ler:** quanto mais forte a cor violeta, maior a vantagem de {primeiro}; quanto mais forte o verde, "
    f"maior a vantagem de {segundo}; cinza-claro é quase empate. A diferença é calculada nos votos dos dois. "
    "No modo \"local de votação\", cada círculo é uma escola ou outro local, e o tamanho mostra quantos votos "
    "válidos teve. Cada voto conta onde a pessoa vota, que nem sempre é onde ela mora."
)

# --- ranking -------------------------------------------------------------------------------
st.subheader("Região por região")
ordenado = ras.sort_values("pct_primeiro")
fig = go.Figure()
for nome in (primeiro, segundo):
    parte = ordenado[(ordenado["pct_primeiro"] > 0.5) == (nome == primeiro)]
    fig.add_trace(go.Scatter(
        x=parte["pct_primeiro"], y=parte["ra"], mode="markers", name=f"{nome} à frente",
        marker=dict(color=CORES[nome], size=np.clip(np.sqrt(parte["qt_aptos"]) / 25, 6, 20),
                    line=dict(color=comum.SUPERFICIE, width=2)),
        customdata=parte["qt_aptos"],
        hovertemplate="<b>%{y}</b><br>" + primeiro + ": %{x:.1%} dos votos dos dois<br>eleitores: "
                      "%{customdata:,.0f}<extra></extra>"))
fig.add_vline(x=0.5, line=dict(color=comum.EIXO, width=1))
fig.update_xaxes(tickformat=".0%", title=f"% de {primeiro} nos votos dos dois (o de {segundo} é 100% menos)")
fig.update_yaxes(categoryorder="array", categoryarray=ordenado["ra"].tolist(), showgrid=False)
comum.estilo(fig, altura=760)
comum.mostrar(fig, fonte="TSE; limites das regiões administrativas: IPE-DF.", chave="ranking_df")
st.caption("O tamanho do ponto mostra o número de eleitores da região.")

# --- mudança 2022 -> 2026 ---------------------------------------------------------------------
st.subheader("O que mudou de 2022 para 2026 (Presidente, 1º turno)")
antes, depois = disputas.loc["pres_2022_1t"], disputas.loc["pres_2026_1t"]
r22 = com_percentuais(regioes[(regioes["disputa"] == "pres_2022_1t") & (regioes["ra"] != "Sem localização")], antes)
r26 = com_percentuais(regioes[(regioes["disputa"] == "pres_2026_1t") & (regioes["ra"] != "Sem localização")], depois)
p22, s22 = sorted([antes["nm_a"], antes["nm_b"]])
p26, s26 = sorted([depois["nm_a"], depois["nm_b"]])
mudanca = r22[["ra", "diferenca"]].merge(r26[["ra", "diferenca", "qt_aptos"]], on="ra", suffixes=("_2022", "_2026"))
mudanca["variacao"] = mudanca["diferenca_2026"] - mudanca["diferenca_2022"]
mudanca = mudanca.sort_values("diferenca_2026")
st.markdown(
    f"Nos dois anos, os dois primeiros colocados no DF foram o candidato do PL ({p22} em 2022, {p26} em 2026) e "
    f"{s26}. O gráfico liga a diferença entre os dois em 2022 (cinza) à de 2026 (colorida), em cada região."
)
fig = go.Figure()
for _, linha in mudanca.iterrows():
    fig.add_trace(go.Scatter(x=[linha["diferenca_2022"], linha["diferenca_2026"]], y=[linha["ra"]] * 2,
                             mode="lines", line=dict(color=comum.APAGADO, width=2), hoverinfo="skip",
                             showlegend=False))
fig.add_trace(go.Scatter(
    x=mudanca["diferenca_2022"], y=mudanca["ra"], mode="markers", name="2022",
    marker=dict(color=comum.APAGADO, size=9, line=dict(color=comum.SUPERFICIE, width=2)),
    hovertemplate="<b>%{y}</b><br>2022: %{x:+.1%}<extra></extra>"))
fig.add_trace(go.Scatter(
    x=mudanca["diferenca_2026"], y=mudanca["ra"], mode="markers", name="2026",
    marker=dict(color=[CORES[p26] if v > 0 else CORES[s26] for v in mudanca["diferenca_2026"]], size=11,
                line=dict(color=comum.SUPERFICIE, width=2)),
    customdata=mudanca["variacao"],
    hovertemplate="<b>%{y}</b><br>2026: %{x:+.1%}<br>mudança: %{customdata:+.1%}<extra></extra>"))
fig.add_vline(x=0, line=dict(color=comum.EIXO, width=1))
alcance = float(np.nanmax(np.abs(mudanca[["diferenca_2022", "diferenca_2026"]].to_numpy()))) + 0.05
fig.update_xaxes(range=[-alcance, alcance], tickformat="+.0%",
                 title=f"← vantagem de {s26}  ·  diferença em pontos  ·  vantagem do candidato do PL →")
fig.update_yaxes(categoryorder="array", categoryarray=mudanca["ra"].tolist(), showgrid=False)
comum.estilo(fig, altura=760)
comum.mostrar(
    fig,
    tabela=pd.DataFrame({
        "Região administrativa": mudanca["ra"],
        f"2022 ({p22} − {s22})": mudanca["diferenca_2022"].map(lambda x: f"{100 * x:+.1f}".replace(".", ",")),
        f"2026 ({p26} − {s26})": mudanca["diferenca_2026"].map(lambda x: f"{100 * x:+.1f}".replace(".", ",")),
        "Mudança (pontos)": mudanca["variacao"].map(lambda x: f"{100 * x:+.1f}".replace(".", ",")),
    }).iloc[::-1],
    fonte="TSE (boletins de urna de 2022 e votação por seção de 2026); limites: IPE-DF.",
    chave="mudanca_df",
)
mais = mudanca["variacao"].gt(0).sum()
st.caption(
    f"**Como ler:** a diferença é em pontos, nos votos dos dois. Em {mais} das {len(mudanca)} regiões a "
    f"diferença andou na direção do candidato do PL; nas outras {len(mudanca) - mais}, na direção de {s26}."
)

st.subheader("Sobre os dados")
st.markdown(
    """
- **Regiões administrativas:** limites oficiais das 35 RAs, publicados pelo IPE-DF (antiga Codeplan). Cada local de
  votação foi colocado na RA pelo ponto (latitude e longitude) que o TSE informa.
- **Voto conta onde a pessoa vota**, que nem sempre é onde ela mora: quem se mudou e não transferiu o título vota
  no local antigo.
- **A soma bate com o oficial:** somando as seções, os votos de cada candidato no DF são iguais ao resultado oficial
  do TSE nas quatro disputas.
- **Governador:** no DF, CELINA LEÃO e LEANDRO GRASS disputam o 2º turno em 25/10.
"""
)
comum.rodape()
