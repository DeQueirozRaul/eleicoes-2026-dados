"""Conferência dos dados: o que o projeto confere antes de concluir.

Dados: app/dados/conferencia_*.parquet, gerados por scripts/site_conferencia.py.
"""

import comum
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

FONTE_SECOES = ("TSE, Portal de Dados Abertos: votação e detalhe da apuração por seção eleitoral (Presidente, "
                "1º turno de 2026) e resultado oficial por município.")

comum.cabecalho(
    "Conferência dos dados",
    "Antes de tirar conclusões, o projeto confere se as contas batem com o resultado oficial e se os "
    "métodos reproduzem o que aconteceu. Aqui estão as conferências e o que foi encontrado.",
)

if not comum.existe("conferencia_resumo"):
    st.info("Os dados desta página ainda não foram gerados: rode `python scripts/site_conferencia.py`.")
    comum.rodape()
    st.stop()

resumo = comum.ler("conferencia_resumo").iloc[0]


def votos(x) -> str:
    """Número de votos com a palavra certa: '1 voto', '0 votos', '5.246 votos'."""
    return f"{comum.numero(x)} {'voto' if abs(x) == 1 else 'votos'}"


def diferenca(x) -> str:
    """Diferença em votos com sinal: '0', '+829', '−98'."""
    if x == 0:
        return "0"
    return ("+" if x > 0 else "−") + comum.numero(abs(x))


def altura_tabela(linhas: int) -> int:
    """Altura (px) para st.dataframe mostrar todas as linhas sem rolagem."""
    return 35 * (linhas + 1) + 3


def titulo_grafico(titulo: str, como_ler: str) -> None:
    st.markdown(f"##### {titulo}")
    st.caption(f"**Como ler:** {como_ler}")


def nome_uf(uf: str) -> str:
    return "Exterior" if uf == "ZZ" else uf


def municipio(texto: str) -> str:
    """'SÃO PAULO (SP)' -> 'São Paulo (SP)'."""
    nome, _, uf = texto.partition(" (")
    return f"{nome.title()} ({uf}" if uf else nome.title()


st.markdown(
    "**Nesta página:** "
    "[1. Soma das seções × resultado oficial](#soma-das-secoes) · "
    "[2. Reprodução da apuração de 2022](#apuracao-2022) · "
    "[3. Voto a voto (RDV) × oficial](#rdv) · "
    "[4. Lei de Benford](#benford) · "
    "[5. Checagens automáticas](#checagens) · "
    "[6. Seções fora do padrão](#fora-do-padrao)"
)

# ---------------------------------------------------------------------------
# 1. Soma das seções × resultado oficial
# ---------------------------------------------------------------------------
st.header("1. A soma das seções bate com o resultado oficial?", anchor="soma-das-secoes")
st.markdown(
    f"Cada seção eleitoral (o lugar onde um grupo de eleitores vota, com uma urna) gera um boletim com os "
    f"votos dela. O TSE publica os votos de cada uma das **{comum.numero(resumo['secoes_detalhe'])} seções** "
    f"e, separadamente, o resultado oficial. Se os dados estão certos, somar as seções tem de dar exatamente "
    f"o resultado oficial. Fizemos a soma para Presidente, 1º turno de 2026, candidato por candidato, em cada "
    f"UF, em cada município e no exterior."
)

c1, c2, c3 = st.columns(3)
with c1:
    comum.cartao(f"Votos nos {resumo['candidatos_oficiais']} candidatos, somando as seções",
                 comum.numero(resumo["validos_secoes"]))
with c2:
    comum.cartao("Resultado oficial do TSE", comum.numero(resumo["validos_oficial"]))
with c3:
    if resumo["municipios_com_diferenca"] == 0:
        detalhe_dif = (f"Também zero em cada candidato, em cada UF e em cada um dos "
                       f"{comum.numero(resumo['municipios'])} municípios e cidades do exterior.")
    else:
        detalhe_dif = (f"{comum.numero(resumo['municipios_com_diferenca'])} dos "
                       f"{comum.numero(resumo['municipios'])} municípios e cidades do exterior têm diferença.")
    comum.cartao("Diferença", votos(resumo["diferenca_validos"]), detalhe_dif)

