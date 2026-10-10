"""Perfil dos candidatos: quem se candidatou e quem foi eleito em 2018, 2022 e
2026, comparado com a população adulta (Censo 2022).

Dados: app/dados/candidatos_*.parquet, gerados por scripts/site_candidatos.py.
"""

import comum
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

FONTE = ("TSE, Portal de Dados Abertos (candidatos 2018, 2022 e 2026) e resultados do 1º turno de 2026; "
         "IBGE, Censo 2022 (SIDRA, tabela 10061)")
FONTE_TSE = "TSE, Portal de Dados Abertos (candidatos 2018, 2022 e 2026) e resultados do 1º turno de 2026"
ANOS = [2026, 2022, 2018]
CARGOS = ["Todos os cargos", "Presidente", "Governador", "Senador", "Deputado Federal",
          "Deputado Estadual ou Distrital"]
DEPUTADOS = ["Deputado Federal", "Deputado Estadual ou Distrital"]
ORDEM = {
    "Gênero": ["Mulheres", "Homens"],
    "Cor ou raça": ["Branca", "Preta", "Parda", "Amarela", "Indígena"],
    "Faixa etária": ["18 a 29 anos", "30 a 39 anos", "40 a 49 anos", "50 a 59 anos", "60 a 69 anos",
                     "70 anos ou mais"],
    "Grau de instrução": ["Até fundamental incompleto", "Fundamental completo", "Médio completo",
                          "Superior completo"],
}
TIPOS_TITULO = ["Religioso", "Policial ou militar", "Professor(a)", "Doutor(a)", "Enfermeiro(a) ou médico(a)"]
# Três grupos, três cores validadas (daltonismo e contraste): candidatos, eleitos e,
# como referência neutra, a população.
COR_GRUPO = {"Candidatos": comum.SERIE, "Eleitos": comum.DESTAQUE, "População": comum.MUDO}
COR_ANO = {2018: comum.SEQUENCIAL[2], 2022: comum.SEQUENCIAL[4], 2026: comum.SEQUENCIAL[6]}
MINIMO = 10  # grupos menores não têm percentual mostrado (cada pessoa pesaria mais de 10 pontos)


def titulo(texto: str, como_ler: str | None = None) -> None:
    st.markdown(f"##### {texto}")
    if como_ler:
        st.caption(f"**Como ler:** {como_ler}")


def altura(categorias: int, series: int = 1, legenda: bool = True, espessura: int = 13) -> int:
    """Altura que deixa cada barra com ~`espessura` px (barras finas)."""
    return int((105 if legenda else 60) + categorias * series * espessura / 0.62)


def eixo_categorias(fig: go.Figure) -> None:
    """Categorias de cima para baixo na ordem dada, com folga entre rótulo e barra."""
    fig.update_yaxes(autorange="reversed", showgrid=False, ticklabelstandoff=6)


def quebra(texto: str, largura: int = 18) -> str:
    """Quebra rótulos longos do eixo em duas linhas (cabem melhor no celular)."""
    if len(texto) <= largura or " " not in texto:
        return texto
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        if atual and len(atual) + 1 + len(p) > largura:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    return "<br>".join(linhas + [atual])


UF_NOME = {"AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
           "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais",
           "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
           "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia",
           "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
           "TO": "Tocantins"}
UF_DE = {"AC": "do Acre", "AL": "de Alagoas", "AM": "do Amazonas", "AP": "do Amapá", "BA": "da Bahia",
         "CE": "do Ceará", "DF": "do Distrito Federal", "ES": "do Espírito Santo", "GO": "de Goiás",
         "MA": "do Maranhão", "MG": "de Minas Gerais", "MS": "de Mato Grosso do Sul", "MT": "de Mato Grosso",
         "PA": "do Pará", "PB": "da Paraíba", "PE": "de Pernambuco", "PI": "do Piauí", "PR": "do Paraná",
         "RJ": "do Rio de Janeiro", "RN": "do Rio Grande do Norte", "RO": "de Rondônia", "RR": "de Roraima",
         "RS": "do Rio Grande do Sul", "SC": "de Santa Catarina", "SE": "de Sergipe", "SP": "de São Paulo",
         "TO": "do Tocantins"}


