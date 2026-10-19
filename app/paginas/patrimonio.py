"""Patrimônio declarado pelos candidatos: valores típicos em 2026, tipos de bens e
a evolução, descontada a inflação, de quem concorreu mais de uma vez.

Dados: app/dados/patrimonio_*.parquet, gerados por scripts/site_candidatos.py.
"""

import unicodedata

import comum
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

FONTE = "TSE, Portal de Dados Abertos (candidatos e bens de candidatos) e resultados do 1º turno de 2026"
FONTE_IPCA = FONTE + "; IPCA do IBGE (SIDRA, tabela 1737)"
ORDEM_CARGOS = ["Presidente", "Governador", "Senador", "Deputado Federal", "Deputado Estadual ou Distrital"]
ORDEM_BENS = ["Imóveis", "Aplicações e dinheiro", "Participações em empresas", "Veículos, barcos e aviões",
              "Criptoativos", "Outros bens e direitos"]
# Três grupos, três cores validadas: eleitos em destaque, não eleitos na cor da série
# e quem ainda disputa o 2º turno em cinza (situação em aberto).
COR_GRUPO = {"Eleitos": comum.DESTAQUE, "Não eleitos": comum.SERIE, "No 2º turno": comum.MUDO}
RESSALVA = (
    "**Antes de ler:** os bens são declarados pelo próprio candidato à Justiça Eleitoral, em geral pelo valor "
    "de compra que consta no Imposto de Renda, e não pelo valor de mercado. Um imóvel comprado há 20 anos "
    "aparece pelo preço de 20 anos atrás. Diferenças entre candidatos ou entre eleições podem refletir só a "
    "forma de declarar. **Nada aqui indica irregularidade.**"
)


def titulo(texto: str, como_ler: str | None = None) -> None:
    st.markdown(f"##### {texto}")
    if como_ler:
        st.caption(f"**Como ler:** {como_ler}")


def reais(v: float) -> str:
    """1_406_588 -> 'R$ 1,4 milhão'; 147_432 -> 'R$ 147 mil'."""
    if v is None or pd.isna(v):
        return "—"
    if abs(v) >= 1e9:
        x = v / 1e9
        return f"R$ {comum.numero(x, 1)} {'bilhão' if abs(round(x, 1)) < 2 else 'bilhões'}"
    if abs(v) >= 1e6:
        x = v / 1e6
        return f"R$ {comum.numero(x, 1)} {'milhão' if abs(round(x, 1)) < 2 else 'milhões'}"
    if abs(v) >= 1e3:
        return f"R$ {comum.numero(v / 1e3)} mil"
    return f"R$ {comum.numero(v)}"


def rs(v: float) -> str:
    """reais() para texto em markdown (o "$" sozinho abriria uma fórmula)."""
    return reais(v).replace("$", "\\$")


def altura(categorias: int, series: int = 1, legenda: bool = True, espessura: int = 13) -> int:
    """Altura que deixa cada barra com ~`espessura` px (barras finas)."""
    return int((105 if legenda else 60) + categorias * series * espessura / 0.62)


def eixo_categorias(fig: go.Figure) -> None:
    fig.update_yaxes(autorange="reversed", showgrid=False, ticklabelstandoff=6)


def rotulo_zero(medianas: pd.Series) -> list[str]:
    """Escreve "R$ 0" onde a mediana é zero, para não confundir com "sem dado"."""
    return ["R$ 0" if pd.notna(m) and m == 0 else "" for m in medianas]


def variacao(v: float) -> str:
    if v is None or pd.isna(v):
        return "—"
    return ("+" if v > 0 else "−" if v < 0 else "") + comum.pct(abs(v), 0)


def quebra(texto: str, largura: int = 18) -> str:
    if len(texto) <= largura or " " not in texto:
        return texto
    linhas, atual = [], ""
    for p in texto.split():
        if atual and len(atual) + 1 + len(p) > largura:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    return "<br>".join(linhas + [atual])


def normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().upper()


