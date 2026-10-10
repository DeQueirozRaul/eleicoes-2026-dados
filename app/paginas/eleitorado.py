"""Página "Eleitorado": quem pode votar em 2026 (idade, gênero e escolaridade),
o voto facultativo de jovens e idosos, os municípios com mais eleitores do que
habitantes e a abstenção por perfil.

Lê só os arquivos pequenos gerados por scripts/site_eleitorado.py.
"""

import comum
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

FONTE_PERFIL = "TSE, Portal de Dados Abertos, perfil do eleitorado (cadastro fechado para cada eleição)"
FONTE_ABSTENCAO = "TSE, Portal de Dados Abertos, perfil do comparecimento e da abstenção"
FONTE_IBGE = "IBGE, estimativa da população (SIDRA, tabela 6579)"

NOMES = {
    "BR": "Brasil", "ZZ": "Exterior",
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais",
    "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia",
    "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
    "TO": "Tocantins",
}
# Dois grupos na mesma figura (sempre com legenda): mulheres e homens.
COR_GENERO = {"Mulheres": comum.SERIE, "Homens": comum.DESTAQUE}


# --- ajudantes ----------------------------------------------------------------
def nome(sigla: str) -> str:
    return NOMES.get(sigla, sigla)


def rotulo_local(sigla: str) -> str:
    """Texto do seletor: 'Brasil', 'Acre (AC)', 'Exterior'."""
    if sigla in ("BR", "ZZ") or sigla not in NOMES:
        return nome(sigla)
    return f"{nome(sigla)} ({sigla})"


def no_local(sigla: str) -> str:
    """'no Brasil', 'em São Paulo', 'no exterior' (para frases)."""
    if sigla == "BR":
        return "no Brasil"
    if sigla == "ZZ":
        return "no exterior"
    return f"em {nome(sigla)} ({sigla})"


def grande(x: float) -> str:
    """158745463 -> '158,7 milhões'; 1634244 -> '1,6 milhão'; 606603 -> '606,6 mil'; 950 -> '950'."""
    if x >= 1e6:
        valor = comum.numero(x / 1e6, 1)
        return f"{valor} {'milhão' if valor.startswith('1,') else 'milhões'}"
    if x >= 1e4:
        return f"{comum.numero(x / 1e3, 1)} mil"
    return comum.numero(x)


def idade_texto(faixa: str) -> str:
    """'16 a 19' -> '16 a 19 anos'; '90 ou mais' -> '90 anos ou mais'; '16 anos' fica igual."""
    if faixa.endswith("anos"):
        return faixa
    if faixa.endswith("ou mais"):
        return faixa.replace(" ou mais", " anos ou mais")
    return f"{faixa} anos"


def data_br(valor) -> str:
    return pd.Timestamp(valor).strftime("%d/%m/%Y")


def passo_bonito(maximo: float, marcas: int = 3) -> float:
    """Intervalo 'redondo' entre marcas do eixo (1, 2, 2,5 ou 5 vezes uma potência de 10)."""
    bruto = maximo / marcas
    potencia = 10 ** int(f"{bruto:e}".split("e")[1])
    for fator in (1, 2, 2.5, 5, 10):
        if fator * potencia >= bruto:
            return fator * potencia
    return 10 * potencia


def eixo_porcentagem(fig: go.Figure, maximo: float, eixo: str = "x", simetrico: bool = False,
                     marcas_desejadas: int = 4) -> None:
    """Marcas do eixo em % (valores em pontos percentuais, ex.: 5 = 5%)."""
    passo = passo_bonito(maximo, marcas_desejadas)
    marcas = [passo * i for i in range(int(maximo / passo) + 2)]
    valores = ([-m for m in reversed(marcas[1:])] if simetrico else []) + marcas
    textos = [f"{comum.numero(abs(v), 1 if passo < 1 else 0)}%" for v in valores]
    limite = 1.03 * max(marcas[-1], maximo)
    faixa = [-limite, limite] if simetrico else [0, limite]
    getattr(fig, f"update_{eixo}axes")(tickvals=valores, ticktext=textos, range=faixa)


def barras_horizontais(rotulos, valores, cores, textos_hover, altura=None) -> go.Figure:
    """Barras horizontais de uma série, de cima para baixo na ordem recebida."""
    rotulos = list(rotulos)
    fig = go.Figure(go.Bar(
        y=rotulos, x=list(valores), orientation="h", marker_color=cores, showlegend=False,
        customdata=list(textos_hover), hovertemplate="%{customdata}<extra></extra>"))
    comum.estilo(fig, altura=altura or max(240, 26 * len(rotulos) + 60), legenda=False)
    fig.update_yaxes(autorange="reversed", showgrid=False, ticklabelstandoff=6)
    fig.update_xaxes(showgrid=True, gridcolor=comum.GRADE)
    fig.update_layout(bargap=0.3)
    return fig