if resumo["votos_fora"]:
    st.markdown(
        f"**O que aparecia no arquivo das seções e não no resultado oficial:** "
        f"{votos(resumo['votos_fora'])} no número {resumo['nr_fora']} ({resumo['nm_urna_fora']}, "
        f"{resumo['partido_fora']}). Pelo cadastro de candidatos do TSE, essa candidatura terminou em "
        f"{resumo['situacao_fora'].lower()}, mas o número estava na urna; os votos nele têm destino "
        f"\"{resumo['destino_votos_fora'].lower()}\", ou seja, contam como **nulos**. No arquivo das seções eles "
        f"aparecem no número {resumo['nr_fora']}; no resultado oficial, dentro dos nulos. Somando os dois, os "
        f"nulos também batem: {comum.numero(resumo['nulos_secoes'])} + {comum.numero(resumo['votos_fora'])} = "
        f"{comum.numero(resumo['nulos_oficial'])}, o número oficial."
    )

por_uf = comum.ler("conferencia_secoes_uf")
tabela_uf = pd.DataFrame({
    "UF": por_uf["uf"].map(nome_uf),
    "Soma das seções": por_uf["validos_secoes"].map(comum.numero),
    "Resultado oficial": por_uf["candidatos_oficial"].map(comum.numero),
    "Diferença": por_uf["diferenca"].map(diferenca),
    "Seções": por_uf["secoes"].map(comum.numero),
    f"Votos no nº {resumo['nr_fora']} (nulos no oficial)": por_uf["votos_fora"].map(comum.numero),
})
st.markdown("##### Votos nos candidatos a Presidente, por UF: soma das seções × resultado oficial")
st.caption("**Como ler:** cada linha é uma UF (ou o exterior). \"Diferença\" é a soma das seções menos o "
           "resultado oficial: zero em todas.")
st.dataframe(tabela_uf, hide_index=True)
st.caption(f"Fonte: {FONTE_SECOES}")

with st.expander("Por candidato, e os outros números conferidos"):
    por_candidato = comum.ler("conferencia_secoes_candidato")
    st.markdown("**Por candidato (Brasil e exterior), em ordem alfabética**")
    st.dataframe(pd.DataFrame({
        "Candidato": por_candidato["nm_urna"] + " (" + por_candidato["nr_candidato"].astype(str) + ")",
        "Soma das seções": por_candidato["soma_secoes"].map(comum.numero),
        "Resultado oficial": por_candidato["oficial"].map(comum.numero),
        "Diferença": por_candidato["diferenca"].map(diferenca),
        "UFs com diferença": por_candidato["ufs_com_diferenca"].map(comum.numero),
    }), hide_index=True, height=altura_tabela(len(por_candidato)))
    st.caption(f"O número {resumo['nr_fora']} não está no resultado oficial porque os votos nele contam como nulos.")
    st.markdown("**Outros números conferidos**")
    outros = pd.DataFrame([
        ("Eleitores aptos", resumo["aptos_secoes"], resumo["aptos_oficial"]),
        ("Comparecimento (pessoas que votaram)", resumo["comparecimento_secoes"], resumo["comparecimento_oficial"]),
        ("Votos em branco", resumo["brancos_secoes"], resumo["brancos_oficial"]),
        (f"Votos nulos (com os votos no nº {resumo['nr_fora']})", resumo["nulos_secoes"] + resumo["votos_fora"],
         resumo["nulos_oficial"]),
    ], columns=["O que", "Soma das seções", "Resultado oficial"])
    outros["Diferença"] = (outros["Soma das seções"] - outros["Resultado oficial"]).map(diferenca)
    outros["Soma das seções"] = outros["Soma das seções"].map(comum.numero)
    outros["Resultado oficial"] = outros["Resultado oficial"].map(comum.numero)
    st.dataframe(outros, hide_index=True)

# ---------------------------------------------------------------------------
# 2. Reprodução da apuração de 2022
# ---------------------------------------------------------------------------
st.header("2. A apuração de 2022 reproduzida bate com o registro oficial?", anchor="apuracao-2022")
st.markdown(
    "Para testar a [previsão ao vivo](/apuracao), o projeto reconstruiu a noite da apuração do 2º turno de 2022 "
    "a partir dos boletins de urna: cada seção entra na conta no minuto em que o boletim chegou ao TSE. Se a "
    "reconstrução estiver certa, ela tem de repetir o registro oficial do TSE (o \"histórico de totalização\"), "
    "que mostra, ao longo da noite, quanto já estava apurado e o placar."
)
curva = comum.ler("conferencia_apuracao_2022")
inicio, fim = curva["momento"].min(), curva["momento"].max()
c1, c2 = st.columns(2)
with c1:
    comum.cartao("Diferença média no total de seções apuradas", comum.pontos(resumo["apuracao_dif_secoes_media"]),
                 f"em {resumo['apuracao_momentos']} momentos, das {inicio:%Hh%M} às {fim:%Hh%M}")