# --- dados -------------------------------------------------------------------------------
por_cargo = comum.ler("patrimonio_cargo")
por_partido = comum.ler("patrimonio_partido")
tipos = comum.ler("patrimonio_tipos")
evolucao = comum.ler("patrimonio_evolucao")
pessoas = comum.ler("patrimonio_pessoas")
resumo = comum.ler("patrimonio_resumo").set_index("chave")["valor"]
MINIMO = int(resumo["minimo_grupo"])
referencia = int(resumo["ipca_referencia"])
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]
MES_REFERENCIA = f"{MESES[referencia % 100 - 1]} de {referencia // 100}"

# --- página ----------------------------------------------------------------------------------
comum.cabecalho("Patrimônio declarado",
                "Os bens que os candidatos declararam à Justiça Eleitoral em 2026 e como mudaram desde 2018.")
st.warning(RESSALVA, icon=":material/info:")

# 1. Patrimônio típico por cargo ----------------------------------------------------------------
st.header("Patrimônio típico por cargo em 2026")
todos = por_cargo[(por_cargo["cargo"] == "Todos os cargos") & (por_cargo["grupo"] == "Todos")].iloc[0]
st.markdown(
    "Usamos a **mediana**: metade dos candidatos declarou menos que esse valor e metade declarou mais. A média "
    "seria puxada por poucas declarações muito altas: o 1% de candidatos com maior patrimônio declarado soma "
    f"**{comum.pct(resumo['parcela_1pct_maiores_2026'], 0)}** de todo o valor declarado em 2026. "
    f"O patrimônio mediano de quem foi a voto em 2026 é **{rs(todos['mediana'])}**, contando quem não declarou "
    f"nenhum bem: **{comum.numero(todos['zero'])}** candidatos ({comum.pct(todos['zero'] / todos['n'], 0)}) "
    "declararam patrimônio zero."
)

titulo("Patrimônio mediano declarado por cargo: eleitos, no 2º turno e não eleitos (2026)",
       "quanto mais longa a barra, maior o patrimônio típico do grupo. Laranja: eleitos; azul: não eleitos; "
       "cinza: candidatos no 2º turno. Grupos com menos de "
       f"{MINIMO} pessoas não têm barra (ex.: os 2 candidatos a Presidente no 2º turno).")
fig = go.Figure()
for grupo in ["Eleitos", "No 2º turno", "Não eleitos"]:
    g = por_cargo[por_cargo["grupo"] == grupo].set_index("cargo").reindex(ORDEM_CARGOS)
    fig.add_bar(y=[quebra(c) for c in ORDEM_CARGOS], x=g["mediana"] / 1e3, orientation="h", name=grupo,
                marker_color=COR_GRUPO[grupo], text=rotulo_zero(g["mediana"]), textposition="outside",
                textfont=dict(color=comum.TINTA_2, size=11), cliponaxis=False,
                customdata=[[reais(m), comum.numero(n) if pd.notna(n) else "0"] for m, n in zip(g["mediana"], g["n"])],
                hovertemplate="%{y}<br>" + grupo + ": %{customdata[0]} (%{customdata[1]} pessoas)<extra></extra>")
fig.update_layout(barmode="group", bargroupgap=0.08)
fig.update_xaxes(title_text="R$ mil", tickformat=",.0f", rangemode="tozero", showgrid=True, gridcolor=comum.GRADE)
eixo_categorias(fig)
t = por_cargo.pivot_table(index="cargo", columns="grupo", values=["mediana", "n", "zero"]).reindex(
    ORDEM_CARGOS + ["Todos os cargos"])
tabela = pd.DataFrame({"Cargo": t.index})
for grupo in ["Todos", "Eleitos", "No 2º turno", "Não eleitos"]:
    tabela[f"Mediana: {grupo.lower()}"] = [reais(v) if pd.notna(n) and n >= MINIMO else "—"
                                          for v, n in zip(t[("mediana", grupo)], t[("n", grupo)])]
tabela["Candidatos"] = [comum.numero(v) for v in t[("n", "Todos")]]
tabela["Declararam zero"] = [f"{comum.numero(z)} ({comum.pct(z / n, 0)})" for z, n in zip(t[("zero", "Todos")],
                                                                                        t[("n", "Todos")])]