def legenda_manual(fig: go.Figure, itens: dict[str, str]) -> None:
    """Itens de legenda para cores aplicadas dentro de uma mesma série de barras."""
    for rotulo, cor in itens.items():
        fig.add_bar(x=[None], y=[None], name=rotulo, marker_color=cor, showlegend=True, hoverinfo="skip")
    fig.update_layout(showlegend=True, barmode="overlay", margin=dict(t=40))


# --- dados --------------------------------------------------------------------
if not comum.existe("eleitorado_locais"):
    comum.cabecalho("Eleitorado")
    st.info("Os dados desta página ainda não foram gerados: rode `python scripts/site_eleitorado.py`.",
            icon=":material/info:")
    comum.rodape()
    st.stop()

locais = comum.ler("eleitorado_locais")
piramide = comum.ler("eleitorado_piramide")
municipios = comum.ler("eleitorado_municipios")
abstencao = comum.ler("eleitorado_abstencao")
evolucao = comum.ler("eleitorado_evolucao")
conferencia = comum.ler("eleitorado_conferencia")
censo = comum.ler("eleitorado_censo_idades").set_index("categoria")

ANO = int(locais["ano"].max())
ANTERIOR = int(sorted(locais["ano"].unique())[-2])
atual = locais[locais["ano"] == ANO].set_index("local")
data_cadastro = data_br(atual.loc["BR", "dt_geracao"])

comum.cabecalho(
    "Eleitorado",
    f"Quem pode votar em {ANO}: idade, gênero e escolaridade dos eleitores e o que mudou desde "
    f"{int(locais['ano'].min())}.",
)

# --- seletor e cartões ---------------------------------------------------------
opcoes = ["BR"] + sorted([s for s in atual.index if s not in ("BR", "ZZ")], key=nome) + ["ZZ"]
local = st.selectbox("Lugar", opcoes, format_func=rotulo_local,
                     help="Muda os cartões, a pirâmide e o gráfico das eleições anteriores.")
linha = atual.loc[local]
antes = locais[(locais["ano"] == ANTERIOR) & (locais["local"] == local)].iloc[0]
total = linha["qt_eleitores"]

c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
diferenca = total - antes["qt_eleitores"]
with c1:
    comum.cartao(f"Eleitores em {ANO}", grande(total),
                 f"{'+' if diferenca >= 0 else '−'}{grande(abs(diferenca))} desde {ANTERIOR}")
with c2:
    comum.cartao("Mulheres", comum.pct(linha["qt_mulheres"] / total),
                 f"{grande(linha['qt_mulheres'])} de eleitoras", cor=COR_GENERO["Mulheres"])
with c3:
    comum.cartao("Com 16 ou 17 anos", grande(linha["qt_16_17"]),
                 f"{comum.pct(linha['qt_16_17'] / total)} do eleitorado; voto facultativo")
with c4:
    comum.cartao("Com 70 anos ou mais", grande(linha["qt_70_mais"]),
                 f"{comum.pct(linha['qt_70_mais'] / total)} do eleitorado; voto facultativo")
st.caption(f"Cadastro eleitoral fechado para a eleição de {ANO} (arquivo do TSE gerado em {data_cadastro}). "
           "A idade é a que o eleitor tem no dia da eleição.")

# --- 1. pirâmide ---------------------------------------------------------------
st.subheader(f"Idade e gênero dos eleitores {no_local(local)}")
st.caption("Como ler: cada barra é uma faixa de 5 anos de idade, com as mulheres à direita e os homens à "
           "esquerda. Quanto mais comprida a barra, maior a parte do eleitorado naquela faixa. A primeira faixa "
           "tem só 4 idades (16 a 19 anos), porque o voto começa aos 16."
           + (" O traço preto mostra o Brasil, para comparar." if local != "BR" else ""))

dados = piramide[piramide["local"] == local].copy()
dados["pct"] = 100 * dados["qt_eleitores"] / total
brasil = piramide[piramide["local"] == "BR"].copy()
brasil["pct"] = 100 * brasil["qt_eleitores"] / atual.loc["BR", "qt_eleitores"]
ordem_faixas = dados.sort_values("ordem")["faixa"].unique().tolist()

fig = go.Figure()
for genero, sinal in [("Homens", -1), ("Mulheres", 1)]:
    d = dados[dados["genero"] == genero].sort_values("ordem")
    hover = [f"<b>{genero}, {idade_texto(f)}</b><br>{comum.numero(q)} eleitores<br>{comum.pct(p / 100)} do eleitorado"
             for f, q, p in zip(d["faixa"], d["qt_eleitores"], d["pct"])]
    fig.add_bar(y=d["faixa"], x=sinal * d["pct"], orientation="h", name=genero, marker_color=COR_GENERO[genero],
                customdata=hover, hovertemplate="%{customdata}<extra></extra>")
    if local != "BR":
        b = brasil[brasil["genero"] == genero].sort_values("ordem")
        fig.add_scatter(y=b["faixa"], x=sinal * b["pct"], mode="markers", name="Brasil",
                        marker=dict(symbol="line-ns", size=14, line=dict(width=2, color=comum.TINTA)),
                        showlegend=genero == "Homens", legendgroup="brasil",
                        customdata=[f"Brasil: {comum.pct(p / 100)}" for p in b["pct"]],
                        hovertemplate="%{customdata}<extra></extra>")
