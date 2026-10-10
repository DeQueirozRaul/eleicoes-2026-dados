import comum
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

comum.cabecalho(
    "Previsão do 2º turno",
    "O que o resultado do 1º turno, sozinho, diz sobre o 2º turno de 25/10. Não é pesquisa eleitoral: "
    "o modelo não entrevista ninguém e usa só resultados oficiais do TSE.",
)

nacional = comum.ler("previsao_nacional")
p = nacional[nacional["variante"] == "modelo principal"].iloc[0]
A, B = p["finalista_a"], p["finalista_b"]
CORES = comum.cores_finalistas([A, B])


def faixa(linha, nome: str) -> tuple[float, float, float, float]:
    """(mais provável, limite inferior, limite superior, chance de terminar à frente) de `nome`."""
    if nome == A:
        return linha["pct_a_mediana"], linha["pct_a_inferior"], linha["pct_a_superior"], linha["prob_a_vence"]
    return (1 - linha["pct_a_mediana"], 1 - linha["pct_a_superior"], 1 - linha["pct_a_inferior"],
            1 - linha["prob_a_vence"])


# --- resumo ------------------------------------------------------------------
st.subheader("O resultado do 1º turno não aponta quem fica à frente")
colunas = st.columns(2)
for coluna, nome in zip(colunas, sorted([A, B])):
    mais_provavel, inferior, superior, chance = faixa(p, nome)
    with coluna:
        comum.cartao(nome, comum.pct(mais_provavel),
                     f"dos votos válidos (entre {comum.pct(inferior)} e {comum.pct(superior)} em 90% dos cenários) · "
                     f"{comum.pct(chance, 0)} de chance de terminar à frente", cor=CORES[nome])

fig = go.Figure()
for nome in sorted([A, B], reverse=True):
    mais_provavel, inferior, superior, _ = faixa(p, nome)
    fig.add_trace(go.Scatter(
        x=[inferior, superior], y=[nome, nome], mode="lines", line=dict(color=CORES[nome], width=10),
        opacity=0.35, showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=[mais_provavel], y=[nome], mode="markers", name=nome,
        marker=dict(color=CORES[nome], size=14, line=dict(color=comum.SUPERFICIE, width=2)),
        hovertemplate=f"<b>{nome}</b><br>mais provável: %{{x:.1%}}<br>"
                      f"faixa de 90%: {comum.pct(inferior)} a {comum.pct(superior)}<extra></extra>"))
fig.add_vline(x=0.5, line=dict(color=comum.EIXO, width=1))
fig.update_xaxes(tickformat=".0%", range=[0.38, 0.62], title="% dos votos válidos no 2º turno")
comum.estilo(fig, altura=220, legenda=False)
st.markdown("**% previsto dos votos válidos no 2º turno**")
comum.mostrar(
    fig,
    tabela=pd.DataFrame([{
        "Candidato": nome,
        "Mais provável": comum.pct(faixa(p, nome)[0]),
        "Faixa de 90% dos cenários": f"{comum.pct(faixa(p, nome)[1])} a {comum.pct(faixa(p, nome)[2])}",
        "Chance de terminar à frente": comum.pct(faixa(p, nome)[3], 0),
    } for nome in sorted([A, B])]),
    fonte="TSE (resultados de 2002 a 2026); cálculo do projeto com 20 mil cenários simulados.",
)
st.caption(
    "**Como ler:** a bolinha é o resultado mais provável; a barra é a faixa onde o resultado caiu em 90% dos "
    "cenários simulados. As faixas dos dois se sobrepõem quase inteiras: só com o 1º turno, não dá para "
    "saber quem fica à frente."
)