comum.mostrar(comum.estilo(fig, altura=altura(5, 3) + 30), tabela=tabela, fonte=FONTE, chave="pat_cargo")
dep = por_cargo.set_index(["cargo", "grupo"])
st.caption(
    "Patrimônio zero, por cargo: " + "; ".join(
        f"{c.lower()}, {comum.pct(dep.loc[(c, 'Todos'), 'zero'] / dep.loc[(c, 'Todos'), 'n'], 0)}"
        for c in ORDEM_CARGOS) + ". Quem não declarou bens pode não ter bens em seu nome ou ter optado por "
    "informar \"nada a declarar\"; os dados não distinguem os dois casos."
)

# 2. Por partido ---------------------------------------------------------------------------------
titulo("Patrimônio mediano declarado por partido: eleitos e não eleitos (2026)",
       "partidos em ordem alfabética. Laranja: eleitos; azul: não eleitos. Partidos com menos de "
       f"{MINIMO} candidatos no cargo não aparecem; grupos de eleitos com menos de {MINIMO} pessoas ficam sem "
       "barra laranja (o valor de um grupo tão pequeno seria o de poucas pessoas). \"R\\$ 0\": mais da metade do "
       "grupo não declarou bens.")
cargo_p = st.selectbox("Cargo", ["Todos os cargos", "Deputado Federal", "Deputado Estadual ou Distrital",
                                 "Senador", "Governador"], key="pat_partido_cargo")
pp = por_partido[por_partido["cargo"] == cargo_p]
partidos = sorted(pp.loc[(pp["grupo"] == "Todos") & (pp["n"] >= MINIMO), "sg_partido"], key=normalizar)
fig = go.Figure()
for grupo in ["Eleitos", "Não eleitos"]:
    g = pp[pp["grupo"] == grupo].set_index("sg_partido").reindex(partidos)
    fig.add_bar(y=partidos, x=g["mediana"] / 1e3, orientation="h", name=grupo, marker_color=COR_GRUPO[grupo],
                text=rotulo_zero(g["mediana"]), textposition="outside", textfont=dict(color=comum.TINTA_2, size=11),
                cliponaxis=False,
                customdata=[[reais(m) if pd.notna(m) else f"menos de {MINIMO} pessoas",
                             comum.numero(n) if pd.notna(n) else "0"] for m, n in zip(g["mediana"], g["n"])],
                hovertemplate="%{y}<br>" + grupo + ": %{customdata[0]} (%{customdata[1]} pessoas)<extra></extra>")
fig.update_layout(barmode="group", bargroupgap=0.08)
fig.update_xaxes(title_text="R$ mil", tickformat=",.0f", rangemode="tozero", showgrid=True, gridcolor=comum.GRADE)
eixo_categorias(fig)
t = pp.pivot_table(index="sg_partido", columns="grupo", values=["mediana", "n", "zero"]).reindex(partidos)
tabela = pd.DataFrame({
    "Partido": partidos,
    "Candidatos": [comum.numero(v) for v in t[("n", "Todos")]],
    "Mediana: todos": [reais(v) for v in t[("mediana", "Todos")]],
    "Mediana: eleitos": [reais(v) for v in t[("mediana", "Eleitos")]] if ("mediana", "Eleitos") in t else "—",
    "Eleitos": [comum.numero(v) if pd.notna(v) else "0" for v in t[("n", "Eleitos")]]
    if ("n", "Eleitos") in t else "0",
    "Mediana: não eleitos": [reais(v) for v in t[("mediana", "Não eleitos")]],
    "Declararam zero": [f"{comum.numero(z)} ({comum.pct(z / n, 0)})" for z, n in zip(t[("zero", "Todos")],
                                                                                  t[("n", "Todos")])],
})
comum.mostrar(comum.estilo(fig, altura=altura(len(partidos), 2) + 30), tabela=tabela, fonte=FONTE,
              chave="pat_partido")