comum.estilo(fig, altura=520)
fig.update_layout(barmode="relative", bargap=0.2, legend=dict(traceorder="normal"))
fig.update_yaxes(categoryorder="array", categoryarray=ordem_faixas, showgrid=False, ticklabelstandoff=6)
fig.update_xaxes(showgrid=True, gridcolor=comum.GRADE, zeroline=True, zerolinecolor=comum.EIXO,
                 title="% do eleitorado")
eixo_porcentagem(fig, max(dados["pct"].max(), brasil["pct"].max() if local != "BR" else 0), simetrico=True)

tabela = dados.pivot_table(index=["ordem", "faixa"], columns="genero", values="qt_eleitores").reset_index()
tabela = pd.DataFrame({
    "Idade": tabela["faixa"].map(idade_texto),
    "Mulheres": tabela["Mulheres"].map(comum.numero),
    "Homens": tabela["Homens"].map(comum.numero),
    "% do eleitorado (mulheres)": (tabela["Mulheres"] / total).map(comum.pct),
    "% do eleitorado (homens)": (tabela["Homens"] / total).map(comum.pct),
})
comum.mostrar(fig, tabela=tabela, fonte=FONTE_PERFIL, chave="piramide")

centenarios = censo.loc["100 anos ou mais"]
st.markdown(
    f"**Ponto de atenção: eleitores com 100 anos ou mais.** O cadastro de {ANO} tem "
    f"{comum.numero(centenarios['qt_eleitores_2026'])} eleitores com 100 anos ou mais. O Censo 2022 contou "
    f"{comum.numero(centenarios['populacao_censo_2022'])} pessoas dessa idade no Brasil inteiro, e o cadastro de "
    f"2022 tinha {comum.numero(centenarios['qt_eleitores_2022'])}. Uma explicação conhecida: o título só é "
    "cancelado quando o óbito é comunicado à Justiça Eleitoral, então parte desses registros pode ser de pessoas "
    "que já morreram. Isso aparece na abstenção dessas idades (veja abaixo). É um ponto de atenção conhecido do "
    "cadastro, não uma acusação."
)
st.caption("Fontes: TSE, perfil do eleitorado; IBGE, Censo 2022 (SIDRA, tabela 9514).")

# --- 2. voto facultativo ---------------------------------------------------------
st.subheader("Voto facultativo: jovens de 16 e 17 anos e eleitores de 70 anos ou mais")
st.markdown(
    "Votar é obrigatório dos 18 aos 69 anos. Para quem tem 16 ou 17 anos, 70 anos ou mais ou não sabe ler "
    "e escrever, é opcional. Os jovens de 16 e 17 anos só entram no eleitorado se pedirem o título."
)
grupo = st.segmented_control("Grupo", ["16 e 17 anos", "70 anos ou mais"], default="16 e 17 anos",
                             required=True, key="grupo_facultativo")
coluna = "qt_16_17" if grupo == "16 e 17 anos" else "qt_70_mais"

serie = locais[locais["local"] == local].sort_values("ano").copy()
serie["pct"] = 100 * serie[coluna] / serie["qt_eleitores"]
uf = locais[(locais["ano"] == ANO) & (locais["local"] != "BR")].copy()
uf["pct"] = 100 * uf[coluna] / uf["qt_eleitores"]
uf = uf.sort_values("pct", ascending=False)

r_atual, r_antes = serie.iloc[-1], serie.iloc[-2]
st.markdown(
    f"Em {ANO}, {no_local(local)}, são **{comum.numero(r_atual[coluna])} eleitores com {grupo}** "
    f"({comum.pct(r_atual['pct'] / 100)} do eleitorado). Em {ANTERIOR}, eram {comum.numero(r_antes[coluna])} "
    f"({comum.pct(r_antes['pct'] / 100)})."
)

esquerda, direita = st.columns(2, gap="large")
with esquerda:
    st.markdown(f"**Eleitores com {grupo} em cada eleição, {no_local(local)}**")
    st.caption("Em % do eleitorado de cada ano.")
    fig = go.Figure(go.Bar(
        x=serie["ano"].astype(str), y=serie["pct"], marker_color=comum.SERIE,
        customdata=[f"<b>{a}</b><br>{comum.numero(q)} eleitores<br>{comum.pct(p / 100)} do eleitorado"
                    for a, q, p in zip(serie["ano"], serie[coluna], serie["pct"])],
        hovertemplate="%{customdata}<extra></extra>"))
    comum.estilo(fig, altura=360, legenda=False)
    fig.update_layout(bargap=0.55)
    fig.update_xaxes(type="category")
    eixo_porcentagem(fig, serie["pct"].max(), eixo="y")
    comum.mostrar(fig, tabela=pd.DataFrame({
        "Eleição": serie["ano"].astype(str),
        f"Eleitores com {grupo}": serie[coluna].map(comum.numero),
        "Eleitorado total": serie["qt_eleitores"].map(comum.numero),
        "% do eleitorado": (serie["pct"] / 100).map(comum.pct),
        "Arquivo do TSE gerado em": serie["dt_geracao"].map(data_br),
    }), fonte=FONTE_PERFIL, chave="facultativo_anos")