with c2:
    comum.cartao("Diferença média no placar", comum.pontos(resumo["apuracao_dif_placar_media"], 2),
                 f"{comum.pontos(resumo['apuracao_dif_placar_media_depois_5'], 2)} depois de 5% das seções apuradas")

REPRODUZIDA, OFICIAL = "Reconstrução do projeto (boletins de urna)", "Registro oficial do TSE"


def grafico_noite(coluna: str, rotulo_y: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=curva["momento"], y=100 * curva[f"{coluna}_oficial"], name=OFICIAL, mode="lines",
        line=dict(color=comum.TINTA_2, width=2, dash="dot"),
        hovertemplate=f"{OFICIAL}: %{{y:.2f}}%<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=curva["momento"], y=100 * curva[f"{coluna}_reproduzida"], name=REPRODUZIDA, mode="lines",
        line=dict(color=comum.SERIE, width=2),
        hovertemplate=f"{REPRODUZIDA}: %{{y:.2f}}%<extra></extra>"))
    comum.estilo(fig, altura=340)
    fig.update_layout(hovermode="x unified", margin=dict(t=56))
    fig.update_xaxes(tickformat="%Hh%M", hoverformat="%Hh%M", title=None)
    fig.update_yaxes(title=rotulo_y, ticksuffix="%")
    return fig


def tabela_noite(coluna: str) -> pd.DataFrame:
    amostra = curva.iloc[::5]
    return pd.DataFrame({
        "Hora": amostra["momento"].dt.strftime("%Hh%M"),
        OFICIAL: (amostra[f"{coluna}_oficial"]).map(lambda v: comum.pct(v, 2)),
        REPRODUZIDA: (amostra[f"{coluna}_reproduzida"]).map(lambda v: comum.pct(v, 2)),
    })


titulo_grafico(
    "Seções apuradas ao longo da noite do 2º turno de 2022 (% do total)",
    f"as duas linhas quase se sobrepõem. A maior distância entre elas foi de "
    f"{comum.pontos(resumo['apuracao_dif_secoes_max'])}.")
comum.mostrar(grafico_noite("pct_secoes", "Seções apuradas"), tabela=tabela_noite("pct_secoes"),
              fonte="TSE: boletins de urna e histórico de totalização do 2º turno de 2022 (Presidente).",
              chave="noite_secoes")

titulo_grafico(
    "Placar de LULA ao longo da noite do 2º turno de 2022 (% dos votos válidos)",
    f"o 2º turno foi entre JAIR BOLSONARO e LULA; o placar de JAIR BOLSONARO é o que falta para 100%. "
    f"Nos primeiros minutos, com poucas seções apuradas, cada boletim muda muito o placar e a distância chega "
    f"a {comum.pontos(resumo['apuracao_dif_placar_max'])}; depois de 5% apurado, a distância média é de "
    f"{comum.pontos(resumo['apuracao_dif_placar_media_depois_5'], 2)}.")
fig = grafico_noite("pct_a", "Placar de LULA")
fig.add_hline(y=50, line=dict(color=comum.APAGADO, width=1))
comum.mostrar(fig, tabela=tabela_noite("pct_a"),
              fonte="TSE: boletins de urna e histórico de totalização do 2º turno de 2022 (Presidente).",
              chave="noite_placar")

# ---------------------------------------------------------------------------
# 3. RDV × oficial
# ---------------------------------------------------------------------------
st.header("3. A leitura voto a voto (RDV) bate com o resultado oficial?", anchor="rdv")
st.markdown(
    "Para a análise dos votos no número errado, o projeto leu o **Registro Digital do Voto (RDV)** de todas as "
    "urnas de 9 disputas para Governador. O RDV é o arquivo em que a urna guarda cada voto digitado, embaralhado "
    "e sem identificar o eleitor. Antes de usar a leitura, conferimos: a soma dos votos de cada candidato no "
    "RDV tem de bater com o resultado oficial."
)
rdv = comum.ler("conferencia_rdv")
exatas = int((rdv["diferenca_rdv_oficial"] == 0).sum())
c1, c2 = st.columns(2)
with c1:
    comum.cartao("Disputas em que a soma bateu exatamente", f"{exatas} de {len(rdv)}")