# 3. Tipos de bens -----------------------------------------------------------------------------------
st.header("Do que é feito o patrimônio declarado em 2026")
st.markdown(
    "O TSE classifica os bens em cerca de 50 tipos, os mesmos do Imposto de Renda. Agrupamos em seis. "
    "Criptoativos não têm tipo próprio: foram encontrados pela descrição do bem (palavras como "
    "\"criptomoeda\", \"bitcoin\", \"BTC\", \"USDT\")."
)
tp = tipos.set_index("categoria").reindex(ORDEM_BENS)
tp["parte_valor"] = tp["valor"] / tp["valor"].sum()
tp["parte_candidatos"] = tp["candidatos_com"] / tp["candidatos_total"]
col1, col2 = st.columns(2, gap="large")
with col1:
    titulo("Parte de cada tipo no valor total declarado",
           "as barras somam 100% do valor declarado por todos os candidatos que foram a voto.")
    fig = go.Figure()
    fig.add_bar(y=[quebra(c) for c in ORDEM_BENS], x=tp["parte_valor"], orientation="h", marker_color=comum.SERIE,
                text=[comum.pct(v, 2 if v < 0.01 else 1) if v < 0.02 else "" for v in tp["parte_valor"]],
                textposition="outside",
                textfont=dict(color=comum.TINTA_2, size=11), cliponaxis=False,
                customdata=[[comum.pct(p), reais(v)] for p, v in zip(tp["parte_valor"], tp["valor"])],
                hovertemplate="%{y}<br>%{customdata[0]} do valor total (%{customdata[1]})<extra></extra>")
    fig.update_xaxes(tickformat=".0%", rangemode="tozero", showgrid=True, gridcolor=comum.GRADE)
    eixo_categorias(fig)
    tabela = pd.DataFrame({"Tipo": ORDEM_BENS, "Valor declarado": [reais(v) for v in tp["valor"]],
                           "Parte do total": [comum.pct(v) for v in tp["parte_valor"]],
                           "Bens declarados": [comum.numero(v) for v in tp["bens"]]})
    comum.mostrar(comum.estilo(fig, altura=altura(6, legenda=False, espessura=22) + 20, legenda=False), tabela=tabela,
                  fonte=FONTE, chave="pat_tipos_valor")
with col2:
    titulo("Candidatos que declararam pelo menos um bem de cada tipo",
           "% dos candidatos que foram a voto. Um candidato pode ter bens de vários tipos.")
    fig = go.Figure()
    fig.add_bar(y=[quebra(c) for c in ORDEM_BENS], x=tp["parte_candidatos"], orientation="h",
                marker_color=comum.SERIE,
                text=[comum.pct(v, 2 if v < 0.01 else 1) if v < 0.02 else "" for v in tp["parte_candidatos"]],
                textposition="outside", textfont=dict(color=comum.TINTA_2, size=11), cliponaxis=False,
                customdata=[[comum.pct(p), comum.numero(n), comum.numero(t)] for p, n, t in
                            zip(tp["parte_candidatos"], tp["candidatos_com"], tp["candidatos_total"])],
                hovertemplate="%{y}<br>%{customdata[0]} (%{customdata[1]} de %{customdata[2]})<extra></extra>")
    fig.update_xaxes(tickformat=".0%", rangemode="tozero", showgrid=True, gridcolor=comum.GRADE)
    eixo_categorias(fig)
    tabela = pd.DataFrame({"Tipo": ORDEM_BENS, "Candidatos com o tipo": [comum.numero(v) for v in tp["candidatos_com"]],
                           "% dos candidatos": [comum.pct(v) for v in tp["parte_candidatos"]]})
    comum.mostrar(comum.estilo(fig, altura=altura(6, legenda=False, espessura=22) + 20, legenda=False), tabela=tabela,
                  fonte=FONTE, chave="pat_tipos_cand")