# --- dados -------------------------------------------------------------------------
perfil = comum.ler("candidatos_perfil")
populacao = comum.ler("candidatos_populacao")
eleitos_conf = comum.ler("candidatos_eleitos")
mulheres_partido = comum.ler("candidatos_mulheres_partido")
mulheres_anos = comum.ler("candidatos_mulheres_anos")
titulos = comum.ler("candidatos_titulos")
reeleicao = comum.ler("candidatos_reeleicao")

# Estados de 2026 cuja totalização de deputados ainda não era final quando os dados foram baixados.
pendentes = eleitos_conf[(eleitos_conf["ano"] == 2026) & (eleitos_conf["vagas_aguardando"] > 0)]
UFS_PENDENTES = sorted({uf.strip() for txt in pendentes["ufs_aguardando"] for uf in txt.split(",") if uf.strip()})
ONDE_PENDENTE = " e ".join(UF_NOME.get(uf, uf) for uf in UFS_PENDENTES)      # "Amazonas"
DE_PENDENTE = " e ".join(UF_DE.get(uf, uf) for uf in UFS_PENDENTES)           # "do Amazonas"
VAGAS_PENDENTES = dict(zip(pendentes["cargo"], pendentes["vagas_aguardando"]))


def distribuicao(ano: int, cargo: str, dimensao: str) -> pd.DataFrame:
    """% de cada categoria em cada grupo (sem 'Não informado' na base)."""
    d = perfil[(perfil["ano"] == ano) & (perfil["cargo"] == cargo) & (perfil["dimensao"] == dimensao)
               & perfil["categoria"].isin(ORDEM[dimensao])]
    d = d.assign(total=d.groupby("grupo")["n"].transform("sum"))
    p = populacao[populacao["dimensao"] == dimensao]
    p = p.assign(grupo="População", n=p["pessoas"], total=p["pessoas"].sum())
    d = pd.concat([d, p[["grupo", "categoria", "n", "total"]]], ignore_index=True)
    d["pct"] = d["n"] / d["total"]
    return d


def grafico_perfil(d: pd.DataFrame, dimensao: str, grupos: list[str]) -> go.Figure:
    categorias = ORDEM[dimensao]
    fig = go.Figure()
    for grupo in grupos:
        g = d[d["grupo"] == grupo].set_index("categoria").reindex(categorias)
        texto = [f"{comum.pct(p)} ({comum.numero(n)} de {comum.numero(t)})" if pd.notna(p) else "—"
                 for p, n, t in zip(g["pct"], g["n"], g["total"])]
        fig.add_bar(y=[quebra(c) for c in categorias], x=g["pct"].fillna(0), orientation="h", name=grupo,
                    marker_color=COR_GRUPO[grupo], customdata=texto,
                    hovertemplate="%{y}<br>" + grupo + ": %{customdata}<extra></extra>")
    fig.update_layout(barmode="group", bargroupgap=0.08)
    fig.update_xaxes(tickformat=".0%", rangemode="tozero", showgrid=True, gridcolor=comum.GRADE)
    eixo_categorias(fig)
    return comum.estilo(fig, altura=altura(len(categorias), len(grupos)))


def tabela_perfil(d: pd.DataFrame, dimensao: str) -> pd.DataFrame:
    t = d.pivot_table(index="categoria", columns="grupo", values="pct").reindex(ORDEM[dimensao])
    t = t[[g for g in ["Candidatos", "Eleitos", "No 2º turno", "População"] if g in t.columns]]
    t = t.map(lambda v: comum.pct(v) if pd.notna(v) else "—")
    return t.reset_index().rename(columns={"categoria": dimensao})


def parcela(d: pd.DataFrame, grupo: str, categorias: list[str]) -> float | None:
    g = d[d["grupo"] == grupo]
    if g.empty or g["total"].iloc[0] < MINIMO:
        return None
    return g.loc[g["categoria"].isin(categorias), "n"].sum() / g["total"].iloc[0]


