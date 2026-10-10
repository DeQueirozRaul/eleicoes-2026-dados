import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import comum
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # para importar o pacote eleicoes

from eleicoes.acompanhamento import Acompanhamento  # noqa: E402
from eleicoes.ao_vivo import MINIMO_APURADO, Parametros  # noqa: E402
from eleicoes.tse_ao_vivo import FUSO_BRASILIA  # noqa: E402

PLACAR, PROJECAO = comum.SERIE, comum.DESTAQUE
CONFIG = json.loads((comum.DADOS / "ao_vivo_config.json").read_text(encoding="utf-8"))
INICIO = datetime.fromisoformat(CONFIG["inicio_apuracao"])
# Para testar fora da noite da eleição: AO_VIVO_ELEICAO=6257 (1º turno, já apurado)
ELEICAO = int(os.environ.get("AO_VIVO_ELEICAO", CONFIG["eleicao"]))
A, B = CONFIG["finalistas"]["A"], CONFIG["finalistas"]["B"]
CORES = comum.cores_finalistas([A["nm_urna"], B["nm_urna"]])
PRIMEIRO = sorted([A["nm_urna"], B["nm_urna"]])[0]   # o gráfico mostra o % do 1º em ordem alfabética

comum.cabecalho(
    "Apuração ao vivo",
    "O placar parcial engana, porque cada região apura num ritmo diferente. A projeção estima, a cada minuto, "
    "como os votos que ainda faltam devem se dividir.",
)


@st.cache_resource(show_spinner=False)
def acompanhamento(eleicao: int) -> Acompanhamento:
    """Um só acompanhamento por processo, compartilhado por todos os visitantes."""
    return Acompanhamento(
        eleicao=eleicao, cargo=CONFIG["cargo"], nr_a=A["nr_candidato"], nr_b=B["nr_candidato"],
        prior=comum.ler("ao_vivo_prior"), parametros=Parametros(**CONFIG["parametros"]),
    ).iniciar()


def pct_de(nome: str, pct_a: float) -> float:
    return pct_a if nome == A["nm_urna"] else 1 - pct_a