with c2:
    comum.cartao(f"Maior diferença nas outras {len(rdv) - exatas}",
                 comum.pct(rdv["diferenca_pct"].abs().max(), 2) + " dos votos",
                 "explicações abaixo da tabela")
rdv["disputa"] = rdv["uf"] + " " + rdv["ano"].astype(str)
st.markdown("##### Votos nos candidatos a Governador (1º turno): soma no RDV × resultado oficial")
st.caption("**Como ler:** \"Diferença\" é o RDV menos o resultado oficial; \"+\" quer dizer que o RDV tem mais "
           "votos. A % é da soma de votos dos candidatos na disputa.")
st.dataframe(pd.DataFrame({
    "Disputa": rdv["disputa"],
    "Soma no RDV": rdv["votos_rdv"].map(comum.numero),
    "Resultado oficial": rdv["votos_oficial"].map(comum.numero),
    "Diferença": rdv["diferenca_rdv_oficial"].map(diferenca),
    "Diferença (%)": rdv["diferenca_pct"].abs().map(lambda v: comum.pct(v, 3)),
}), hide_index=True)
st.caption("Fonte: TSE, arquivos transmitidos para totalização (RDV) e resultado oficial de Governador.")
com_diferenca = rdv[rdv["diferenca_rdv_oficial"] != 0]
if len(com_diferenca):
    st.markdown("**Por que há diferença em " + str(len(com_diferenca)) + " disputas:**\n" + "\n".join(
        f"- **{d['disputa']} ({diferenca(d['diferenca_rdv_oficial'])}):** {d['explicacao']}"
        for _, d in com_diferenca.iterrows()))
st.page_link("paginas/nulos.py", label="Ver a análise que usa o RDV: Votos no número errado", icon=":material/dialpad:")

# ---------------------------------------------------------------------------
# 4. Lei de Benford
# ---------------------------------------------------------------------------
st.header("4. Lei de Benford: por que ela não prova fraude", anchor="benford")
benford = comum.ler("conferencia_benford")
totais = benford.groupby("nm_urna")["total"].first().sort_values(ascending=False)
finalistas = sorted(totais.index[:2])
cores = comum.cores_finalistas(finalistas)
st.markdown(
    "A lei de Benford é uma regularidade que aparece em muitos conjuntos de números que vão de unidades a "
    "milhões, como a população das cidades: o primeiro dígito é 1 em cerca de 30% dos casos, 2 em 18%, e a "
    "frequência cai até o 9, que aparece em menos de 5%. Às vezes ela é usada para \"testar\" eleições: se os "
    "votos não seguem a curva, haveria fraude. Abaixo, o teste feito do mesmo jeito para os dois candidatos a "
    "Presidente mais votados em 2026, e por que o resultado não diz nada sobre fraude."
)


def grafico_digitos(nivel: str, posicao: int, rotulo: str) -> tuple[go.Figure, pd.DataFrame]:
    dados = benford[(benford["nivel"] == nivel) & (benford["posicao"] == posicao)
                    & benford["nm_urna"].isin(finalistas)]
    fig = go.Figure()
    for nome in finalistas:
        d = dados[dados["nm_urna"] == nome]
        fig.add_trace(go.Bar(
            x=d["digito"], y=100 * d["proporcao"], name=nome, marker_color=cores[nome],
            hovertemplate=f"{nome}<br>Dígito %{{x}}: %{{y:.1f}}% {rotulo}<extra></extra>"))
    esperado = dados.drop_duplicates("digito")
    fig.add_trace(go.Scatter(
        x=esperado["digito"], y=100 * esperado["benford"], name="Curva de Benford (esperado)",
        mode="lines+markers", line=dict(color=comum.TINTA_2, width=2), marker=dict(size=8),
        hovertemplate="Curva de Benford<br>Dígito %{x}: %{y:.1f}%<extra></extra>"))
    comum.estilo(fig, altura=360)
    fig.update_layout(barmode="group", bargroupgap=0.12, margin=dict(t=56))
    fig.update_xaxes(tickmode="array", tickvals=esperado["digito"].tolist(),
                     title=f"{'Primeiro' if posicao == 1 else 'Segundo'} dígito do número de votos")
    fig.update_yaxes(ticksuffix="%", title=None)
    tabela = dados.pivot(index="digito", columns="nm_urna", values="proporcao").reset_index()
    tabela = tabela.merge(esperado[["digito", "benford"]], on="digito")
    tabela = pd.DataFrame({
        "Dígito": tabela["digito"],
        **{nome: tabela[nome].map(comum.pct) for nome in finalistas},
        "Curva de Benford": tabela["benford"].map(comum.pct),
    })
    return fig, tabela