def frase(d: pd.DataFrame, nome: str, categorias: list[str], base_pop: str) -> str:
    partes = [f"{comum.pct(parcela(d, 'População', categorias))} da população de {base_pop}",
              f"{comum.pct(parcela(d, 'Candidatos', categorias))} dos candidatos"]
    eleitos = parcela(d, "Eleitos", categorias)
    if eleitos is not None:
        partes.append(f"{comum.pct(eleitos)} dos eleitos")
    return f"**{nome}** são " + ", ".join(partes[:-1]) + " e " + partes[-1] + "."


# --- página ----------------------------------------------------------------------------
comum.cabecalho("Perfil dos candidatos",
                "Quem se candidatou e quem foi eleito em 2018, 2022 e 2026, comparado com a população "
                "adulta do Brasil.")

st.markdown(
    "Contamos as **candidaturas que foram a voto**: estavam na urna e os votos foram contados como válidos. "
    "Ficam de fora quem desistiu, quem foi barrado e quem teve os votos anulados. Em 2026 os resultados são "
    "do 1º turno (4 de outubro); quem disputa o 2º turno (25 de outubro) aparece à parte, nem como eleito "
    "nem como não eleito."
)

# 1. Quem é eleito se parece com a população? --------------------------------------
st.header("Quem é eleito se parece com a população?")
filtro_ano, filtro_cargo = st.columns([1, 2])
with filtro_ano:
    ano = st.segmented_control("Ano", ANOS, default=2026, required=True, key="perfil_ano")
with filtro_cargo:
    cargo = st.selectbox("Cargo", CARGOS, key="perfil_cargo")

dist = {dim: distribuicao(ano, cargo, dim) for dim in ORDEM}
so_eleitos = dist["Gênero"][dist["Gênero"]["grupo"] == "Eleitos"]
n_eleitos = int(so_eleitos["total"].iloc[0]) if len(so_eleitos) else 0
grupos = ["Candidatos"] + (["Eleitos"] if n_eleitos >= MINIMO else []) + ["População"]

st.markdown(
    frase(dist["Gênero"], "Mulheres", ["Mulheres"], "18 anos ou mais") + "  \n"
    + frase(dist["Cor ou raça"], "Pessoas pretas e pardas", ["Preta", "Parda"], "18 anos ou mais")
)
if n_eleitos < MINIMO:
    if ano == 2026 and cargo == "Presidente":
        st.caption("Para Presidente em 2026 ainda não há eleito: a disputa vai ao 2º turno.")
    else:
        st.caption(f"Com {n_eleitos} eleito(s) neste cargo, não mostramos o perfil dos eleitos: "
                   f"cada pessoa pesaria mais de {100 // MINIMO} pontos no percentual.")

st.caption("**Como ler:** em cada gráfico, as barras de uma mesma cor somam 100%. Azul: candidatos; "
           "laranja: eleitos; cinza: população. Se a barra laranja de uma categoria é mais curta que a "
           "cinza, essa categoria é proporcionalmente menor entre os eleitos do que na população.")

for linha in [("Gênero", "Cor ou raça"), ("Faixa etária", "Grau de instrução")]:
    colunas = st.columns(2, gap="large")
    for coluna, dimensao in zip(colunas, linha):
        with coluna:
            base = "25 anos ou mais" if dimensao == "Grau de instrução" else "18 anos ou mais"
            titulo(f"{dimensao}: candidatos, eleitos e população ({ano}, {cargo.lower()})")
            comum.mostrar(grafico_perfil(dist[dimensao], dimensao, grupos),
                          tabela=tabela_perfil(dist[dimensao], dimensao),
                          fonte=f"{FONTE}. População de {base}.", chave=f"perfil_{dimensao}")

notas = ["Idade completa no dia do 1º turno. Grau de instrução nos mesmos grupos do IBGE: cada nível inclui "
         "quem começou o seguinte e não terminou (ex.: \"médio completo\" inclui superior incompleto). Para "
         "instrução, a comparação é com a população de 25 anos ou mais, que em geral já terminou os estudos."]