@st.fragment(run_every=60)
def painel_ao_vivo() -> None:
    acomp = acompanhamento(ELEICAO)
    historico = acomp.tabela_historico()
    agora = datetime.now(FUSO_BRASILIA)
    if historico.empty:
        if acomp.erro:
            st.warning(f"Não foi possível falar com o TSE na última tentativa ({acomp.erro}). "
                       "Tentando de novo em instantes.", icon=":material/sync_problem:")
        elif acomp.ultima_tentativa is None:
            st.info("Conectando ao TSE: a primeira leitura de todos os municípios leva de 2 a 3 minutos.",
                    icon=":material/hourglass_top:")
        else:
            st.info(f"O TSE ainda não começou a divulgar o 2º turno (verificado às "
                    f"{acomp.ultima_tentativa:%H:%M}). Esta página confere de novo a cada 5 minutos.",
                    icon=":material/schedule:")
        return

    ultima = historico.iloc[-1]
    secoes = ultima["pct_secoes_oficial"] if pd.notna(ultima["pct_secoes_oficial"]) else ultima["pct_secoes"]
    st.markdown(f"**{comum.pct(secoes, 2)} das seções apuradas** · atualizado às {ultima['momento']:%H:%M} "
                f"(horário de Brasília) · a página se atualiza sozinha a cada minuto")
    if acomp.erro:
        st.warning(f"A última leitura do TSE falhou ({acomp.erro}); os números abaixo são da leitura anterior.",
                   icon=":material/sync_problem:")

    publicavel = ultima["pct_secoes"] >= MINIMO_APURADO and pd.notna(ultima["pct_a_mediana"])
    colunas = st.columns(2)
    for coluna, nome in zip(colunas, sorted([A["nm_urna"], B["nm_urna"]])):
        oficial = ultima["pct_a_oficial"] if pd.notna(ultima["pct_a_oficial"]) else ultima["qt_a"] / max(
            ultima["qt_a"] + ultima["qt_b"], 1)
        if publicavel and not acomp.encerrado:
            mais = pct_de(nome, ultima["pct_a_mediana"])
            faixa = sorted([pct_de(nome, ultima["pct_a_inferior"]), pct_de(nome, ultima["pct_a_superior"])])
            chance = pct_de(nome, ultima["prob_a_vence"])
            detalhe = (f"projeção: {comum.pct(mais)} (margem de {comum.pct(faixa[0])} a {comum.pct(faixa[1])}) · "
                       f"{comum.pct(chance, 0)} de chance de terminar à frente")
        elif acomp.encerrado:
            detalhe = "resultado com 100% das seções apuradas"
        else:
            detalhe = "a projeção aparece a partir de 5% das seções apuradas"
        with coluna:
            comum.cartao(f"{nome} · placar oficial", comum.pct(pct_de(nome, oficial), 2), detalhe, cor=CORES[nome])

    if len(historico) > 1:
        fig = go.Figure()
        proj = historico[(historico["pct_secoes"] >= MINIMO_APURADO) & historico["pct_a_mediana"].notna()]
        y = lambda serie: serie.map(lambda v: pct_de(PRIMEIRO, v))  # noqa: E731
        if len(proj):
            fig.add_trace(go.Scatter(
                x=pd.concat([proj["momento"], proj["momento"][::-1]]),
                y=pd.concat([y(proj["pct_a_superior"]), y(proj["pct_a_inferior"])[::-1]]),
                fill="toself", fillcolor="rgba(235,104,52,0.14)", line=dict(width=0), hoverinfo="skip",
                name="margem da projeção (90%)"))
            fig.add_trace(go.Scatter(x=proj["momento"], y=y(proj["pct_a_mediana"]), mode="lines", name="projeção",
                                     line=dict(color=PROJECAO, width=2),
                                     hovertemplate="%{x|%H:%M}<br>projeção: %{y:.2%}<extra></extra>"))
        fig.add_trace(go.Scatter(x=historico["momento"], y=y(historico["pct_a_oficial"]), mode="lines",
                                 name="placar oficial", line=dict(color=PLACAR, width=2),
                                 hovertemplate="%{x|%H:%M}<br>placar: %{y:.2%}<extra></extra>"))
        fig.add_hline(y=0.5, line=dict(color=comum.EIXO, width=1))
        fig.update_xaxes(tickformat="%H:%M", title="horário de Brasília")
        outro = sorted([A["nm_urna"], B["nm_urna"]])[1]
        fig.update_yaxes(tickformat=".1%", title=f"% de {PRIMEIRO}")
        comum.estilo(fig, altura=380)
        comum.mostrar(fig, fonte="TSE (resultados divulgados ao vivo); projeção calculada pelo projeto.",
                      chave="ao_vivo")
        st.caption(f"**Como ler:** % de {PRIMEIRO} nos votos válidos (o de {outro} é 100% menos esse valor). A linha "
                   "azul é o placar oficial em cada momento; a laranja, a projeção, com a faixa da margem.")

    por_uf = acomp.placar_ufs.copy()
    if not por_uf.empty:
        with st.expander("Placar e % apurado por estado"):
            validos = (por_uf["qt_a"] + por_uf["qt_b"]).where(lambda v: v > 0)
            tabela = pd.DataFrame({"UF": por_uf["uf"].replace({"ZZ": "Exterior"}),
                                   "Seções apuradas": por_uf["pct_secoes"].map(lambda x: comum.pct(x, 0))})
            for nome in sorted([A["nm_urna"], B["nm_urna"]]):
                coluna = "qt_a" if nome == A["nm_urna"] else "qt_b"
                tabela[nome] = (por_uf[coluna] / validos).map(lambda x: "—" if pd.isna(x) else comum.pct(x))
            st.dataframe(tabela, hide_index=True)


agora = datetime.now(FUSO_BRASILIA)
if "AO_VIVO_ELEICAO" in os.environ or agora >= INICIO - timedelta(minutes=15):
    st.subheader("2º turno de 2026")
    painel_ao_vivo()
else:
    st.info(
        "**Na noite de 25/10**, a partir do fechamento das urnas (17h, horário de Brasília), esta página vai "
        "mostrar o placar oficial do 2º turno e a projeção, atualizados a cada minuto. Até lá, ela mostra o teste "
        "feito com as duas apurações de 2022.",
        icon=":material/schedule:",
    )

st.subheader("O teste: a noite de 2022 reproduzida seção por seção")
st.markdown(
    "Usando a hora em que cada boletim de urna chegou ao TSE, reconstruímos a apuração de 2022 minuto a minuto e "
    "rodamos a projeção como se fosse aquela noite, sem saber o resultado final. O gráfico mostra o % do "
    "1º colocado do 1º turno (LULA) nos votos dos dois primeiros (o de JAIR BOLSONARO é 100% menos esse valor)."
)


def momento_em(teste: pd.DataFrame, fracao: float) -> pd.Series:
    return teste[teste["pct_secoes"] >= fracao].iloc[0]