st.caption(
    "\"Aplicações e dinheiro\": poupança, renda fixa, fundos, previdência privada (VGBL), contas bancárias e "
    "dinheiro em espécie. \"Outros bens e direitos\": créditos a receber (dinheiro emprestado a terceiros), "
    "joias e obras de arte, consórcios, direitos autorais e bens sem tipo definido. Como poucas declarações "
    "muito grandes pesam muito no valor total, o gráfico da direita mostra quão comum é cada tipo."
)

# 4. Evolução ----------------------------------------------------------------------------------------------
st.header("Como mudou o patrimônio de quem concorreu de novo")
c26 = resumo["candidatos_2026"]
st.markdown(
    "Para comparar a mesma pessoa em eleições diferentes, ligamos as candidaturas pelo **CPF**, que o TSE "
    f"publica. Dos {comum.numero(c26)} candidatos que foram a voto em 2026, "
    f"**{comum.numero(resumo['ligados_2022_2026'])}** ({comum.pct(resumo['ligados_2022_2026'] / c26, 0)}) também "
    f"foram a voto em 2022, **{comum.numero(resumo['ligados_2018_2026'])}** "
    f"({comum.pct(resumo['ligados_2018_2026'] / c26, 0)}) em 2018 e **{comum.numero(resumo['ligados_tres_anos'])}** "
    "nas três eleições. A ligação por CPF confere com o \"Histórico de candidaturas\" do TSE em "
    f"{comum.numero(resumo['historico_confirmados_2022'])} de {comum.numero(resumo['historico_pares_2022'])} pares "
    f"(2022) e {comum.numero(resumo['historico_confirmados_2018'])} de {comum.numero(resumo['historico_pares_2018'])} "
    "(2018)."
)
st.markdown(
    f"Os valores estão **corrigidos pela inflação (IPCA) para {MES_REFERENCIA}**, mês do registro das "
    f"candidaturas de 2026: R\\$ 1,00 declarado em agosto de 2018 equivale a R\\$ "
    f"{comum.numero(resumo['ipca_fator_2018'], 2)}, e em agosto de 2022, a R\\$ "
    f"{comum.numero(resumo['ipca_fator_2022'], 2)}."
)
st.info(
    "**Por que muitos patrimônios \"caem\" depois de corrigidos:** como os bens costumam ser declarados pelo "
    "valor de compra, quem declarou exatamente os mesmos bens nas duas eleições aparece com queda real igual à "
    "inflação do período. Uma variação negativa não quer dizer que a pessoa perdeu bens, e uma positiva não "
    "quer dizer que enriqueceu: pode ser compra, venda, herança, atualização de valores ou mudança na forma de "
    "declarar.",
    icon=":material/info:",
)

periodo = st.segmented_control("Comparar", ["2022 → 2026", "2018 → 2022", "2018 → 2026"], default="2022 → 2026",
                               required=True, key="pat_periodo")
ev = evolucao[evolucao["periodo"] == periodo]
antes, depois = periodo.split(" → ")
ec = ev[ev["recorte"] == "cargo"].set_index("grupo").reindex(ORDEM_CARGOS + ["Todos os cargos"])
tot = ec.loc["Todos os cargos"]
st.markdown(
    f"**{comum.numero(tot['pessoas'])} pessoas** foram a voto em {antes} e em {depois}. O patrimônio mediano "
    f"delas foi de {rs(tot['mediana_antes'])} para {rs(tot['mediana_depois'])} (valores de {MES_REFERENCIA}). "
    f"Olhando pessoa a pessoa, a variação real mediana foi de **{variacao(tot['variacao_mediana'])}**, e "
    f"{comum.pct(tot['subiu'] / tot['pessoas_com_base'], 0)} tiveram aumento real."
)
titulo(f"Patrimônio mediano das mesmas pessoas em {antes} e em {depois}, por cargo em {depois}",
       f"para cada cargo, a barra cinza é a mediana em {antes} e a azul, em {depois}, das mesmas pessoas, com "
       f"valores corrigidos para {MES_REFERENCIA}. Cargos com menos de {MINIMO} pessoas não aparecem.")
