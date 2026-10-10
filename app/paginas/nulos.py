import comum
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

comum.cabecalho(
    "Votos no número errado",
    "Quantos votos para Governador foram anulados porque o eleitor digitou o número de um candidato a "
    "Presidente, e se isso poderia ter mudado as disputas mais apertadas.",
)

d = comum.ler("nulos_disputas_apertadas")
d["disputa"] = d["uf"] + " " + d["ano"].astype(str)
d["vezes"] = d["nulos_com_numero_de_presidenciavel"] / d["votos_para_mudar"]
todas = comum.ler("nulos_todas_disputas")


def legivel(resultado: str) -> str:
    """'2º turno: A × B' -> '2º turno entre A e B'; 'eleito: A' -> 'A venceu no 1º turno'."""
    if resultado.startswith("eleito: "):
        return f"{resultado.removeprefix('eleito: ')} venceu no 1º turno"
    return resultado.replace("2º turno: ", "2º turno entre ").replace(" × ", " e ")


def mudanca(linha) -> str:
    m = linha["mudanca_mais_facil"]
    if m == "vencer no 1º turno":
        return f"{linha['mais_votado']} vencer no 1º turno"
    if m == "forçar um 2º turno":
        return "haver 2º turno"
    if m == "trocar quem vai ao 2º turno":
        return "mudar quem vai ao 2º turno"
    return m


def na_hipotese(linha) -> str:
    if not linha["hipotese_muda_resultado"]:
        return "Não mudaria"
    r = linha["resultado_na_hipotese"]
    if r.startswith("eleito: "):
        return f"Mudaria: {r.removeprefix('eleito: ')} venceria no 1º turno"
    return "Mudaria: haveria " + r.replace("2º turno: ", "2º turno entre ").replace(" × ", " e ")


# --- resumo ------------------------------------------------------------------
suficientes = int(d["em_jogo_maior_que_margem"].sum())
mudariam = d[d["hipotese_muda_resultado"]]
c1, c2, c3 = st.columns(3)
with c1:
    comum.cartao("Disputas de Governador muito apertadas", f"{len(d)} de {len(todas)}",
                 "poderiam mudar com menos de 1,5% dos votos válidos (2022 e 2026)")
with c2:
    comum.cartao("Votos anulados suficientes para mudar o resultado", f"{suficientes} de {len(d)}",
                 "dependendo de em quem o eleitor queria votar")
with c3:
    comum.cartao("Mudaria na hipótese da coligação", f"{len(mudariam)} de {len(d)}",
                 "todas em 2026: " + ", ".join(sorted(mudariam["uf"])))

st.markdown(
    """
**De onde vem o dado.** O boletim de urna só mostra o total de nulos. Mas o TSE publica também o **Registro
Digital do Voto (RDV)** de cada urna: a lista de todos os votos, embaralhados e sem identificar o eleitor, com os
dígitos digitados. Quando alguém digita para Governador um número sem candidato no estado (por exemplo, o número
de um candidato a Presidente), o voto é anulado e o número fica registrado. Lemos o RDV de todas as urnas das
disputas mais apertadas, voto a voto.
"""
)

# --- gráfico principal -----------------------------------------------------------
st.subheader("Os votos anulados com número de presidenciável eram suficientes para mudar o resultado?")
ordem = d.sort_values("vezes")
cores = [comum.DESTAQUE if v > 1 else comum.APAGADO for v in ordem["vezes"]]
fig = go.Figure()
# hastes saindo da linha "1×" (numa escala log, barras saindo da borda distorceriam o tamanho)
for (_, linha), cor in zip(ordem.iterrows(), cores):
    fig.add_trace(go.Scatter(x=[1, linha["vezes"]], y=[linha["disputa"]] * 2, mode="lines",
                             line=dict(color=cor, width=2), hoverinfo="skip", showlegend=False))
fig.add_trace(go.Scatter(
    x=ordem["vezes"], y=ordem["disputa"], mode="markers", showlegend=False,
    marker=dict(color=cores, size=12, line=dict(color=comum.SUPERFICIE, width=2)),
    customdata=ordem[["nulos_com_numero_de_presidenciavel", "votos_para_mudar"]],
    hovertemplate="<b>%{y}</b><br>anulados com número de presidenciável: %{customdata[0]:,.0f}"
                  "<br>votos que bastariam para mudar: %{customdata[1]:,.0f}<br>%{x:.1f} vezes<extra></extra>",
))
fig.add_vline(x=1, line=dict(color=comum.TINTA_2, width=1),
              annotation_text="igual ao que bastava", annotation_position="bottom right",
              annotation_font=dict(color=comum.TINTA_2, size=12))
fig.update_xaxes(type="log", title="votos anulados ÷ votos que bastariam para mudar o resultado (escala log)",
                 tickvals=[0.5, 1, 2, 5, 10, 20], ticktext=["metade", "1×", "2×", "5×", "10×", "20×"],
                 range=[-0.45, 1.35])