# --- por que a margem é grande ------------------------------------------------
st.subheader("Por que a margem de erro é tão grande")
primeiro_turno = comum.ler("inicio_presidente_1t_2026").set_index("nm_urna")["pct_validos"]
vantagem = primeiro_turno[A] - primeiro_turno[B]
eliminados = 1 - primeiro_turno[A] - primeiro_turno[B]
st.markdown(
    f"""
O modelo aprende com os seis 2º turnos desde 2002 como o placar muda entre um turno e outro.
Duas coisas pesam em 2026:

- Em 5 das 6 eleições, quem liderou o 1º turno ficou com menos da metade dos votos dos candidatos
  eliminados. Em 2026, os eliminados somaram {comum.pct(eliminados)} dos votos válidos, e esse padrão compensa
  a vantagem de {comum.pontos(vantagem)} de {A} no 1º turno.
- Em 2006, o 2º colocado perdeu votos entre os turnos, um caso que nenhuma outra eleição mostrou. Com seis
  eleições só, um caso assim alarga muito a margem. Não há motivo objetivo para descartar uma eleição real,
  então o modelo principal usa todas.
"""
)
nomes_variantes = {"modelo principal": "Modelo principal",
                   "sem a eleição de 2006 no treino": "Sem a eleição de 2006",
                   "mudança igual em todos os municípios": "Mudança igual em todos os municípios"}
st.dataframe(pd.DataFrame([{
    "Versão do modelo": nomes_variantes.get(v["variante"], v["variante"]),
    **{f"{nome} (faixa de 90%)": f"{comum.pct(faixa(v, nome)[0])} ({comum.pct(faixa(v, nome)[1])} a "
                                 f"{comum.pct(faixa(v, nome)[2])})" for nome in sorted([A, B])},
    **{f"Chance de {nome} à frente": comum.pct(faixa(v, nome)[3], 0) for nome in sorted([A, B])},
} for _, v in nacional.iterrows()]), hide_index=True)
st.caption("Tirar 2006 estreita a faixa, mas seria escolher os dados para obter a resposta. "
           "A versão principal fica com todas as eleições.")

# --- por UF ------------------------------------------------------------------
st.subheader("Previsão por estado")
uf = comum.ler("previsao_uf").sort_values("pct_a_mediana")
uf["rotulo"] = uf["uf"].replace({"ZZ": "Exterior"})
uf["a_frente"] = uf["pct_a_mediana"].map(lambda x: A if x > 0.5 else B)
fig = go.Figure()
for nome in sorted([A, B]):
    parte = uf[uf["a_frente"] == nome]
    fig.add_trace(go.Scatter(
        x=parte["pct_a_mediana"], y=parte["rotulo"], mode="markers", name=f"mais provável: {nome} à frente",
        marker=dict(color=CORES[nome], size=10, line=dict(color=comum.SUPERFICIE, width=2)),
        error_x=dict(type="data", symmetric=False, array=parte["pct_a_superior"] - parte["pct_a_mediana"],
                     arrayminus=parte["pct_a_mediana"] - parte["pct_a_inferior"], color=comum.APAGADO,
                     thickness=1.5, width=0),
        customdata=parte[["pct_a_inferior", "pct_a_superior", "prob_a_vence"]],
        hovertemplate="<b>%{y}</b><br>" + A + ": %{x:.1%} (faixa %{customdata[0]:.1%} a %{customdata[1]:.1%})"
                      "<br>chance de " + A + " à frente: %{customdata[2]:.0%}<extra></extra>"))
fig.add_vline(x=0.5, line=dict(color=comum.EIXO, width=1))
fig.update_xaxes(tickformat=".0%", title=f"% previsto para {A} (o de {B} é 100% menos esse valor)")
fig.update_yaxes(categoryorder="array", categoryarray=uf["rotulo"].tolist(), showgrid=False)
comum.estilo(fig, altura=760)
comum.mostrar(
    fig,
    tabela=pd.DataFrame({
        "UF": uf["rotulo"],
        f"{A}: mais provável": uf["pct_a_mediana"].map(comum.pct),
        f"{A}: faixa de 90%": [f"{comum.pct(i)} a {comum.pct(s)}" for i, s in zip(uf["pct_a_inferior"], uf["pct_a_superior"])],
        f"Chance de {A} à frente": uf["prob_a_vence"].map(lambda x: comum.pct(x, 0)),
        f"Chance de {B} à frente": uf["prob_a_vence"].map(lambda x: comum.pct(1 - x, 0)),
    }).iloc[::-1],
    fonte="TSE; cálculo do projeto.",
)
st.caption(f"**Como ler:** cada linha é um estado. À direita da linha dos 50%, o mais provável é {A} à frente; "
           f"à esquerda, {B}. O traço cinza é a faixa de 90% dos cenários.")