cargos_ev = [c for c in ORDEM_CARGOS if pd.notna(ec.loc[c, "mediana_depois"])]
fig = go.Figure()
for rotulo, coluna, cor in [(antes, "mediana_antes", comum.MUDO), (depois, "mediana_depois", comum.SERIE)]:
    g = ec.reindex(cargos_ev)
    fig.add_bar(y=[quebra(c) for c in cargos_ev], x=g[coluna] / 1e3, orientation="h", name=rotulo, marker_color=cor,
                customdata=[[reais(v), comum.numero(n)] for v, n in zip(g[coluna], g["pessoas"])],
                hovertemplate="%{y}<br>" + rotulo + ": %{customdata[0]} (%{customdata[1]} pessoas)<extra></extra>")
fig.update_layout(barmode="group", bargroupgap=0.08)
fig.update_xaxes(title_text=f"R$ mil de {MES_REFERENCIA}", tickformat=",.0f", rangemode="tozero", showgrid=True,
                 gridcolor=comum.GRADE)
eixo_categorias(fig)
tabela = pd.DataFrame({
    "Cargo em " + depois: ec.index,
    "Pessoas": [comum.numero(v) for v in ec["pessoas"]],
    f"Mediana {antes}": [reais(v) for v in ec["mediana_antes"]],
    f"Mediana {depois}": [reais(v) for v in ec["mediana_depois"]],
    "Variação real mediana (pessoa a pessoa)": [variacao(v) for v in ec["variacao_mediana"]],
    "Tiveram aumento real": [f"{comum.numero(s)} de {comum.numero(b)}" for s, b in
                             zip(ec["subiu"], ec["pessoas_com_base"])],
})
comum.mostrar(comum.estilo(fig, altura=altura(len(cargos_ev), 2) + 30), tabela=tabela, fonte=FONTE_IPCA,
              chave="pat_ev_cargo")

titulo(f"Variação real mediana do patrimônio, pessoa a pessoa, por partido em {depois} ({antes} → {depois})",
       "para cada pessoa, calculamos quanto o patrimônio corrigido mudou em %; a barra é a mediana dessas "
       "variações. À direita do zero, a pessoa típica do partido declarou mais; à esquerda, menos. Partidos em "
       f"ordem alfabética; só partidos com pelo menos {MINIMO} pessoas com patrimônio acima de zero na primeira "
       "eleição.")
epp = ev[(ev["recorte"] == "partido") & ev["variacao_mediana"].notna()].copy()
epp = epp.sort_values("grupo", key=lambda s: s.map(normalizar))
fig = go.Figure()
fig.add_bar(y=epp["grupo"], x=epp["variacao_mediana"], orientation="h", marker_color=comum.SERIE, name="Variação",
            customdata=[[variacao(v), comum.numero(n), reais(a), reais(d)] for v, n, a, d in
                        zip(epp["variacao_mediana"], epp["pessoas_com_base"], epp["mediana_antes"],
                            epp["mediana_depois"])],
            hovertemplate=("%{y}<br>Variação real mediana: %{customdata[0]} (%{customdata[1]} pessoas)"
                           "<br>Mediana " + antes + ": %{customdata[2]} · " + depois + ": %{customdata[3]}"
                           "<extra></extra>"))
fig.add_vline(x=0, line_color=comum.TINTA_2, line_width=1)
fig.update_xaxes(tickformat=".0%", showgrid=True, gridcolor=comum.GRADE)
eixo_categorias(fig)
tabela = pd.DataFrame({
    f"Partido em {depois}": epp["grupo"],
    "Pessoas": [comum.numero(v) for v in epp["pessoas"]],
    f"Mediana {antes}": [reais(v) for v in epp["mediana_antes"]],
    f"Mediana {depois}": [reais(v) for v in epp["mediana_depois"]],
    "Variação real mediana": [variacao(v) for v in epp["variacao_mediana"]],
    "Tiveram aumento real": [f"{comum.numero(s)} de {comum.numero(b)}" for s, b in
                             zip(epp["subiu"], epp["pessoas_com_base"])],
})
comum.mostrar(comum.estilo(fig, altura=altura(len(epp), legenda=False) + 20, legenda=False), tabela=tabela,
              fonte=FONTE_IPCA, chave="pat_ev_partido")