if ano == 2026:
    seg = perfil[(perfil["ano"] == 2026) & (perfil["grupo"] == "No 2º turno") & (perfil["dimensao"] == "Gênero")
                 & (perfil["cargo"].isin(["Todos os cargos"] if cargo == "Todos os cargos" else [cargo]))]
    if not seg.empty:
        mulheres = int(seg.loc[seg["categoria"] == "Mulheres", "n"].sum())
        notas.append(f"No 2º turno de 2026: {comum.numero(seg['n'].sum())} candidatos, dos quais "
                     f"{comum.numero(mulheres)} mulheres. O perfil completo deles está na tabela de cada gráfico "
                     f"(coluna \"No 2º turno\").")
    if cargo in ("Todos os cargos", *DEPUTADOS) and UFS_PENDENTES:
        faltam = " e ".join(f"{comum.numero(v)} vagas de {c.lower()}" for c, v in VAGAS_PENDENTES.items())
        notas.append(f"{ONDE_PENDENTE}: a totalização para deputado ainda não era final quando os dados foram "
                     f"baixados. Os candidatos contam entre os candidatos, mas não entre os eleitos "
                     f"(faltam {faltam}).")
if ano == 2018 and cargo in ("Todos os cargos", "Senador"):
    notas.append("Senado em 2018: 53 eleitos, e não 54. Em Mato Grosso, a candidata eleita teve o diploma "
                 "cassado depois da eleição, os votos foram anulados e a vaga foi preenchida numa eleição "
                 "suplementar, que não entra nesta análise.")
st.caption("  \n".join(notas))

# 2. Mulheres ---------------------------------------------------------------------------
st.header("Mulheres nas candidaturas e entre os eleitos")
st.markdown(
    "A lei exige que cada partido ou federação tenha **pelo menos 30% e no máximo 70%** de candidaturas de "
    "cada sexo nas eleições para deputado (Lei 9.504/1997, art. 10). Na prática, a regra garante um mínimo "
    "de candidatas mulheres. Não existe cota para eleitas."
)
cargo_m = st.segmented_control("Cargo", DEPUTADOS, default="Deputado Federal", required=True, key="mulheres_cargo")

titulo(f"Mulheres entre candidatos e entre eleitos, {cargo_m.lower()}: 2018, 2022 e 2026",
       "linha azul: % de mulheres entre os candidatos que foram a voto; laranja: % de mulheres entre os "
       "eleitos. A linha pontilhada marca 30%, o mínimo da cota (que vale só para as candidaturas).")
m = mulheres_anos[mulheres_anos["cargo"] == cargo_m].sort_values("ano")
m = m.assign(pct_cand=m["candidatas"] / m["candidatos"], pct_eleitas=m["eleitas"] / m["eleitos"])
fig = go.Figure()
for nome, col, num, den, cor in [("Candidatos", "pct_cand", "candidatas", "candidatos", comum.SERIE),
                                 ("Eleitos", "pct_eleitas", "eleitas", "eleitos", comum.DESTAQUE)]:
    fig.add_scatter(x=m["ano"].astype(str), y=m[col], name=nome, mode="lines+markers",
                    line=dict(color=cor, width=2.5), marker=dict(size=9, color=cor, line=dict(width=2, color="white")),
                    customdata=[f"{comum.pct(p)} ({comum.numero(a)} de {comum.numero(b)})"
                                for p, a, b in zip(m[col], m[num], m[den])],
                    hovertemplate="%{x} · " + nome.lower() + ": %{customdata}<extra></extra>")
fig.add_hline(y=0.3, line_color=comum.MUDO, line_width=1, line_dash="dot",
              annotation_text="cota: 30% das candidaturas", annotation_position="bottom right",
              annotation_font=dict(color=comum.TINTA_2, size=12))