with direita:
    st.markdown(f"**Eleitores com {grupo} em cada UF, em {ANO}**")
    destaque = local not in ("BR",)
    media = 100 * atual.loc["BR", coluna] / atual.loc["BR", "qt_eleitores"]
    st.caption(f"Em % do eleitorado de cada UF. A linha vertical é o Brasil ({comum.pct(media / 100)})."
               + (f" Em destaque: {nome(local)}." if destaque else ""))
    cores = [comum.DESTAQUE if s == local else comum.APAGADO for s in uf["local"]] if destaque \
        else [comum.SERIE] * len(uf)
    fig = barras_horizontais(
        [s if s != "ZZ" else "Exterior" for s in uf["local"]], uf["pct"], cores,
        [f"<b>{nome(s)}</b><br>{comum.numero(q)} eleitores<br>{comum.pct(p / 100)} do eleitorado"
         for s, q, p in zip(uf["local"], uf[coluna], uf["pct"])], altura=640)
    fig.add_vline(x=media, line_width=1.5, line_color=comum.TINTA_2)
    eixo_porcentagem(fig, uf["pct"].max())
    comum.mostrar(fig, tabela=pd.DataFrame({
        "UF": uf["local"].map(nome),
        f"Eleitores com {grupo}": uf[coluna].map(comum.numero),
        "% do eleitorado": (uf["pct"] / 100).map(comum.pct),
    }), fonte=FONTE_PERFIL, chave="facultativo_uf")

if grupo == "16 e 17 anos":
    jovens_censo = censo.loc["16 anos", "populacao_censo_2022"] + censo.loc["17 anos", "populacao_censo_2022"]
    jovens_2022 = censo.loc["16 anos", "qt_eleitores_2022"] + censo.loc["17 anos", "qt_eleitores_2022"]
    st.markdown(
        f"Para comparar: o Censo 2022 contou {grande(jovens_censo)} de pessoas com 16 ou 17 anos no Brasil, e "
        f"{grande(jovens_2022)} de jovens dessas idades estavam no eleitorado de 2022, cerca de "
        f"{comum.numero(100 * jovens_2022 / jovens_censo)} de cada 100. Em todas as eleições desde "
        f"{int(locais['ano'].min())} há mais eleitores de 17 anos do que de 16."
    )
    st.caption("Fontes: TSE, perfil do eleitorado; IBGE, Censo 2022 (SIDRA, tabela 9514).")
else:
    idosos = locais[locais["local"] == "BR"].sort_values("ano")
    idosos_pct = idosos["qt_70_mais"] / idosos["qt_eleitores"]
    st.markdown(
        f"No Brasil, a parte do eleitorado com 70 anos ou mais foi de {comum.pct(idosos_pct.iloc[0])} em "
        f"{int(idosos['ano'].iloc[0])} para {comum.pct(idosos_pct.iloc[-1])} em {ANO}"
        + (", e cresceu em todas as eleições" if idosos_pct.is_monotonic_increasing else "")
        + ", acompanhando o envelhecimento da população. Esse grupo inclui registros de pessoas que podem já ter "
        "morrido (ponto de atenção acima)."
    )

# --- 3. municípios com mais eleitores do que habitantes ------------------------
st.subheader("Municípios com mais eleitores do que habitantes")
mun = municipios.dropna(subset=["populacao"]).copy()
mun["acima"] = mun["qt_eleitores"] > mun["populacao"]
acima = mun[mun["acima"]].sort_values("eleitores_por_100_hab", ascending=False)
ano_pop = int(mun["ano_populacao"].max())
acima_censo = mun[mun["qt_eleitores"] > mun["populacao_censo_2022"]]
nas_duas = acima["cd_municipio_tse"].isin(acima_censo["cd_municipio_tse"]).sum()
mediana = mun["eleitores_por_100_hab"].median()

m1, m2, m3 = st.columns(3)
with m1:
    comum.cartao("Municípios nessa situação", comum.numero(len(acima)),
                 f"{comum.pct(len(acima) / len(mun))} dos {comum.numero(len(mun))} municípios",
                 cor=comum.DESTAQUE)
with m2:
    comum.cartao("Eleitores por 100 habitantes", comum.numero(mediana, 0),
                 "no município típico (mediana); menores de 16 anos não votam")
with m3:
    comum.cartao("Eleitores nesses municípios", grande(acima["qt_eleitores"].sum()),
                 f"{comum.pct(acima['qt_eleitores'].sum() / mun['qt_eleitores'].sum())} do eleitorado no Brasil; "
                 f"metade desses municípios tem menos de {comum.numero(acima['qt_eleitores'].median())} eleitores")