st.caption("Quem declarou zero na primeira eleição fica fora da variação em % (não dá para calcular aumento "
           "sobre zero), mas entra nas medianas do gráfico por cargo.")

# 5. Tabela pesquisável -----------------------------------------------------------------------------------------
st.subheader("Procure um candidato de 2026")
st.markdown(
    "Todos os candidatos que foram a voto em 2026, em ordem alfabética do nome de urna, com o patrimônio "
    f"declarado em 2018 e 2022 (quando concorreram) corrigido para {MES_REFERENCIA}. A tabela não destaca "
    "ninguém: serve para consultar."
)
busca = st.text_input("Nome de urna ou nome completo", placeholder="Digite parte do nome", key="pat_busca")
p = pessoas
if busca and busca.strip():
    termo = normalizar(busca.strip())
    p = p[p["nm_urna"].map(normalizar).str.contains(termo, regex=False)
          | p["nm_candidato"].map(normalizar).str.contains(termo, regex=False)]
var = p["patrimonio_2026"] / p["patrimonio_2022"].where(p["patrimonio_2022"] > 0) - 1
mostrar = pd.DataFrame({
    "Nome de urna": p["nm_urna"], "UF": p["uf"], "Cargo em 2026": p["cargo"], "Partido em 2026": p["sg_partido"],
    "Patrimônio 2026": p["patrimonio_2026"], "Patrimônio 2022 (corrigido)": p["patrimonio_2022"],
    "Patrimônio 2018 (corrigido)": p["patrimonio_2018"], "Variação real 2022 → 2026": var,
    "Situação em 2026": p["situacao"], "Nome completo": p["nm_candidato"],
})
st.caption(f"{comum.numero(len(mostrar))} candidatos" + (" encontrados." if busca else "."))
colunas_reais = ["Patrimônio 2018 (corrigido)", "Patrimônio 2022 (corrigido)", "Patrimônio 2026"]
estilo = mostrar.style.format(lambda v: "—" if pd.isna(v) else "R$ " + comum.numero(v), subset=colunas_reais)
estilo = estilo.format(variacao, subset=["Variação real 2022 → 2026"])
st.dataframe(estilo, hide_index=True, height=420)
st.caption("Fonte: " + FONTE_IPCA + ". \"—\": a pessoa não foi a voto naquela eleição (ou, na variação, "
           "declarou zero em 2022).")

# Método ------------------------------------------------------------------------------------------------------------
with st.expander("Como os dados foram tratados"):
    st.markdown(
        "- **Quem entra:** candidaturas a Presidente, Governador, Senador e deputado que foram a voto (estavam "
        "na urna e tiveram os votos contados como válidos). Vices e suplentes ficam de fora.\n"
        "- **Patrimônio:** soma dos valores de todos os bens declarados pelo candidato naquela eleição. Quem "
        "não declarou bens tem patrimônio zero.\n"
        "- **Eleitos:** em 2026, situação nos arquivos oficiais de resultado do 1º turno. Quem disputa o 2º "
        "turno está à parte; candidatos a deputado de estados com totalização ainda não final contam só em "
        "\"todos\".\n"
        f"- **Mediana só para grupos com pelo menos {MINIMO} pessoas:** em grupos menores o valor seria o de "
        "uma ou poucas pessoas.\n"
        "- **Mesma pessoa em anos diferentes:** ligada pelo CPF publicado pelo TSE; quando falta o CPF, por "
        "nome completo e data de nascimento. O CPF não é publicado aqui.\n"
        f"- **Inflação:** IPCA mensal (série 433 do Banco Central). Valores de cada eleição são tratados como "
        f"de agosto daquele ano (prazo do registro) e levados para {MES_REFERENCIA}.\n"
        "- **Criptoativos:** o TSE não tem um tipo próprio; contamos os bens cuja descrição cita criptomoedas "
        "(menos imóveis, veículos, joias, ações e quotas de empresas)."
    )

comum.rodape()