def mostrar_noite(teste: pd.DataFrame, turno: int) -> None:
    final = teste["pct_a_final"].iloc[0]
    publicada = teste[teste["pct_secoes"] >= MINIMO_APURADO]
    em10, em50 = momento_em(teste, 0.10), momento_em(teste, 0.50)
    cobertura = publicada["final_no_intervalo"].mean()

    c1, c2, c3 = st.columns(3)
    with c1:
        comum.cartao("Com 10% das seções apuradas", comum.pontos(em10["erro_projecao_pp"] / 100),
                     f"de erro da projeção, contra {comum.pontos(em10['erro_placar_pp'] / 100)} do placar oficial",
                     cor=PROJECAO)
    with c2:
        comum.cartao("Com metade apurada", comum.pontos(em50["erro_projecao_pp"] / 100),
                     f"de erro da projeção, contra {comum.pontos(em50['erro_placar_pp'] / 100)} do placar oficial",
                     cor=PROJECAO)
    with c3:
        comum.cartao("Resultado final dentro da margem", comum.pct(cobertura, 0),
                     "das atualizações da projeção (margem de 90%)")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pd.concat([publicada["momento"], publicada["momento"][::-1]]),
        y=pd.concat([publicada["pct_a_superior"], publicada["pct_a_inferior"][::-1]]),
        fill="toself", fillcolor="rgba(235,104,52,0.14)", line=dict(width=0), hoverinfo="skip",
        name="margem da projeção (90%)"))
    fig.add_trace(go.Scatter(
        x=teste["momento"], y=teste["pct_a_apurado"], mode="lines", name="placar oficial naquele momento",
        line=dict(color=PLACAR, width=2), customdata=teste["pct_secoes"],
        hovertemplate="%{x|%H:%M}<br>placar: %{y:.1%}<br>seções apuradas: %{customdata:.0%}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=publicada["momento"], y=publicada["pct_a_mediana"], mode="lines", name="projeção",
        line=dict(color=PROJECAO, width=2), customdata=publicada[["pct_a_inferior", "pct_a_superior"]],
        hovertemplate="%{x|%H:%M}<br>projeção: %{y:.1%} (margem %{customdata[0]:.1%} a "
                      "%{customdata[1]:.1%})<extra></extra>"))
    fig.add_hline(y=0.5, line=dict(color=comum.EIXO, width=1))
    fig.add_hline(y=final, line=dict(color=comum.TINTA_2, width=1),
                  annotation_text=f"resultado final: {comum.pct(final)}", annotation_position="top right",
                  annotation_font=dict(color=comum.TINTA_2, size=12))
    fig.update_xaxes(tickformat="%H:%M", title="horário de Brasília")
    fig.update_yaxes(tickformat=".0%", title="% de LULA nos votos dos dois primeiros",
                     range=[min(0.40, teste["pct_a_apurado"].min() - 0.01), max(0.60, teste["pct_a_apurado"].max() + 0.01)])
    comum.estilo(fig, altura=430)

    tabela = teste.iloc[::5]
    comum.mostrar(
        fig,
        tabela=pd.DataFrame({
            "Horário": tabela["momento"].dt.strftime("%H:%M"),
            "Seções apuradas": tabela["pct_secoes"].map(lambda x: comum.pct(x, 0)),
            "Placar oficial (LULA)": tabela["pct_a_apurado"].map(comum.pct),
            "Projeção (LULA)": [comum.pct(m) if s >= MINIMO_APURADO else "—"
                                for m, s in zip(tabela["pct_a_mediana"], tabela["pct_secoes"])],
            "Erro do placar": tabela["erro_placar_pp"].map(lambda x: comum.pontos(x / 100)),
            "Erro da projeção": [comum.pontos(e / 100) if s >= MINIMO_APURADO else "—"
                                 for e, s in zip(tabela["erro_projecao_pp"], tabela["pct_secoes"])],
        }),
        fonte=f"TSE (boletins de urna e histórico da totalização do {turno}º turno de 2022); cálculo do projeto.",
        chave=f"noite_{turno}",
    )


abas = st.tabs(["2º turno de 2022", "1º turno de 2022"])
with abas[0]:
    mostrar_noite(comum.ler("apuracao_2022_2t"), 2)
    st.caption(
        "**Como ler:** a linha azul é o placar que o TSE mostrava em cada momento; a laranja, a projeção, com a "
        "faixa da margem. Naquela noite o placar oficial só virou às 18h44, com 68% apurado; a projeção ficou do "
        "lado do vencedor desde que começou a ser publicada (5% apurado)."
    )
with abas[1]:
    mostrar_noite(comum.ler("apuracao_2022_1t"), 1)
    st.caption(
        "**Como ler:** no 1º turno, o placar considera só os dois primeiros colocados. Os municípios pequenos "
        "apuram primeiro e votaram diferente das capitais, e por isso o placar parcial ficou longe do final por "
        "horas."
    )

st.subheader("Como a projeção funciona")
st.markdown(
    """
1. **Em cada município**, estima quantos votos ainda faltam apurar e como devem se dividir, partindo do resultado
   do 1º turno e da mudança típica entre turnos.
2. **Aprende com o próprio erro durante a noite:** se nos municípios já apurados de um estado a estimativa erra
   1 ponto para o mesmo lado, corrige isso no que falta apurar naquele estado (e no país).
3. **Leva em conta o tamanho dos municípios**, porque os pequenos apuram primeiro e votam diferente das capitais.
4. **Só aparece a partir de 5% das seções apuradas**, porque antes disso oscila demais.

O teste de 2022 ajudou a desenhar a projeção; o teste realmente independente será a noite de 25/10/2026,
e o resultado será publicado aqui, acertando ou errando.
"""
)
comum.rodape("docs/previsao.md")