st.markdown(
    f"Comparamos o eleitorado de {ANO} de cada município com a população estimada pelo IBGE para {ano_pop}. "
    "**Isso é um ponto de atenção conhecido, não um indício de fraude.** As explicações mais comuns:\n"
    "- **O título fica onde a pessoa escolheu votar, não onde ela mora.** Quem se muda para outra cidade "
    "pode manter o título na cidade de origem (onde tem família ou vínculo) e voltar para votar.\n"
    "- **A população é uma estimativa.** Fora dos anos de censo, o IBGE calcula a população de cada "
    "município por modelo; em municípios pequenos, poucas centenas de pessoas mudam a conta. Pelo Censo "
    f"2022, a lista teria {comum.numero(len(acima_censo))} municípios ({comum.numero(nas_duas)} aparecem "
    "nas duas contas).\n"
    "- **O cadastro demora a sair de quem morreu ou se mudou de vez.** O título só é cancelado quando o "
    "óbito é comunicado à Justiça Eleitoral ou depois de três eleições seguidas sem votar, justificar a "
    "ausência ou pagar a multa.\n\n"
    "A própria Justiça Eleitoral acompanha essa comparação: a Lei 9.504/1997 (art. 92) prevê revisão do "
    "cadastro quando o número de eleitores fica alto em relação à população estimada pelo IBGE."
)

st.markdown("**Quantos eleitores há para cada 100 habitantes, município por município**")
st.caption("Como ler: cada barra conta quantos municípios têm aquela proporção. 100 quer dizer um eleitor "
           "por habitante. Em laranja, os municípios com mais eleitores do que habitantes.")