fig.update_yaxes(tickformat=".0%", range=[0, max(0.45, m[["pct_cand", "pct_eleitas"]].max().max() + 0.05)])
fig.update_xaxes(type="category", showgrid=False)
tabela = pd.DataFrame({
    "Ano": m["ano"].astype(str),
    "Candidatas": [comum.numero(v) for v in m["candidatas"]],
    "Candidatos (total)": [comum.numero(v) for v in m["candidatos"]],
    "% mulheres entre candidatos": [comum.pct(v) for v in m["pct_cand"]],
    "Eleitas": [comum.numero(v) for v in m["eleitas"]],
    "Eleitos (total)": [comum.numero(v) for v in m["eleitos"]],
    "% mulheres entre eleitos": [comum.pct(v) for v in m["pct_eleitas"]],
})
comum.mostrar(comum.estilo(fig, altura=320), tabela=tabela, fonte=FONTE_TSE, chave="mulheres_anos")
ult = m[m["ano"] == 2026].iloc[0]
pri = m[m["ano"] == 2018].iloc[0]
st.markdown(
    f"Em 2026, {comum.pct(ult['pct_cand'])} dos candidatos a {cargo_m.lower()} que foram a voto eram mulheres, "
    f"e {comum.pct(ult['pct_eleitas'])} dos eleitos ({comum.numero(ult['eleitas'])} de "
    f"{comum.numero(ult['eleitos'])}). Em 2018, eram {comum.pct(pri['pct_cand'])} e "
    f"{comum.pct(pri['pct_eleitas'])}."
)

titulo(f"Mulheres entre os pedidos de registro por partido ou federação, {cargo_m.lower()} (2026)",
       "cada barra é a % de mulheres entre todas as candidaturas que o partido ou federação registrou no "
       "Brasil inteiro. A linha marca 30%. Partidos em ordem alfabética; nomes com barra (ex.: PSOL/REDE) são "
       "federações.")
mp = mulheres_partido[mulheres_partido["cargo"] == cargo_m].copy()
mp = mp.assign(pct=mp["registros_mulheres"] / mp["registros"],
               pct_voto=mp["candidatas"] / mp["candidatos"].where(mp["candidatos"] > 0))
mp = mp.sort_values("agremiacao", key=lambda s: s.str.upper())
fig = go.Figure()
fig.add_bar(y=mp["agremiacao"].str.replace(" (federação)", "", regex=False), x=mp["pct"], orientation="h",
            marker_color=comum.SERIE, name="Mulheres",
            customdata=[[comum.pct(p), comum.numero(a), comum.numero(b),
                         comum.pct(v) if pd.notna(v) else "—", comum.numero(e), comum.numero(t)]
                        for p, a, b, v, e, t in zip(mp["pct"], mp["registros_mulheres"], mp["registros"],
                                                    mp["pct_voto"], mp["eleitas"], mp["eleitos"])],
            hovertemplate=("<b>%{y}</b><br>Pedidos de registro: %{customdata[0]} mulheres "
                           "(%{customdata[1]} de %{customdata[2]})<br>Entre quem foi a voto: %{customdata[3]}"
                           "<br>Eleitas: %{customdata[4]} de %{customdata[5]} eleitos<extra></extra>"))
fig.add_vline(x=0.3, line_color=comum.TINTA_2, line_width=1, line_dash="dot", annotation_text="30%",
              annotation_position="top", annotation_font=dict(color=comum.TINTA_2, size=12))
fig.update_xaxes(tickformat=".0%", range=[0, max(0.6, mp["pct"].max() + 0.05)], showgrid=True,
                 gridcolor=comum.GRADE)
eixo_categorias(fig)
tabela = pd.DataFrame({
    "Partido ou federação": mp["agremiacao"],
    "Pedidos de registro": [comum.numero(v) for v in mp["registros"]],
    "Mulheres (registro)": [comum.numero(v) for v in mp["registros_mulheres"]],
    "% mulheres (registro)": [comum.pct(v) for v in mp["pct"]],
    "Foram a voto": [comum.numero(v) for v in mp["candidatos"]],
    "% mulheres (foram a voto)": [comum.pct(v) if pd.notna(v) else "—" for v in mp["pct_voto"]],
    "Eleitos": [comum.numero(v) for v in mp["eleitos"]],
    "Eleitas": [comum.numero(v) for v in mp["eleitas"]],
})
comum.mostrar(comum.estilo(fig, altura=altura(len(mp), legenda=False) + 20, legenda=False), tabela=tabela,
              fonte=FONTE_TSE, chave="mulheres_partido")