fig.update_yaxes(showgrid=False)
comum.estilo(fig, altura=380, legenda=False)
comum.mostrar(
    fig,
    tabela=pd.DataFrame({
        "Disputa": d["disputa"],
        "Votos que bastariam para mudar": d["votos_para_mudar"].map(comum.numero),
        "Anulados com nº de presidenciável": d["nulos_com_numero_de_presidenciavel"].map(comum.numero),
        "Quantas vezes": d["vezes"].map(lambda x: comum.numero(x, 1) + "×"),
    }),
    fonte="TSE: Registro Digital do Voto (RDV) e resultados de Governador; cálculo do projeto.",
)
st.caption(
    "**Como ler:** cada linha compara os votos anulados com o número de um candidato a Presidente com os votos que "
    "bastariam para mudar o resultado. Pontos laranja ficam à direita da linha: os anulados eram mais do que o necessário. "
    "Isso não quer dizer que o resultado mudaria, porque não se sabe em quem cada eleitor queria votar."
)

df26 = d[(d["uf"] == "DF") & (d["ano"] == 2026)]
if len(df26):
    x = df26.iloc[0]
    numero_mais = x["detalhe"].split(",")[0]
    digitos, qt = [t.strip() for t in numero_mais.split(":")]
    st.markdown(
        f"**Exemplo (DF, 2026):** {x['mais_votado']} teve {comum.pct(x['pct_mais_votado'], 2)} dos votos válidos; "
        f"faltaram **{comum.numero(x['votos_para_mudar'])} votos** para passar de 50% e vencer no 1º turno. "
        f"Nas urnas, **{comum.numero(x['nulos_com_numero_de_presidenciavel'])} votos para Governador** foram "
        f"anulados com o número de um candidato a Presidente ({qt} deles digitaram {digitos}), "
        f"{comum.numero(x['vezes'], 0)} vezes o que faltou."
    )

# --- tabela completa ----------------------------------------------------------------
st.subheader("As disputas, uma a uma")
st.markdown(
    "**Hipótese da coligação** (um cenário, não um fato): quem digitou o número de um candidato a Presidente "
    "queria votar no candidato a Governador cuja coligação ou federação inclui o partido daquele presidenciável. "
    "A regra vale igualmente para todos os números e partidos. Se o partido não estava em nenhuma coligação para "
    "Governador no estado, o voto continua nulo."
)
tabela = pd.DataFrame({
    "Disputa": d["disputa"],
    "Resultado oficial": d["resultado_oficial"].map(legivel),
    "Votos que bastariam para mudar": [f"{comum.numero(v)} para {mudanca(linha)}"
                                       for v, (_, linha) in zip(d["votos_para_mudar"], d.iterrows())],
    "Anulados com nº de presidenciável": d["nulos_com_numero_de_presidenciavel"].map(comum.numero),
    "Eram suficientes?": d["em_jogo_maior_que_margem"].map({True: "Sim", False: "Não"}),
    "Na hipótese da coligação": [na_hipotese(linha) for _, linha in d.iterrows()],
})
st.table(tabela, hide_index=True, border="horizontal")
st.caption(
    "Disputas da mais apertada para a menos apertada. Nos 2º turnos, os candidatos estão em ordem alfabética."
)

st.subheader("Que números foram digitados")
digitados = pd.DataFrame({
    "Disputa": d["disputa"],
    "Votos para Governador": d["votos_governador_rdv"].map(comum.numero),
    "Anulados com nº de presidenciável": [
        f"{comum.numero(n)} ({comum.pct(n / t)})"
        for n, t in zip(d["nulos_com_numero_de_presidenciavel"], d["votos_governador_rdv"])],
    "Números mais digitados (votos)": d["detalhe"],
})
st.table(digitados, hide_index=True, border="horizontal")
st.caption(
    "O número de um presidenciável só vira nulo quando nenhum candidato a Governador do estado tem aquele número; "
    "por isso o tamanho do fenômeno depende de quais partidos lançaram candidato em cada estado."
)

# --- ressalvas -------------------------------------------------------------------
st.subheader("Ressalvas")
st.markdown(
    """
- **O RDV não diz a intenção.** Parte desses votos pode ser nulo de propósito. A hipótese da coligação é só um
  cenário, não uma afirmação sobre o que o eleitor queria.
- **Só dá para ver a confusão que virou nulo.** Se o número digitado era de um candidato a Governador existente, o
  voto foi para ele e não dá para separar do voto intencional.
- **Voto nulo é uma escolha legítima e o resultado oficial é o do TSE.** A análise mede quanto a confusão entre os
  números de cargos diferentes pesa em disputas apertadas; não questiona o resultado.
- **A contagem confere com o oficial:** os votos de cada candidato contados no RDV bateram com o resultado do TSE
  (diferença zero em 6 disputas e de no máximo 0,02% nas outras 3; detalhes na página Conferência dos dados).
"""
)
comum.rodape("docs/nulos.md")