largura = 5
mun["faixa"] = (mun["eleitores_por_100_hab"] // largura * largura).clip(upper=200)
contagem = mun.groupby("faixa").agg(municipios=("cd_municipio_tse", "size"), acima=("acima", "max")).reset_index()
contagem["rotulo"] = [f"{comum.numero(f)} a {comum.numero(f + largura)}" if f < 200 else "200 ou mais"
                      for f in contagem["faixa"]]
fig = go.Figure(go.Bar(
    x=contagem["faixa"] + largura / 2, y=contagem["municipios"], width=largura * 0.8,
    marker_color=[comum.DESTAQUE if a else comum.APAGADO for a in contagem["acima"]],
    customdata=[f"<b>{r} eleitores por 100 habitantes</b><br>{comum.numero(n)} municípios"
                for r, n in zip(contagem["rotulo"], contagem["municipios"])],
    hovertemplate="%{customdata}<extra></extra>", showlegend=False))
legenda_manual(fig, {"Mais habitantes do que eleitores": comum.APAGADO,
                     "Mais eleitores do que habitantes": comum.DESTAQUE})
comum.estilo(fig, altura=360)
fig.update_xaxes(title="Eleitores por 100 habitantes", tickvals=list(range(0, 201, 25)),
                 ticktext=[comum.numero(v) if v < 200 else "200+" for v in range(0, 201, 25)])
fig.update_yaxes(title="Municípios")
fig.update_layout(bargap=0)
comum.mostrar(fig, tabela=pd.DataFrame({
    "Eleitores por 100 habitantes": contagem["rotulo"],
    "Municípios": contagem["municipios"].map(comum.numero),
}), fonte=f"TSE, perfil do eleitorado {ANO}; {FONTE_IBGE}", chave="municipios_hist")

por_uf = mun.groupby("uf").agg(total=("cd_municipio_tse", "size"), acima=("acima", "sum")).reset_index()
por_uf = por_uf[por_uf["acima"] > 0].sort_values(["acima", "uf"], ascending=[False, True])
destaque = local in set(por_uf["uf"])
st.markdown("**Municípios com mais eleitores do que habitantes, por UF**")
st.caption("Número de municípios. Passe o mouse (ou toque) numa barra para ver a parte dos municípios da UF."
           + (f" Em destaque: {nome(local)}." if destaque else ""))
fig = barras_horizontais(
    por_uf["uf"], por_uf["acima"],
    [comum.DESTAQUE if s == local else comum.APAGADO for s in por_uf["uf"]] if destaque
    else [comum.SERIE] * len(por_uf),
    [f"<b>{nome(s)}</b><br>{comum.numero(a)} de {comum.numero(t)} municípios ({comum.pct(a / t)})"
     for s, a, t in zip(por_uf["uf"], por_uf["acima"], por_uf["total"])])
comum.mostrar(fig, tabela=pd.DataFrame({
    "UF": por_uf["uf"].map(nome),
    "Municípios com mais eleitores do que habitantes": por_uf["acima"].map(comum.numero),
    "Municípios da UF": por_uf["total"].map(comum.numero),
    "% dos municípios da UF": (por_uf["acima"] / por_uf["total"]).map(comum.pct),
}), fonte=f"TSE, perfil do eleitorado {ANO}; {FONTE_IBGE}", chave="municipios_uf")

por_lugar = local not in ("BR", "ZZ")
lista = acima[acima["uf"] == local] if por_lugar else acima
st.markdown(f"**A lista {'de ' + nome(local) if por_lugar else 'completa'}** "
            f"({comum.numero(len(lista))} municípios, do maior para o menor número de eleitores por 100 habitantes)")
if len(lista):
    st.dataframe(pd.DataFrame({
        "Município": lista["nm_municipio"],
        "UF": lista["uf"],
        f"Eleitores {ANO}": lista["qt_eleitores"].map(comum.numero),
        f"População {ano_pop}": lista["populacao"].map(comum.numero),
        "Eleitores por 100 hab.": lista["eleitores_por_100_hab"].map(lambda v: comum.numero(v, 0)),
        "Censo 2022": lista["populacao_censo_2022"].map(comum.numero),
    }), hide_index=True, height=320)
else:
    st.caption(f"Nenhum município de {nome(local)} tem mais eleitores do que habitantes.")
st.caption(f"Fonte: TSE, perfil do eleitorado {ANO}; {FONTE_IBGE}; IBGE, Censo 2022 (SIDRA, tabela 4709).")

# --- 4. abstenção ----------------------------------------------------------------
st.subheader("Quem deixou de votar: abstenção por idade e escolaridade")
eleicoes = abstencao[["ano", "turno"]].drop_duplicates().sort_values(["ano", "turno"])
if ANO not in eleicoes["ano"].values:
    st.info(f"O TSE ainda não publicou o perfil do comparecimento e da abstenção de {ANO} (consultado em "
            f"{data_br(abstencao['dt_consulta'].max())}). Os gráficos abaixo mostram {int(eleicoes['ano'].max())}; "
            f"{ANO} entra aqui quando o arquivo sair.", icon=":material/event:")
rotulos = {f"{t}º turno de {a}": (a, t) for a, t in eleicoes.itertuples(index=False)}
padrao = [r for r, (a, t) in rotulos.items() if t == 1][-1]
escolha = st.segmented_control("Eleição", list(rotulos), default=padrao, required=True, key="eleicao_abstencao")
ano_ab, turno_ab = rotulos[escolha]
ab = abstencao[(abstencao["ano"] == ano_ab) & (abstencao["turno"] == turno_ab)].copy()
ab["taxa"] = 100 * ab["qt_abstencao"] / ab["qt_aptos"]
geral = ab[ab["dimensao"] == "total"].iloc[0]
generos = ab[ab["dimensao"] == "genero"].set_index("categoria")

st.markdown(
    f"Abstenção é a parte dos eleitores aptos que não foi votar. No {escolha}, foi de "
    f"**{comum.pct(geral['taxa'] / 100)}**: {comum.numero(geral['qt_abstencao'])} de "
    f"{comum.numero(geral['qt_aptos'])} eleitores. Entre as mulheres, {comum.pct(generos.loc['Mulheres', 'taxa'] / 100)}; "
    f"entre os homens, {comum.pct(generos.loc['Homens', 'taxa'] / 100)}."
)
# nomes curtos: a legenda precisa caber numa linha nos gráficos estreitos (duas colunas)
cores_voto = {"Obrigatório": comum.SERIE, "Facultativo": comum.DESTAQUE}


def grafico_abstencao(d: pd.DataFrame, chave: str, rotulo: str) -> None:
    d = d.sort_values("ordem")
    fig = barras_horizontais(
        d["categoria"], d["taxa"],
        [cores_voto["Facultativo" if f else "Obrigatório"] for f in d["facultativo"]],
        [f"<b>{c}</b><br>{comum.pct(t / 100)} não votaram<br>{comum.numero(a)} de {comum.numero(n)} eleitores"
         for c, t, a, n in zip(d["categoria"], d["taxa"], d["qt_abstencao"], d["qt_aptos"])])
    legenda_manual(fig, cores_voto)
    fig.add_vline(x=geral["taxa"], line_width=1.5, line_color=comum.TINTA_2)
    eixo_porcentagem(fig, d["taxa"].max())
    comum.mostrar(fig, tabela=pd.DataFrame({
        rotulo: d["categoria"],
        "Abstenção": (d["taxa"] / 100).map(comum.pct),
        "Não votaram": d["qt_abstencao"].map(comum.numero),
        "Eleitores aptos": d["qt_aptos"].map(comum.numero),
        "Voto": d["facultativo"].map({True: "facultativo", False: "obrigatório"}),
    }), fonte=f"{FONTE_ABSTENCAO}, {ano_ab}", chave=chave)


esquerda, direita = st.columns(2, gap="large")
with esquerda:
    st.markdown(f"**Abstenção por idade, {escolha}**")
    st.caption("Em % dos eleitores aptos de cada idade. Ex.: a barra de 80 a 84 anos mostra quantos de cada 100 "
               f"eleitores dessa idade não votaram. A linha vertical é a abstenção de todos os eleitores "
               f"({comum.pct(geral['taxa'] / 100)}).")
    idade = ab[ab["dimensao"] == "idade"].copy()
    idade["categoria"] = idade["categoria"].map(idade_texto)
    grafico_abstencao(idade, "abstencao_idade", "Idade")

with direita:
    st.markdown(f"**Abstenção por escolaridade, {escolha}**")
    so_obrigatorio = st.toggle("Só eleitores de 18 a 69 anos", key="abstencao_18_69",
                               help="Separa o efeito da idade: quem tem menos escolaridade é, em média, mais velho.")
    st.caption("Em % dos eleitores aptos de cada grau de instrução (o declarado ao tirar o título). "
               "Analfabetos têm voto facultativo em qualquer idade. A linha vertical é a abstenção de todos os "
               f"eleitores ({comum.pct(geral['taxa'] / 100)}).")
    escolaridade = ab[ab["dimensao"] == ("escolaridade_18_69" if so_obrigatorio else "escolaridade")]
    grafico_abstencao(escolaridade[escolaridade["categoria"] != "Não informado"], "abstencao_escolaridade",
                      "Escolaridade")

idades_ab = ab[ab["dimensao"] == "idade"].set_index("categoria")
oficial = ab[ab["dimensao"] == "resultado_oficial"]
st.markdown(
    f"A partir dos 70 anos, quando o voto deixa de ser obrigatório, a abstenção passa da média de todos os "
    f"eleitores ({comum.pct(idades_ab.loc['70 a 74', 'taxa'] / 100)} de 70 a 74 anos e "
    f"{comum.pct(idades_ab.loc['80 a 84', 'taxa'] / 100)} de 80 a 84). Nas idades mais altas, parte dela pode vir "
    "de registros de pessoas que já morreram (ponto de atenção da pirâmide). Entre os jovens de 16 e 17 anos, que "
    f"também têm voto facultativo, ficou em {comum.pct(idades_ab.loc['16 anos', 'taxa'] / 100)} e "
    f"{comum.pct(idades_ab.loc['17 anos', 'taxa'] / 100)}: só está no eleitorado quem pediu o título."
)
if len(oficial):
    o = oficial.iloc[0]
    st.caption(
        f"Conferência: o arquivo de perfil soma {comum.numero(geral['qt_abstencao'])} abstenções no {escolha}; o "
        f"resultado oficial de Presidente, {comum.numero(o['qt_abstencao'])} (diferença de "
        f"{comum.pct(abs(geral['qt_abstencao'] - o['qt_abstencao']) / o['qt_aptos'], 2)} do eleitorado). "
        "O resultado oficial é sempre o do TSE."
    )

# --- 5. gênero e escolaridade --------------------------------------------------------
st.subheader("Gênero e escolaridade do eleitorado")
genero = evolucao[(evolucao["dimensao"] == "genero")].copy()
genero["pct"] = 100 * genero["qt_eleitores"] / genero.groupby("ano")["qt_eleitores"].transform("sum")
pct_m = genero[genero["categoria"] == "Mulheres"].set_index("ano")["pct"]
st.markdown(
    f"As mulheres são a maior parte do eleitorado em todas as eleições desde {int(pct_m.index.min())}: "
    f"{comum.pct(pct_m.iloc[0] / 100)} em {int(pct_m.index.min())} e {comum.pct(pct_m.iloc[-1] / 100)} em {ANO}, "
    f"{comum.pontos((pct_m.iloc[-1] - pct_m.iloc[0]) / 100)} a mais."
)

esquerda, direita = st.columns(2, gap="large")
with esquerda:
    st.markdown("**Mulheres e homens no eleitorado do Brasil, por eleição**")
    st.caption("Cada barra soma 100% do eleitorado do ano. A linha marca a metade.")
    fig = go.Figure()
    for categoria in ["Mulheres", "Homens"]:
        d = genero[genero["categoria"] == categoria].sort_values("ano")
        fig.add_bar(y=d["ano"].astype(str), x=d["pct"], orientation="h", name=categoria,
                    marker=dict(color=COR_GENERO[categoria], line=dict(width=2, color=comum.SUPERFICIE)),
                    customdata=[f"<b>{categoria}, {a}</b><br>{comum.pct(p / 100)} ({comum.numero(q)})"
                                for a, p, q in zip(d["ano"], d["pct"], d["qt_eleitores"])],
                    hovertemplate="%{customdata}<extra></extra>")
    comum.estilo(fig, altura=330)
    fig.update_layout(barmode="stack", bargap=0.45, legend=dict(traceorder="normal"))
    fig.update_yaxes(type="category", autorange="reversed", showgrid=False, ticklabelstandoff=6)
    fig.update_xaxes(range=[0, 101], tickvals=[0, 25, 50, 75, 100],
                     ticktext=["0%", "25%", "50%", "75%", "100%"], showgrid=True, gridcolor=comum.GRADE)
    fig.add_vline(x=50, line_width=1.5, line_color=comum.TINTA)
    tab = genero.pivot_table(index="ano", columns="categoria", values="qt_eleitores").reset_index()
    comum.mostrar(fig, tabela=pd.DataFrame({
        "Eleição": tab["ano"].astype(str),
        "Mulheres": tab["Mulheres"].map(comum.numero),
        "Homens": tab["Homens"].map(comum.numero),
        "Gênero não informado": tab["Não informado"].map(comum.numero),
        "% de mulheres": (tab["Mulheres"] / tab[["Mulheres", "Homens", "Não informado"]].sum(axis=1)).map(comum.pct),
    }), fonte=FONTE_PERFIL, chave="genero_anos")

with direita:
    escol = evolucao[evolucao["dimensao"] == "escolaridade"].copy()
    escol["pct"] = 100 * escol["qt_eleitores"] / escol.groupby("ano")["qt_eleitores"].transform("sum")
    escol = escol[escol["categoria"] != "Não informado"]
    anos_comparar = sorted(a for a in escol["ano"].unique() if a != ANO)
    st.markdown(f"**Escolaridade do eleitorado do Brasil, {ANO} e outra eleição**")
    comparar = st.segmented_control("Comparar com", [str(a) for a in anos_comparar], default=str(anos_comparar[0]),
                                    required=True, key="escolaridade_comparar")
    st.caption("Em % do eleitorado de cada ano. É o grau de instrução declarado ao tirar o título; quem estudou "
               "depois e não atualizou o cadastro continua com o grau antigo.")
    cores_anos = {comparar: comum.APAGADO, str(ANO): comum.SERIE}
    fig = go.Figure()
    for ano_txt, cor in cores_anos.items():
        d = escol[escol["ano"] == int(ano_txt)].sort_values("ordem")
        fig.add_bar(y=d["categoria"], x=d["pct"], orientation="h", name=ano_txt, marker_color=cor,
                    customdata=[f"<b>{c}, {ano_txt}</b><br>{comum.pct(p / 100)} ({comum.numero(q)} eleitores)"
                                for c, p, q in zip(d["categoria"], d["pct"], d["qt_eleitores"])],
                    hovertemplate="%{customdata}<extra></extra>")
    comum.estilo(fig, altura=430)
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.1)
    fig.update_yaxes(autorange="reversed", showgrid=False, ticklabelstandoff=6)
    fig.update_xaxes(showgrid=True, gridcolor=comum.GRADE)
    eixo_porcentagem(fig, escol[escol["ano"].isin([int(comparar), ANO])]["pct"].max())
    tab = escol[escol["ano"].isin([int(comparar), ANO])].pivot_table(
        index=["ordem", "categoria"], columns="ano", values="pct").reset_index()
    comum.mostrar(fig, tabela=pd.DataFrame({
        "Escolaridade": tab["categoria"],
        f"% em {comparar}": (tab[int(comparar)] / 100).map(comum.pct),
        f"% em {ANO}": (tab[ANO] / 100).map(comum.pct),
        "Diferença": [("+" if b >= a else "−") + comum.pontos((b - a) / 100)
                      for a, b in zip(tab[int(comparar)], tab[ANO])],
    }), fonte=FONTE_PERFIL, chave="escolaridade_anos")