def desvio(nivel: str, nome: str, posicao: int = 1) -> float:
    d = benford[(benford["nivel"] == nivel) & (benford["nm_urna"] == nome) & (benford["posicao"] == posicao)]
    return float((d["proporcao"] - d["benford"]).abs().mean())


fig, tabela = grafico_digitos("seção", 1, "das seções")
titulo_grafico(
    "Primeiro dígito dos votos de cada candidato por seção (Presidente, 1º turno de 2026)",
    "a barra do dígito 1 mostra em quantas seções (em %) o candidato teve um número de votos que começa com 1 "
    "(1, de 10 a 19 ou de 100 a 199 votos). A linha é a curva de Benford. Os dois candidatos ficam longe da "
    "curva, e do mesmo jeito: muitas seções no 1, poucas no 2, 3 e 4.")
comum.mostrar(fig, tabela=tabela, fonte=FONTE_SECOES, chave="benford_secao")

tamanho = comum.ler("conferencia_tamanho_secoes").iloc[0]
st.markdown("##### Por que isso acontece: numa seção cabem poucas centenas de eleitores")
st.markdown(
    f"A lei de Benford só vale para números que variam em várias ordens de grandeza (de dezenas a milhares, "
    f"milhões). Numa seção votam, em média, **{comum.numero(tamanho['votantes_media'])} pessoas** (em 90% das "
    f"seções, entre {comum.numero(tamanho['votantes_p05'])} e {comum.numero(tamanho['votantes_p95'])}). Então o "
    f"número de votos de um candidato numa seção fica quase sempre entre algumas dezenas e 300. Quem costuma "
    f"ter de 100 a 199 votos por seção tem muitos \"1\"; quem costuma ter de 50 a 99 tem muitos \"5\" a \"9\". O "
    f"primeiro dígito depende do tamanho da seção e de quanto o candidato é votado naquele lugar, não de "
    f"manipulação."
)
faixas = comum.ler("conferencia_votos_por_secao")
faixas = faixas[faixas["nm_urna"].isin(finalistas)].copy()
faixas["pct"] = faixas["secoes"] / faixas.groupby("nm_urna")["secoes"].transform("sum")
fig = go.Figure()
fig.add_vrect(x0=100, x1=200, fillcolor=comum.NEUTRO, line_width=0, layer="below",
              annotation_text="de 100 a 199 votos:<br>começa com 1", annotation_position="top left",
              annotation_font=dict(color=comum.TINTA_2, size=12))
for nome in finalistas:
    d = faixas[(faixas["nm_urna"] == nome) & (faixas["faixa"] < 500)]
    fig.add_trace(go.Scatter(
        x=d["faixa"] + 5, y=100 * d["pct"], name=nome, mode="lines", line=dict(color=cores[nome], width=2),
        customdata=[f"{f} a {f + 9}" for f in d["faixa"]],
        hovertemplate=f"{nome}<br>De %{{customdata}} votos: %{{y:.1f}}% das seções<extra></extra>"))
comum.estilo(fig, altura=340)
fig.update_layout(margin=dict(t=56))
fig.update_xaxes(title="Votos na seção", range=[0, 450])
fig.update_yaxes(ticksuffix="%", title=None, range=[0, 100 * faixas["pct"].max() * 1.3])
tabela_faixas = faixas.pivot(index="faixa", columns="nm_urna", values="pct").reset_index()
tabela_faixas = pd.DataFrame({
    "Votos na seção": [f"{f} a {f + 9}" if f < 500 else "500 ou mais" for f in tabela_faixas["faixa"]],
    **{nome: tabela_faixas[nome].map(comum.pct) for nome in finalistas},
})
titulo_grafico(
    "Quantos votos cada candidato teve por seção (Presidente, 1º turno de 2026)",
    "cada linha mostra em quantas seções (em %) o candidato teve aquela quantidade de votos. Quase tudo fica "
    "entre 10 e 300 votos: um intervalo pequeno demais para a lei de Benford valer. A faixa sombreada é onde o "
    "primeiro dígito é 1.")
comum.mostrar(fig, tabela=tabela_faixas, fonte=FONTE_SECOES, chave="votos_por_secao")

