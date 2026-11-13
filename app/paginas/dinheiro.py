"""Dinheiro de campanha: quanto as candidaturas de 2026 arrecadaram e gastaram, de onde veio o dinheiro,
para quem foi o fundo eleitoral e quanto custou cada voto.

Dados: app/dados/dinheiro_*.parquet, gerados por scripts/site_dinheiro.py (prestação de contas final do
1º turno entregue ao TSE).
"""

import comum
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

comum.cabecalho("Dinheiro de campanha",
                "Quanto as candidaturas de 2026 arrecadaram e gastaram, de onde veio o dinheiro, para quem foi o fundo "
                "eleitoral e quanto custou cada voto.")

if not comum.existe("dinheiro_resumo"):
    comum.em_construcao("Esta página")
    st.stop()

resumo = comum.ler("dinheiro_resumo").iloc[0]
cargos = comum.ler("dinheiro_cargo").set_index("cargo")
fundo = comum.ler("dinheiro_fundo_grupos")
despesas = comum.ler("dinheiro_despesas")
custo = comum.ler("dinheiro_custo_voto")
faixas = comum.ler("dinheiro_faixas_gasto")

FONTE = (f"TSE, prestação de contas eleitorais dos candidatos de 2026 (contas finais do 1º turno; arquivo de "
         f"{resumo['dt_geracao']})")
CATEGORIAS = ["Fundo eleitoral", "Fundo partidário", "Partido (outros recursos)", "Pessoas físicas",
              "Recursos próprios", "Outros"]
MINIMO_FUNDO = 1e6   # partidos com menos de R$ 1 milhão de fundo eleitoral dariam porcentagens de poucos repasses


def reais(valor: float) -> str:
    """R$ em bilhões, milhões ou mil, com vírgula decimal."""
    if abs(valor) >= 1e9:
        return f"R$ {comum.numero(valor / 1e9, 2)} bilhões"
    if abs(valor) >= 1e6:
        return f"R$ {comum.numero(valor / 1e6, 1)} milhões"
    if abs(valor) >= 1e3:
        return f"R$ {comum.numero(valor / 1e3, 0)} mil"
    return f"R$ {comum.numero(valor, 2)}"


st.info(
    f"**Contas finais do 1º turno**, entregues ao TSE por {comum.numero(resumo['candidatos_com_contas'])} "
    f"candidaturas (arquivo de {resumo['dt_geracao']}). As contas do 2º turno de Presidente e de Governador vencem "
    f"em 24 de novembro e ainda não entram. {comum.numero(resumo['candidatos_so_parcial'])} candidaturas só tinham "
    "entregado contas parciais e também ficam de fora. Doações de um candidato a outro não são somadas de novo: o "
    "dinheiro já foi contado onde entrou.",
    icon=":material/info:",
)

# --- resumo -------------------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
with c1:
    comum.cartao("Arrecadado", reais(resumo["receitas"]), "pelas candidaturas, no 1º turno")
with c2:
    comum.cartao("Dos fundos públicos", comum.pct(resumo["parte_fundos_publicos"], 0),
                 "fundo eleitoral e fundo partidário, pagos com dinheiro público")
with c3:
    comum.cartao("Gasto contratado", reais(resumo["despesas_contratadas"]), "em despesas declaradas")
with c4:
    comum.cartao("Doadores pessoas físicas", comum.numero(resumo["doadores_pessoas_fisicas"]),
                 f"o 1% que mais doou deu {comum.pct(resumo['parte_1pct_doadores'], 0)} do valor doado por pessoas")