# --- teste no passado ----------------------------------------------------------
st.subheader("O teste: cada eleição prevista sem ver o resultado dela")
validacao = comum.ler("previsao_validacao").sort_values("ano", ascending=False)
validacao["rotulo"] = validacao["ano"].astype(str) + ": " + validacao["finalista_a"]
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=validacao["pct_a_previsto"], y=validacao["rotulo"], mode="markers", name="previsto (com faixa de 90%)",
    marker=dict(color=comum.SERIE, size=10, line=dict(color=comum.SUPERFICIE, width=2)),
    error_x=dict(type="data", symmetric=False, array=validacao["pct_a_superior"] - validacao["pct_a_previsto"],
                 arrayminus=validacao["pct_a_previsto"] - validacao["pct_a_inferior"], color=comum.APAGADO,
                 thickness=1.5, width=0),
    hovertemplate="<b>%{y}</b><br>previsto: %{x:.1%}<extra></extra>"))
fig.add_trace(go.Scatter(
    x=validacao["pct_a_real"], y=validacao["rotulo"], mode="markers", name="resultado real",
    marker=dict(color=comum.TINTA, size=11, symbol="diamond", line=dict(color=comum.SUPERFICIE, width=2)),
    hovertemplate="<b>%{y}</b><br>real: %{x:.1%}<extra></extra>"))
fig.add_vline(x=0.5, line=dict(color=comum.EIXO, width=1))
fig.update_xaxes(tickformat=".0%", title="% do 1º colocado do 1º turno, no 2º turno")
comum.estilo(fig, altura=330)
comum.mostrar(
    fig,
    tabela=pd.DataFrame({
        "Eleição": validacao["ano"],
        "Finalistas": validacao["finalista_a"] + " × " + validacao["finalista_b"],
        "Previsto": validacao["pct_a_previsto"].map(comum.pct),
        "Faixa de 90%": [f"{comum.pct(i)} a {comum.pct(s)}" for i, s in zip(validacao["pct_a_inferior"], validacao["pct_a_superior"])],
        "Real": validacao["pct_a_real"].map(comum.pct),
        "Erro": validacao["erro_nacional_pp"].map(lambda x: comum.pontos(x / 100)),
        "Real dentro da faixa?": validacao["real_dentro_do_intervalo"].map({True: "sim", False: "não"}),
    }),
    fonte="TSE; cálculo do projeto (cada eleição prevista com o modelo treinado nas outras cinco).",
)
erros = validacao["erro_nacional_pp"].abs()
st.caption(
    f"**Como ler:** o losango é o resultado real; a bolinha, o previsto. O real ficou dentro da faixa em "
    f"{int(validacao['real_dentro_do_intervalo'].sum())} das {len(validacao)} eleições. Em metade delas o erro foi de "
    f"até {comum.pontos(erros.median() / 100)}; o pior caso foi 2006 ({comum.pontos(erros.max() / 100)})."
)

# --- cenários -------------------------------------------------------------------
st.subheader("Cenários: para onde vão os eleitores dos eliminados")
st.markdown(
    "Não existe o voto de cada pessoa, só os totais por município. Cruzando os 5.570 municípios, dá para "
    "estimar de que lado do 2º turno de 2022 vieram os eleitores de cada candidato eliminado em 2026 "
    "(técnica chamada inferência ecológica)."
)
origem = comum.ler("previsao_origem_eliminados")
origem = origem[origem["agrupamento"] == "Região"].copy()
col_a = [c for c in origem.columns if c.startswith(f"lado de {A}")][0]
col_b = [c for c in origem.columns if c.startswith(f"lado de {B}")][0]
partes = {f"votou no lado de {A} em 2022": (col_a, CORES[A]),
          f"votou no lado de {B} em 2022": (col_b, CORES[B]),
          "não votou válido em 2022": ("sem_lado", comum.APAGADO)}