st.markdown(
    f"**Por município, os números variam muito mais, e a curva aparece.** Os votos válidos vão de "
    f"{comum.numero(resumo['municipio_menor_validos'])} em {municipio(resumo['municipio_menor'])} a "
    f"{comum.numero(resumo['municipio_maior_validos'])} em {municipio(resumo['municipio_maior'])}: várias ordens "
    f"de grandeza."
)
fig, tabela = grafico_digitos("município", 1, "dos municípios")
titulo_grafico(
    "Primeiro dígito dos votos de cada candidato por município (Presidente, 1º turno de 2026)",
    "a mesma conta do primeiro gráfico, agora com o total de votos de cada candidato em cada município. As barras "
    "dos dois candidatos ficam bem mais perto da curva.")
comum.mostrar(fig, tabela=tabela, fonte="TSE, resultado oficial por município (inclui as cidades do exterior).",
              chave="benford_municipio")

a, b = finalistas
st.markdown(
    f"**Distância média entre as barras e a curva:** por seção, {comum.pontos(desvio('seção', a))} para {a} e "
    f"{comum.pontos(desvio('seção', b))} para {b}; por município, {comum.pontos(desvio('município', a))} e "
    f"{comum.pontos(desvio('município', b))}. Mesmo por município, ficar um pouco mais perto ou mais longe da "
    f"curva não indica nada: depende de como os votos de cada candidato se dividem entre municípios grandes e "
    f"pequenos."
)

with st.expander("A mesma conta para todos os candidatos"):
    todos = sorted(benford["nm_urna"].unique())
    st.dataframe(pd.DataFrame({
        "Candidato": todos,
        "Por seção": [comum.pontos(desvio("seção", n)) for n in todos],
        "Por município": [comum.pontos(desvio("município", n)) for n in todos],
    }), hide_index=True, height=altura_tabela(len(todos)))
    st.caption("Distância média, em pontos, entre a % de cada primeiro dígito e a curva de Benford. Nenhum "
               "candidato segue a curva por seção, e a distância acompanha o tamanho típico dos números: quem "
               "tem de alguns votos a algumas dezenas por seção (duas ordens de grandeza) fica mais perto; quem "
               "tem de 1 a 9 votos na maior parte das seções fica mais longe.")

with st.expander("E o segundo dígito?"):
    st.markdown(
        "Outra versão do teste olha o **segundo** dígito (pela lei de Benford, ele vai de 12% para o 0 a 8,5% "
        f"para o 9). Por seção, os dois candidatos também ficam fora da curva (em média, a "
        f"{comum.pontos(desvio('seção', a, 2))} para {a} e {comum.pontos(desvio('seção', b, 2))} para {b}), "
        "pelo mesmo motivo: o tamanho das seções limita os números possíveis."
    )
    fig, tabela = grafico_digitos("seção", 2, "das seções")
    comum.mostrar(fig, tabela=tabela, fonte=FONTE_SECOES, chave="benford_segundo")

st.info(
    "**O que diz a literatura.** Deckert, Myagkov e Ordeshook (2011), \"Benford's Law and the Detection of "
    "Election Fraud\" (revista *Political Analysis*), testaram esse tipo de análise em eleições reais e "
    "simuladas e concluíram que ela não serve, sozinha, para detectar fraude: pode apontar problema em eleição "
    "sem fraude e deixar de apontar onde houve.\n\n"
    "**Resumo:** fugir da curva de Benford nos votos por seção é o esperado em qualquer eleição com seções "
    "pequenas, para qualquer candidato. Não é indício de fraude, e ficar perto da curva também não seria prova "
    "de que está tudo certo. O que dá para conferir com dados públicos é se as somas fecham: a soma dos "
    "boletins das seções é igual ao resultado oficial (parte 1 desta página).",
    icon=":material/menu_book:",
)