st.caption(
    "**Simplificação:** a regra vale para a lista de cada partido ou federação em cada estado, no momento do "
    "pedido de registro. Aqui somamos as listas do Brasil inteiro: um partido acima de 30% no total pode ter "
    "ficado abaixo em algum estado, e vice-versa. Por isso o gráfico não diz se a regra foi cumprida. Partidos "
    "de uma federação aparecem juntos, porque a federação monta uma lista só."
    + (f" Os números de eleitos não incluem os deputados {DE_PENDENTE} (totalização ainda não final)."
       if UFS_PENDENTES else "")
)

# 3. Títulos no nome de urna -------------------------------------------------------------
st.header("Títulos e profissões no nome de urna")
st.markdown(
    "Muitos candidatos põem um título ou profissão no nome que aparece na urna: \"Pastor\", \"Sargento\", "
    "\"Professora\", \"Dr.\". Contamos os nomes de urna que **começam** com uma dessas palavras (ou "
    "abreviações como PR, SGT, PROF), entre os candidatos a deputado federal, estadual e distrital que foram "
    "a voto."
)
with st.expander("Quais palavras entram em cada tipo"):
    st.markdown(
        "- **Religioso:** pastor(a), PR, PRA, bispo(a), padre, irmão, irmã, missionário(a), apóstolo(a), "
        "presbítero, diácono, diaconisa, evangelista, frei, reverendo.\n"
        "- **Policial ou militar:** sargento, subtenente, capitão, coronel, cabo, soldado, tenente, major, "
        "general, brigadeiro, almirante, comandante, delegado(a), policial, PM, inspetor(a), investigador(a), "
        "escrivão, perito(a), bombeiro(a), guarda (e abreviações como SGT, CEL, TEN, CB, SD, DEL).\n"
        "- **Professor(a):** professor(a), PROF, PROFA, PROFE.\n"
        "- **Doutor(a):** DR, DRA, doutor(a).\n"
        "- **Enfermeiro(a) ou médico(a):** enfermeiro(a), médico(a).\n\n"
        "Só vale a primeira palavra: \"Bispo\" no fim do nome costuma ser sobrenome. O título no nome não diz "
        "se a pessoa exerce mesmo a profissão."
    )

t = titulos.groupby(["ano", "titulo"], as_index=False)[["candidatos", "com_resultado", "eleitos"]].sum()
t["total_ano"] = t.groupby("ano")["candidatos"].transform("sum")
t["pct_uso"] = t["candidatos"] / t["total_ano"]

titulo("Candidatos a deputado com título no nome de urna, por tipo (% dos candidatos de cada ano)",
       "cada cor é um ano, do mais claro (2018) ao mais escuro (2026).")
fig = go.Figure()
for a in [2018, 2022, 2026]:
    g = t[t["ano"] == a].set_index("titulo").reindex(TIPOS_TITULO)
    fig.add_bar(y=[quebra(x, 16) for x in TIPOS_TITULO], x=g["pct_uso"], orientation="h", name=str(a),
                marker_color=COR_ANO[a],
                customdata=[f"{comum.pct(p)} ({comum.numero(n)} de {comum.numero(tt)})"
                            for p, n, tt in zip(g["pct_uso"], g["candidatos"], g["total_ano"])],
                hovertemplate="%{y}<br>" + str(a) + ": %{customdata}<extra></extra>")
fig.update_layout(barmode="group", bargroupgap=0.08)
fig.update_xaxes(tickformat=".1%", rangemode="tozero", showgrid=True, gridcolor=comum.GRADE)
eixo_categorias(fig)
uso = t.pivot_table(index="titulo", columns="ano", values="candidatos").reindex(TIPOS_TITULO + ["Sem título"])
tabela = pd.DataFrame({"Tipo": uso.index})
for a in [2018, 2022, 2026]:
    total = t.loc[t["ano"] == a, "candidatos"].sum()
    tabela[f"{a}"] = [f"{comum.numero(v)} ({comum.pct(v / total)})" for v in uso[a]]
comum.mostrar(comum.estilo(fig, altura=altura(len(TIPOS_TITULO), 3)), tabela=tabela, fonte=FONTE_TSE,
              chave="titulos_uso")