ordem = sorted(c for c in origem["candidato"] if c not in ("OUTROS", "TOTAL DOS ELIMINADOS")) + ["OUTROS", "TOTAL DOS ELIMINADOS"]
origem["rotulo"] = origem["candidato"].replace({"OUTROS": "Demais eliminados", "TOTAL DOS ELIMINADOS": "Total dos eliminados"})
origem = origem.set_index("candidato").loc[ordem].reset_index()
fig = go.Figure()
for nome, (coluna, cor) in partes.items():
    fig.add_trace(go.Bar(
        x=origem[coluna], y=origem["rotulo"], orientation="h", name=nome, marker=dict(color=cor,
        line=dict(color=comum.SUPERFICIE, width=2)), hovertemplate="%{y}<br>" + nome + ": %{x:.0%}<extra></extra>"))
fig.update_layout(barmode="stack", barcornerradius=0)
fig.update_xaxes(tickformat=".0%", range=[0, 1])
fig.update_yaxes(categoryorder="array", categoryarray=origem["rotulo"].tolist()[::-1], showgrid=False)
comum.estilo(fig, altura=300)
fig.update_layout(barcornerradius=0, legend_traceorder="normal")
comum.mostrar(
    fig,
    tabela=pd.DataFrame({"Eliminado": origem["rotulo"],
                         **{nome: origem[coluna].map(lambda x: comum.pct(x, 0)) for nome, (coluna, _) in partes.items()}}),
    fonte="TSE (1º turno de 2026 e 2º turno de 2022, por município); estimativa do projeto por região.",
)
st.caption(
    "**Atenção:** a estimativa de cada candidato muda bastante conforme se agrupam os municípios (por região, "
    "por UF ou o Brasil todo). O total dos eliminados é estável: vieram em proporções parecidas dos dois lados."
)

cenarios = comum.ler("previsao_cenarios")
menor, maior = cenarios["pct_a"].min(), cenarios["pct_a"].max()
st.markdown(
    f"""
Nos cenários, uma parte dos eleitores dos eliminados vota no finalista do lado em que votou em 2022
("fidelidade", de 50% a 90%), outra parte vota no outro finalista ("troca", de 5% a 30%) e o resto vota branco,
nulo ou não vai. Nunca 100% vai para um lado só.

**Em todos os {len(cenarios)} cenários, {A} fica entre {comum.pct(menor)} e {comum.pct(maior)}** dos votos
válidos ({B}: entre {comum.pct(1 - maior)} e {comum.pct(1 - menor)}), praticamente o placar do 1º turno entre os
dois. Como os eliminados vieram dos dois lados em proporções parecidas, a transferência deles quase não muda o
placar: o 2º turno deve depender mais de quem volta a votar, de quem deixa de ir e de quem troca de finalista.
"""
)
with st.expander("Ver todos os cenários"):
    tabela = cenarios.copy()
    tabela["fidelidade"] = tabela["fidelidade"].map(lambda x: comum.pct(x, 0))
    tabela["troca"] = tabela["troca"].map(lambda x: comum.pct(x, 0))
    tabela[A] = cenarios["pct_a"].map(lambda x: comum.pct(x, 2))
    tabela[B] = cenarios["pct_a"].map(lambda x: comum.pct(1 - x, 2))
    st.dataframe(tabela.drop(columns="pct_a").rename(columns={
        "agrupamento": "Agrupamento dos municípios", "fidelidade": "Fidelidade", "troca": "Troca"}), hide_index=True)

transf = comum.ler("previsao_validacao_transferencia")
st.markdown(
    f"**Por que os cenários não são a previsão principal:** testado como previsão nas eleições de 2006 a 2022, "
    f"esse método errou em média {comum.pontos(transf['erro_pp'].abs().mean() / 100)}, mais que o modelo principal "
    f"nas mesmas eleições (2,7 pontos). Por isso ele serve para montar cenários, não para prever."
)

comum.rodape("docs/previsao.md")