# ---------------------------------------------------------------------------
# 5. Checagens automáticas
# ---------------------------------------------------------------------------
st.header("5. Checagens automáticas do projeto", anchor="checagens")
st.markdown(
    "Toda vez que o banco de dados é montado (`scripts/montar_base.py`), as checagens de `sql/checagens/` rodam "
    "sozinhas. Cada uma procura linhas com problema; o esperado é nenhuma. O resultado abaixo é da última vez "
    "que os dados desta página foram gerados."
)
TITULOS = {
    "01_candidatos_batem_com_validos.sql": "Votos dos candidatos × votos válidos (2002 a 2026)",
    "02_municipio_sem_segundo_turno.sql": "Todo município do 1º turno tem 2º turno",
    "03_comparecimento_fecha.sql": "O comparecimento fecha",
    "04_municipio_fora_do_cadastro.sql": "Todo município tem código do IBGE",
    "coletor ao vivo": "Coletor ao vivo × total do Brasil",
}
checagens = comum.ler("conferencia_checagens")
linhas = []
for _, c in checagens.iterrows():
    titulo = TITULOS.get(c["checagem"], c["checagem"])
    unidade = "votos de diferença" if c["checagem"] == "coletor ao vivo" else "linhas com problema"
    if c["linhas_com_problema"] == 0:
        resultado = ":material/check_circle: Resultado: nenhum problema"
    else:
        resultado = f":material/error: Resultado: {comum.numero(c['linhas_com_problema'])} {unidade}"
    linhas.append(f"- **{titulo}.** {c['o_que_confere']} {resultado}.")
st.markdown("\n".join(linhas))

fecha = comum.ler("conferencia_comparecimento_fecha")
f2006 = fecha[(fecha["ano"] == 2006) & (fecha["turno"] == 1)].iloc[0]
outros_anos = fecha[fecha["ano"] != 2006]["votos_que_nao_fecham"].abs().sum()
st.markdown("##### O que as checagens já encontraram")
st.markdown(
    f"- **{votos(f2006['votos_que_nao_fecham'])} de 2006 que não fecham.** Nos próprios arquivos do TSE, o "
    f"comparecimento de 2006 é maior que a soma de válidos, brancos e nulos em "
    f"{comum.numero(f2006['votos_que_nao_fecham'])} votos "
    f"({comum.pct(f2006['votos_que_nao_fecham'] / f2006['comparecimento'], 2)} do total), nos dois turnos, sem "
    f"coluna que explique. A checagem do comparecimento tolera diferenças pequenas e o caso fica registrado. "
    f"{'Nas outras eleições, de 2002 a 2026, a conta fecha voto a voto.' if outros_anos == 0 else ''}\n"
    f"- **Votos no número {resumo['nr_fora']} em 2026.** {votos(resumo['votos_fora'])} aparecem no arquivo das "
    f"seções e não no resultado oficial, porque contam como nulos (parte 1).\n"
    "- **Voto em trânsito como se fosse uma UF.** Em 2010, os votos em trânsito aparecem nos arquivos com a "
    "UF \"VT\"; o exterior aparece como \"ZZ\".\n"
    "- **RDV:** uma urna do RS com um formato que o leitor não reconhece e votos em candidaturas indeferidas "
    "em SC e na BA (parte 3).\n"
    "- **Pegadinhas dos arquivos:** codificação Latin-1, `;` como separador, códigos como `#NULO#` e `-1` para "
    "\"sem informação\", e código de município do TSE diferente do código do IBGE."
)

# ---------------------------------------------------------------------------
# 6. Seções fora do padrão
# ---------------------------------------------------------------------------
st.header("6. Seções fora do padrão", anchor="fora-do-padrao")
fora = comum.ler("conferencia_secoes_fora_padrao").set_index("situacao")
st.markdown(
    f"Entre {comum.numero(resumo['secoes_detalhe'])} seções, sempre há casos fora do comum. Contamos alguns, "
    f"com o mesmo critério para todas as seções. **Ponto de atenção não é acusação:** aqui estão as contagens e "
    f"por que esses casos existem; nenhuma seção é tratada como suspeita. Para comparar: metade das seções tem "
    f"mais de {comum.numero(tamanho['aptos_mediana'])} eleitores."
)
pequenas = fora.loc["menos de 50 eleitores"]
um_so = fora.loc["todos os votos válidos para um só candidato"]
cedula = fora.loc["votação em cédula (sistema de apuração)"]
red = fora.loc["boletim recuperado da urna (RED)"]
nao_instaladas = fora.loc["não instalada"]
sem_voto = fora.loc["instalada, sem nenhum voto"]
c1, c2, c3 = st.columns(3)
with c1:
    comum.cartao("Seções com menos de 50 eleitores", comum.numero(pequenas["secoes"]))
with c2:
    comum.cartao("Com todos os votos válidos para um só candidato", comum.numero(um_so["secoes"]))
with c3:
    comum.cartao("Com votação em cédula ou boletim recuperado", comum.numero(cedula["secoes"] + red["secoes"]))

TIPOS = ["presídio ou unidade para adolescentes", "outro", "exterior", "aldeia ou escola indígena"]
ROTULOS = {"presídio ou unidade para adolescentes": "Presídios e unidades<br>para adolescentes",
           "outro": "Outros locais", "exterior": "Exterior",
           "aldeia ou escola indígena": "Aldeias e escolas<br>indígenas"}