com_titulo = t[t["titulo"] != "Sem título"].groupby("ano")[["candidatos"]].sum()
com_titulo["pct"] = com_titulo["candidatos"] / t.groupby("ano")["candidatos"].sum()
st.markdown(
    "Somando todos os tipos, usaram título " + ", ".join(
        f"{comum.pct(com_titulo.loc[a, 'pct'])} dos candidatos em {a}" for a in [2018, 2022]) +
    f" e {comum.pct(com_titulo.loc[2026, 'pct'])} em 2026."
)

ano_t = st.segmented_control("Ano", ANOS, default=2026, required=True, key="titulos_ano")
titulo(f"Quantos foram eleitos, por tipo de título no nome de urna: deputados, {ano_t}",
       "cada barra é a % de eleitos entre os candidatos daquele grupo. A barra cinza é a referência: candidatos "
       "sem título no nome.")
g = t[t["ano"] == ano_t].set_index("titulo").reindex(TIPOS_TITULO + ["Sem título"])
g["taxa"] = g["eleitos"] / g["com_resultado"]
fig = go.Figure()
fig.add_bar(y=[quebra(x, 16) for x in g.index], x=g["taxa"], orientation="h", name="Eleitos",
            marker_color=[comum.SERIE] * len(TIPOS_TITULO) + [comum.MUDO],
            text=["nenhum eleito" if e == 0 else "" for e in g["eleitos"]], textposition="outside",
            textfont=dict(color=comum.TINTA_2, size=11), cliponaxis=False,
            customdata=[f"{comum.pct(p)} ({comum.numero(e)} eleitos de {comum.numero(c)} candidatos)"
                        for p, e, c in zip(g["taxa"], g["eleitos"], g["com_resultado"])],
            hovertemplate="%{y}<br>%{customdata}<extra></extra>")
fig.update_xaxes(tickformat=".0%", rangemode="tozero", showgrid=True, gridcolor=comum.GRADE)
eixo_categorias(fig)
tabela = pd.DataFrame({
    "Tipo": g.index,
    "Candidatos": [comum.numero(v) for v in g["com_resultado"]],
    "Eleitos": [comum.numero(v) for v in g["eleitos"]],
    "% eleitos": [comum.pct(v) for v in g["taxa"]],
})
comum.mostrar(comum.estilo(fig, altura=altura(len(g), legenda=False, espessura=22) + 30, legenda=False),
              tabela=tabela, fonte=FONTE_TSE, chave="titulos_taxa")
st.info(
    "**Correlação, não causa.** Quem usa um título pode ser diferente dos demais candidatos em muitas outras "
    "coisas: carreira, eleitores que já o conhecem, apoio do partido, dinheiro de campanha. Uma taxa de eleição "
    "maior ou menor num grupo não mostra que o título no nome ajuda ou atrapalha a eleger."
    + (f" Em 2026, os candidatos {DE_PENDENTE} ficam fora desta conta (totalização ainda não final)."
       if ano_t == 2026 and UFS_PENDENTES else ""),
    icon=":material/info:",
)

# 4. Reeleição ---------------------------------------------------------------------------
st.header("Reeleição de deputados federais")
st.markdown("O que aconteceu, na eleição seguinte, com os 513 deputados federais eleitos. A mesma pessoa é "
            "encontrada nas duas eleições pelo CPF.")
r = reeleicao.pivot_table(index="periodo", columns="indicador", values="n")
for periodo in ["2022 → 2026", "2018 → 2022"]:
    x = r.loc[periodo]
    antes, depois = periodo.split(" → ")
    decididos = x["reeleitos"] + x["nao_reeleitos"]
    st.markdown(f"**Eleitos em {antes}, na eleição de {depois}**")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        comum.cartao("Tentaram de novo", comum.numero(x["concorreram_de_novo"]),
                     f"de {comum.numero(x['eleitos_antes'])} eleitos em {antes}")
    with c2:
        comum.cartao("Reeleitos", comum.numero(x["reeleitos"]))
    with c3:
        comum.cartao("Taxa de reeleição", comum.pct(x["reeleitos"] / decididos),
                     "entre os que tentaram de novo")
    with c4:
        comum.cartao("Concorreram a outro cargo", comum.numero(x["concorreram_a_outro_cargo"]))
    extra = (f" Outros {comum.numero(x['aguardando'])} tentaram de novo em estado onde a totalização ainda não "
             f"era final ({ONDE_PENDENTE}) e ficam fora da taxa." if x["aguardando"] else "")
    st.caption(
        f"Dos {comum.numero(x['eleitos_depois'])} deputados federais eleitos em {depois}, "
        f"{comum.numero(x['eleitos_depois_que_ja_eram'])} ({comum.pct(x['eleitos_depois_que_ja_eram'] / x['eleitos_depois'])}) "
        f"também tinham sido eleitos em {antes}." + extra
        + (" Quem assumiu como suplente durante o mandato não conta como eleito." if periodo == "2022 → 2026" else "")
    )