# --- conferência ------------------------------------------------------------------
with st.expander("Conferência: o eleitorado desta página bate com os eleitores aptos do resultado?"):
    c = conferencia.copy()
    br = c[c["local"] == "BR"]
    st.markdown(
        "Comparamos o total do perfil do eleitorado com os eleitores aptos do 1º turno de Presidente "
        "(resultado oficial do TSE). No Brasil, a diferença é "
        + "; ".join(f"{a}: {comum.numero(p - q)}" for a, p, q in zip(br["ano"], br["qt_perfil"], br["qt_aptos_1t"]))
        + f" eleitores. Por UF, em {ANO}, a diferença vem quase toda da **transferência temporária**: quem pediu "
        "para votar em outra UF (voto em trânsito, militares, presos provisórios, mesários etc.) conta no perfil "
        "na UF do título e no resultado na UF onde votou."
    )
    u = c[(c["ano"] == ANO) & (c["local"] != "BR")].copy()
    u["ajustado"] = u["qt_perfil"] + u["tte_entrada"] - u["tte_saida"]
    st.dataframe(pd.DataFrame({
        "UF": u["local"].map(nome),
        "Perfil do eleitorado": u["qt_perfil"].map(comum.numero),
        "Aptos no 1º turno": u["qt_aptos_1t"].map(comum.numero),
        "Diferença": (u["qt_perfil"] - u["qt_aptos_1t"]).map(comum.numero),
        "Vieram de outra UF": u["tte_entrada"].map(comum.numero),
        "Foram para outra UF": u["tte_saida"].map(comum.numero),
        "Diferença depois da transferência": (u["ajustado"] - u["qt_aptos_1t"]).map(comum.numero),
    }), hide_index=True)
    st.caption("Fontes: TSE, perfil do eleitorado e transferência temporária do eleitorado (1º turno de 2026); "
               "resultado do 1º turno de Presidente.")

comum.rodape()