# --- 1. de onde veio ------------------------------------------------------------------------
st.header("De onde veio o dinheiro")
valores = pd.Series({c: resumo[f"receitas_{c}"] for c in CATEGORIAS}).sort_values()
fig = go.Figure(go.Bar(
    x=valores / resumo["receitas"], y=valores.index, orientation="h", marker_color=comum.SERIE, width=0.55,
    text=[f"{comum.pct(v / resumo['receitas'], 0)} · {reais(v)}" for v in valores], textposition="outside",
    cliponaxis=False, hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
comum.estilo(fig, altura=320, legenda=False)
fig.update_xaxes(tickformat=".0%", range=[0, 0.95], showgrid=True, gridcolor=comum.GRADE)
st.markdown("**Parte de cada fonte no total arrecadado pelas candidaturas (2026, 1º turno)**")
st.caption("Fundo eleitoral: dinheiro público dividido entre os partidos pelo tamanho da bancada; cada partido "
           "decide quanto vai para cada candidatura. Recursos próprios: o candidato pagando a própria campanha.")
por_cargo = cargos[CATEGORIAS].div(cargos[CATEGORIAS].sum(axis=1), axis=0)
tabela = pd.DataFrame({"Cargo": cargos.index, "Candidaturas": cargos["candidatos"].map(comum.numero),
                       "Arrecadado": cargos[CATEGORIAS].sum(axis=1).map(reais),
                       "Mediana por candidatura": cargos["mediana_por_candidato"].map(reais)})
for c in CATEGORIAS:
    tabela[c] = por_cargo[c].map(lambda v: comum.pct(v, 0)).values
comum.mostrar(fig, tabela=tabela, fonte=FONTE, chave="fontes")
proprios = cargos["parte_candidatos_mais_da_metade_proprio"]
maior = por_cargo.idxmax(axis=1)
com_fundo = [c for c in maior.index if maior[c] == "Fundo eleitoral"]
excecoes = "; ".join(f"para {c}, {maior[c].lower()}" for c in maior.index if maior[c] != "Fundo eleitoral")
st.markdown(
    f"**Por cargo** (na tabela acima): o fundo eleitoral é a maior fonte para "
    f"{', '.join(com_fundo[:-1])} e {com_fundo[-1]}"
    + (f" ({excecoes})" if excecoes else "") + ". A mediana mostra a "
    f"campanha típica: metade arrecadou menos que isso. Uma candidatura a Deputado Federal típica arrecadou "
    f"{reais(cargos.loc['Deputado Federal', 'mediana_por_candidato'])}. Pagaram mais da metade da campanha do "
    f"próprio bolso {comum.pct(proprios.loc['Deputado Federal'], 0)} das candidaturas a Deputado Federal e "
    f"{comum.pct(proprios.loc['Deputado Estadual ou Distrital'], 0)} das a Deputado Estadual ou Distrital "
    "(entre as que arrecadaram algum valor)."
)

# --- 2. fundo para mulheres e pessoas pretas e pardas ---------------------------------------
st.header("Fundo eleitoral para mulheres e para pessoas pretas e pardas")
todos = fundo[fundo["sg_partido"] == "Todos os partidos"].iloc[0]
partidos = fundo[(fundo["sg_partido"] != "Todos os partidos") & (fundo["fundo"] >= MINIMO_FUNDO)].sort_values(
    "sg_partido", ascending=False)
st.markdown(
    "Pela Constituição (Emendas 117/2022 e 133/2024), os partidos têm de aplicar **pelo menos 30%** do fundo "
    "eleitoral em candidaturas de mulheres (mais, se elas forem mais de 30% das candidaturas) e pelo menos 30% em "
    "candidaturas de pessoas pretas e pardas. Somando todos os partidos, **mulheres** eram "
    f"{comum.pct(todos['parte_candidatas_mulheres'], 0)} das candidaturas e receberam "
    f"{comum.pct(todos['parte_fundo_mulheres'], 0)} do fundo; **pessoas pretas e pardas** eram "
    f"{comum.pct(todos['parte_candidatos_negros'], 0)} e receberam {comum.pct(todos['parte_fundo_negros'], 0)}."
)


def grafico_fundo(coluna_candidatos: str, coluna_fundo: str, grupo: str) -> go.Figure:
    fig = go.Figure()
    for _, p in partidos.iterrows():
        fig.add_trace(go.Scatter(x=[p[coluna_candidatos], p[coluna_fundo]], y=[p["sg_partido"]] * 2, mode="lines",
                                 line=dict(color=comum.GRADE, width=3), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=partidos[coluna_candidatos], y=partidos["sg_partido"], mode="markers",
                             name=f"parte das candidaturas ({grupo})",
                             marker=dict(color=comum.APAGADO, size=10, line=dict(color=comum.MUDO, width=1)),
                             hovertemplate="%{y}: %{x:.0%} das candidaturas<extra></extra>"))
    fig.add_trace(go.Scatter(x=partidos[coluna_fundo], y=partidos["sg_partido"], mode="markers",
                             name=f"parte do fundo eleitoral ({grupo})", marker=dict(color=comum.SERIE, size=11),
                             hovertemplate="%{y}: %{x:.0%} do fundo<extra></extra>"))
    fig.add_vline(x=0.30, line=dict(color=comum.DESTAQUE, width=1.5, dash="dash"),
                  annotation_text="30%", annotation_position="top", annotation_font=dict(color=comum.DESTAQUE))
    comum.estilo(fig, altura=40 + 26 * len(partidos))
    fig.update_xaxes(tickformat=".0%", range=[0, 1], showgrid=True, gridcolor=comum.GRADE)
    return fig


def tabela_fundo(coluna_candidatos: str, coluna_fundo: str) -> pd.DataFrame:
    t = partidos.sort_values("sg_partido")
    return pd.DataFrame({"Partido": t["sg_partido"], "Fundo eleitoral recebido": t["fundo"].map(reais),
                         "Parte das candidaturas": t[coluna_candidatos].map(lambda v: comum.pct(v, 1)),
                         "Parte do fundo": t[coluna_fundo].map(lambda v: comum.pct(v, 1))})


abas = st.tabs(["Mulheres", "Pessoas pretas e pardas"])
for aba, (col_c, col_f, grupo) in zip(abas, [("parte_candidatas_mulheres", "parte_fundo_mulheres", "mulheres"),
                                             ("parte_candidatos_negros", "parte_fundo_negros",
                                              "pessoas pretas e pardas")]):
    with aba:
        st.markdown(f"**Parte do fundo eleitoral que chegou a candidaturas de {grupo}, por partido**")
        st.caption("Cinza: a parte que elas eram entre as candidaturas do partido. Azul: a parte do fundo eleitoral "
                   "que receberam. Linha laranja: 30%. Partidos em ordem alfabética.")
        comum.mostrar(grafico_fundo(col_c, col_f, grupo), tabela=tabela_fundo(col_c, col_f), fonte=FONTE,
                      chave=f"fundo_{col_f}")
        abaixo = partidos[partidos[col_f] < 0.30].sort_values("sg_partido")["sg_partido"].tolist()
        if abaixo:
            st.markdown(f"**Ponto de atenção:** nos repasses declarados pelos candidatos, ficaram abaixo de 30% "
                        f"{', '.join(abaixo)}.")
st.caption(
    "**Ponto de atenção não é acusação.** Esta conta usa só o fundo eleitoral que cada candidatura declarou ter "
    "recebido do partido. A conferência oficial é feita pela Justiça Eleitoral nas contas dos partidos, que incluem "
    f"gastos pagos direto pelo partido e regras que esta soma não capta. Partidos com menos de {reais(MINIMO_FUNDO)} "
    "de fundo eleitoral repassado ficam fora do gráfico: com poucos repasses, a porcentagem diz pouco."
)

# --- 3. onde se gasta ---------------------------------------------------------------------
st.header("Onde se gasta")
ordem = despesas.iloc[::-1]
fig = go.Figure(go.Bar(
    x=ordem["parte"], y=ordem["categoria"], orientation="h", marker_color=comum.SERIE, width=0.55,
    text=[f"{comum.pct(p, 0)} · {reais(v)}" for p, v in zip(ordem["parte"], ordem["valor"])], textposition="outside",
    cliponaxis=False, hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
comum.estilo(fig, altura=60 + 34 * len(ordem), legenda=False)
fig.update_xaxes(tickformat=".0%", range=[0, max(ordem["parte"]) * 1.45], showgrid=True, gridcolor=comum.GRADE)
st.markdown(f"**Parte de cada tipo de despesa no total contratado ({reais(resumo['despesas_contratadas'])})**")
st.caption("Impulsionamento de conteúdo: anúncios pagos em redes sociais e buscadores. Militância e mobilização de "
           "rua: pessoas contratadas para panfletar e fazer campanha nas ruas.")
comum.mostrar(fig, fonte=FONTE, chave="despesas", tabela=pd.DataFrame({
    "Tipo de despesa": despesas["categoria"], "Valor": despesas["valor"].map(reais),
    "Parte": despesas["parte"].map(lambda v: comum.pct(v, 1)), "Lançamentos": despesas["lancamentos"].map(comum.numero)}))

# --- 4. custo por voto --------------------------------------------------------------------
st.header("Quanto custou cada voto")
st.markdown("**Custo por voto** é o que a candidatura gastou dividido pelos votos que teve no 1º turno.")
tab = custo.pivot_table(index="cargo", columns="grupo", values=["mediana_custo_voto", "mediana_gasto", "candidatos"])
ordem_cargos = [c for c in ["Governador", "Senador", "Deputado Federal", "Deputado Estadual ou Distrital"] if c in tab.index]
tab = tab.reindex(ordem_cargos)
st.dataframe(pd.DataFrame({
    "Cargo": tab.index,
    "Custo por voto: eleitos": tab[("mediana_custo_voto", "Eleitos")].map(lambda v: f"R$ {comum.numero(v, 2)}"),
    "Custo por voto: não eleitos": tab[("mediana_custo_voto", "Não eleitos")].map(lambda v: f"R$ {comum.numero(v, 2)}"),
    "Gasto típico: eleitos": tab[("mediana_gasto", "Eleitos")].map(reais),
    "Gasto típico: não eleitos": tab[("mediana_gasto", "Não eleitos")].map(reais),
}), hide_index=True)
st.caption("Valores medianos: metade das candidaturas fica acima, metade abaixo. Presidente fica de fora: as contas "
           "do 2º turno ainda não fecharam.")

st.markdown("**Deputado Federal: parte dos candidatos eleitos em cada faixa de gasto**")
st.caption("As candidaturas foram divididas em 10 faixas do mesmo tamanho, da que gastou menos (1) à que gastou "
           "mais (10).")
fig = go.Figure(go.Bar(
    x=[f"{f}" for f in faixas["faixa"]], y=faixas["parte_eleitos"], marker_color=comum.SERIE, width=0.6,
    text=[comum.pct(v, 0) for v in faixas["parte_eleitos"]], textposition="outside", cliponaxis=False,
    customdata=[[reais(a), reais(b)] for a, b in zip(faixas["gasto_min"], faixas["gasto_max"])],
    hovertemplate="faixa %{x}: gasto de %{customdata[0]} a %{customdata[1]}<br>%{y:.0%} eleitos<extra></extra>"))
comum.estilo(fig, altura=320, legenda=False)
fig.update_yaxes(tickformat=".0%", range=[0, min(1, faixas["parte_eleitos"].max() * 1.25)])
fig.update_xaxes(title="faixa de gasto (1 = gastou menos, 10 = gastou mais)", type="category")
comum.mostrar(fig, fonte=FONTE + "; votos: resultado do 1º turno do TSE", chave="faixas", tabela=pd.DataFrame({
    "Faixa": faixas["faixa"], "Gasto de": faixas["gasto_min"].map(reais), "até": faixas["gasto_max"].map(reais),
    "Candidaturas": faixas["candidatos"].map(comum.numero), "Eleitos": faixas["eleitos"].map(comum.numero),
    "Parte eleita": faixas["parte_eleitos"].map(lambda v: comum.pct(v, 1))}))
de_baixo = int((faixas.sort_values("faixa")["parte_eleitos"].cummax() < 0.01).sum())
st.caption(
    f"Na faixa de quem mais gastou, {comum.pct(faixas['parte_eleitos'].iloc[-1], 0)} se elegeram; nas {de_baixo} "
    "faixas de baixo, menos de 1% (quase ninguém). Isso não quer dizer que o dinheiro elege: os partidos concentram o fundo em quem já "
    "tem mais chance (quem tem mandato, quem é conhecido), e gasto e voto andam juntos pelos dois lados."
)

comum.rodape("scripts/site_dinheiro.py")