# Método ------------------------------------------------------------------------------------
todos_anos = mulheres_anos[mulheres_anos["cargo"] == "Todos os cargos"].set_index("ano")
reg, cand = todos_anos["registros"], todos_anos["candidatos"]
with st.expander("Como os dados foram tratados e conferidos"):
    st.markdown(
        "- **Quem conta como candidato:** candidaturas a Presidente, Governador, Senador e deputado (federal, "
        "estadual e distrital) que estavam na urna e tiveram os votos contados como válidos (campo "
        "\"destinação dos votos\" do TSE). Vices e suplentes ficam de fora. Quando uma candidatura de 2026 foi "
        "substituída depois de a urna ser preparada (o substituto herda o número e os votos), conta só o "
        "substituto.\n"
        "- **Eleitos em 2018 e 2022:** situação final da totalização do TSE (eleito, eleito por quociente "
        "partidário, eleito por média). Quem foi ao 2º turno conta pelo resultado do 2º turno.\n"
        "- **Eleitos em 2026:** situação de cada candidato nos arquivos oficiais de resultado do 1º turno, "
        "ligada à candidatura pelo número sequencial do TSE. Bate, candidato a candidato, com a situação do "
        "cadastro de candidatos publicado em 9 de outubro.\n"
        "- **População:** Censo 2022 do IBGE (tabela 10061 do SIDRA): pessoas de 18 anos ou mais para gênero, "
        "cor ou raça e idade; 25 anos ou mais para instrução. O Censo pergunta o sexo; o TSE registra o "
        "gênero declarado pelo candidato.\n"
        "- **Não informado:** candidatos sem a informação (menos de 0,5% em cada ano) ficam fora dos percentuais.\n"
        f"- **Menos candidaturas em 2026:** {comum.numero(reg[2026])} pedidos de registro para estes cargos, contra "
        f"{comum.numero(reg[2022])} em 2022 e {comum.numero(reg[2018])} em 2018 (foram a voto "
        f"{comum.numero(cand[2026])}, {comum.numero(cand[2022])} e {comum.numero(cand[2018])}). A queda está no "
        "próprio cadastro do TSE e se concentra nos deputados: há menos partidos e mais federações, cada "
        "partido ou federação apresenta uma lista por estado e cada lista tem um número máximo de candidatos."
    )
    conf = eleitos_conf.copy()
    st.markdown("**Conferência: eleitos por cargo e vagas em disputa**")
    st.dataframe(pd.DataFrame({
        "Ano": conf["ano"].astype(str), "Cargo": conf["cargo"],
        "Foram a voto": [comum.numero(v) for v in conf["candidatos"]],
        "Vagas": [comum.numero(v) for v in conf["vagas"]],
        "Eleitos": [comum.numero(v) for v in conf["eleitos"]],
        "No 2º turno": [comum.numero(v) for v in conf["no_2o_turno"]],
        "Vagas aguardando totalização": [comum.numero(v) if v else "" for v in conf["vagas_aguardando"]],
    }), hide_index=True)
    gov = conf[(conf["ano"] == 2026) & (conf["cargo"] == "Governador")].iloc[0]
    st.caption("Senado: 2 vagas por estado em 2018 e 2026, 1 em 2022. Deputado estadual ou distrital: 1.035 "
               f"estaduais e 24 distritais. Governador em 2026: {comum.numero(gov['eleitos'])} eleitos no 1º turno "
               f"e {comum.numero(gov['no_2o_turno'] // 2)} estados com 2º turno "
               f"({comum.numero(gov['no_2o_turno'])} candidatos).")

comum.rodape()