contagem = pd.DataFrame({"tipo": TIPOS, "secoes": [int(pequenas[t]) for t in TIPOS]}).sort_values("secoes")
fig = go.Figure(go.Bar(
    x=contagem["secoes"], y=[ROTULOS[t] for t in contagem["tipo"]], orientation="h", marker_color=comum.SERIE,
    width=0.4, hovertemplate="%{y}: %{x} seções<extra></extra>"))
comum.estilo(fig, altura=250, legenda=False)
fig.update_xaxes(title="Seções", showgrid=True, gridcolor=comum.GRADE)
fig.update_yaxes(showgrid=False, title=None, ticksuffix="  ")
titulo_grafico(
    "Seções com menos de 50 eleitores, por tipo de local",
    "o tipo de local vem do nome do local de votação (por exemplo, \"Penitenciária...\", \"Fundação Casa\", "
    "\"Aldeia...\"). Um local indígena sem \"aldeia\" ou \"indígena\" no nome conta como \"outros locais\".")
decrescente = contagem.iloc[::-1]
comum.mostrar(fig, tabela=pd.DataFrame({"Tipo de local": [ROTULOS[t].replace("<br>", " ") for t in decrescente["tipo"]],
                                        "Seções": decrescente["secoes"]}),
              fonte="TSE, detalhe da apuração por seção eleitoral (Presidente, 1º turno de 2026).", chave="pequenas")

candidatos_um_so = {c.removeprefix("candidato: "): int(v) for c, v in um_so.items()
                    if c.startswith("candidato: ") and pd.notna(v)}
frase_candidatos = " e ".join(f"{q} para {nome}" for nome, q in sorted(candidatos_um_so.items()))
st.markdown(
    f"- **{comum.numero(pequenas['secoes'])} seções com menos de 50 eleitores.** A regra geral é de pelo menos 50 "
    f"eleitores por seção (Código Eleitoral, art. 117), com exceções autorizadas pela Justiça Eleitoral. Destas, "
    f"{comum.numero(pequenas['presídio ou unidade para adolescentes'])} ficam em presídios ou unidades de "
    f"internação de adolescentes, {comum.numero(pequenas['exterior'])} no exterior, "
    f"{comum.numero(pequenas['aldeia ou escola indígena'])} em aldeias ou escolas indígenas e "
    f"{comum.numero(pequenas['outro'])} em outros locais, em geral escolas, salões comunitários e postos de saúde "
    f"de comunidades rurais e ribeirinhas. A menor seção instalada tem {comum.numero(tamanho['aptos_min'])} "
    f"eleitores.\n"
    f"- **{comum.numero(um_so['secoes'])} seções com todos os votos válidos para um só candidato** "
    f"({comum.pct(um_so['secoes'] / resumo['secoes_detalhe'], 3)} das seções). Pelo nome do local, pelo menos "
    f"{comum.numero(um_so['aldeia ou escola indígena'])} ficam em aldeias ou escolas indígenas; as outras, em geral "
    f"em comunidades pequenas. São seções com poucos votantes (metade teve menos de "
    f"{comum.numero(um_so['votantes_mediana'])}). Foram {frase_candidatos}. Uma seção assim não indica "
    f"problema: o que dá para conferir é que os votos de cada seção somam o resultado oficial (parte 1).\n"
    f"- **{comum.numero(cedula['secoes'])} seções com votação em cédula de papel** "
    f"({comum.numero(cedula['exterior'])} no exterior). Os votos foram digitados depois no Sistema de Apuração. "
    f"É o procedimento previsto quando a urna eletrônica não pode ser usada.\n"
    f"- **{comum.numero(red['secoes'])} seções com o boletim recuperado.** A urna teve problema e o boletim foi "
    f"gerado pelo Recuperador de Dados (RED), que lê os votos gravados na memória da urna.\n"
    f"- **{comum.numero(nao_instaladas['secoes'])} seções não instaladas**, todas no exterior, com "
    f"{comum.numero(nao_instaladas['eleitores'])} eleitores no total, e "
    f"{comum.numero(sem_voto['secoes'])} instalada{'s' if sem_voto['secoes'] != 1 else ''} sem nenhum voto "
    f"(também no exterior). No arquivo, aparecem com zero votantes."
)

comum.rodape(metodologia="scripts/site_conferencia.py")
