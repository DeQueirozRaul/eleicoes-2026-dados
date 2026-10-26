import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import comum
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # para importar o pacote eleicoes

from eleicoes.acompanhamento import Acompanhamento  # noqa: E402
from eleicoes.ao_vivo import MINIMO_APURADO, Parametros  # noqa: E402
from eleicoes.tse_ao_vivo import FUSO_BRASILIA, ClienteTSE  # noqa: E402

PLACAR, PROJECAO = comum.SERIE, comum.DESTAQUE
# Depois de 99,5% apurado a margem fica mais estreita que os milésimos de ponto que ainda mudam;
# a cobertura da margem é medida de 5% a 99,5% apurado (2022 e 2026 do mesmo jeito)
FIM_COBERTURA = 0.995
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


def placar(linha) -> float | None:
    """% de A no placar oficial; None enquanto não há nenhum voto apurado (com zero
    votos, "100% menos 0%" daria 100% ao outro candidato, o que seria falso)."""
    if pd.notna(linha["pct_a_oficial"]):
        return float(linha["pct_a_oficial"])
    votos = linha["qt_a"] + linha["qt_b"]
    return float(linha["qt_a"] / votos) if votos > 0 else None


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
    oficial = placar(ultima)
    colunas = st.columns(2)
    for coluna, nome in zip(colunas, sorted([A["nm_urna"], B["nm_urna"]])):
        if oficial is None:
            detalhe = "aguardando os primeiros votos apurados"
        elif publicavel and not acomp.encerrado:
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
            valor = "—" if oficial is None else comum.pct(pct_de(nome, oficial), 2)
            comum.cartao(f"{nome} · placar oficial", valor, detalhe, cor=CORES[nome])

    historico["placar"] = [placar(linha) for _, linha in historico.iterrows()]
    historico = historico[historico["placar"].notna()]
    if len(historico) <= 1:
        st.caption("O gráfico da noite aparece quando chegarem os primeiros votos apurados.")
    else:
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
        fig.add_trace(go.Scatter(x=historico["momento"], y=y(historico["placar"].astype(float)), mode="lines",
                                 name="placar oficial", line=dict(color=PLACAR, width=2),
                                 hovertemplate="%{x|%H:%M}<br>placar: %{y:.2%}<extra></extra>"))
        fig.add_hline(y=0.5, line=dict(color=comum.EIXO, width=1))
        fig.update_xaxes(tickformat="%H:%M", title="horário de Brasília")
        outro = sorted([A["nm_urna"], B["nm_urna"]])[1]
        valores = pd.concat([y(historico["placar"].astype(float)), y(proj["pct_a_inferior"]), y(proj["pct_a_superior"])])
        fig.update_yaxes(tickformat=".1%", title=f"% de {PRIMEIRO}",
                         range=[max(0.0, min(valores.min(), 0.5) - 0.02), min(1.0, max(valores.max(), 0.5) + 0.02)])
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


# Para testar fora da noite da eleição: AO_VIVO_ELEICAO_GOVERNADOR=6259 (1º turno, já apurado)
ELEICAO_GOVERNADOR = int(os.environ.get("AO_VIVO_ELEICAO_GOVERNADOR", CONFIG.get("eleicao_governador", 6260)))
UF_NOMES = {"ac": "Acre", "am": "Amazonas", "df": "Distrito Federal", "es": "Espírito Santo",
            "rn": "Rio Grande do Norte", "to": "Tocantins"}


@st.cache_data(ttl=60, show_spinner=False)
def resultado_governador(eleicao: int, uf: str):
    """Placar oficial de Governador numa UF (um arquivo do TSE, guardado por 1 minuto)."""
    try:
        r = ClienteTSE().resultado(eleicao, 3, uf)
    except requests.RequestException:
        return None
    if r is None or r.candidatos.empty:
        return None
    return r.resumo, r.candidatos[["nr_candidato", "nm_urna", "sg_partido", "qt_votos"]].copy()


@st.fragment(run_every=60)
def painel_governador() -> None:
    ufs = CONFIG.get("ufs_governador_2t", ["df"])
    uf = st.selectbox("Estado", ufs, format_func=lambda u: UF_NOMES.get(u, u.upper()), key="uf_governador")
    dados = resultado_governador(ELEICAO_GOVERNADOR, uf)
    if dados is None:
        st.info("Não foi possível ler o resultado do TSE agora; a página tenta de novo em 1 minuto.",
                icon=":material/sync_problem:")
        return
    resumo, cand = dados
    cand = cand.sort_values("qt_votos", ascending=False).head(2)     # no 2º turno são só dois
    votos = int(cand["qt_votos"].sum())
    secoes = resumo["qt_secoes_totalizadas"] / resumo["qt_secoes"] if resumo["qt_secoes"] else 0.0
    gerado = resumo.get("dt_geracao")
    hora = f" · arquivo do TSE das {gerado:%H:%M}" if gerado is not None and pd.notna(gerado) else ""
    st.markdown(f"**{comum.pct(secoes, 2)} das seções apuradas**{hora}")
    nomes = sorted(cand["nm_urna"])
    cores = comum.cores_finalistas(nomes)
    for coluna, nome in zip(st.columns(2), nomes):
        linha = cand[cand["nm_urna"] == nome].iloc[0]
        with coluna:
            if votos == 0:
                comum.cartao(f"{nome} ({linha['sg_partido']}) · placar oficial", "—",
                             "aguardando os primeiros votos apurados", cor=cores[nome])
            else:
                comum.cartao(f"{nome} ({linha['sg_partido']}) · placar oficial",
                             comum.pct(linha["qt_votos"] / votos, 2),
                             f"{comum.numero(linha['qt_votos'])} votos", cor=cores[nome])
    st.caption("Placar oficial do TSE, nos votos dados aos dois candidatos (os válidos), sem projeção: a projeção "
               "deste site é só para Presidente. Atualiza a cada minuto.")


def resultado_2026(noite: pd.DataFrame) -> None:
    final = noite.iloc[-1]
    votos = {A["nm_urna"]: int(final["qt_a_final"]), B["nm_urna"]: int(final["qt_b_final"])}
    validos = sum(votos.values())
    st.markdown(f"**Resultado com {comum.pct(final['pct_secoes_final'], 2)} das seções apuradas** "
                "(votos válidos; quem proclama o resultado é o TSE)")
    for coluna, nome in zip(st.columns(2), sorted(votos)):
        with coluna:
            comum.cartao(nome, comum.pct(votos[nome] / validos, 2), f"{comum.numero(votos[nome])} votos",
                         cor=CORES[nome])


def governador_2026(gov: pd.DataFrame) -> None:
    ufs = CONFIG.get("ufs_governador_2t", ["df"])
    uf = st.selectbox("Estado", ufs, format_func=lambda u: UF_NOMES.get(u, u.upper()), key="uf_governador_final")
    da_uf = gov[gov["uf"] == uf.upper()]
    if da_uf.empty:
        st.info("A gravação da noite não tem o resultado deste estado.", icon=":material/info:")
        return
    ultima = da_uf[da_uf["momento"] == da_uf["momento"].max()]
    st.markdown(f"**{comum.pct(ultima['pct_secoes'].iloc[0], 2)} das seções apuradas** · última leitura da noite, "
                f"às {ultima['momento'].iloc[0]:%H:%M}")
    nomes = sorted(ultima["nm_urna"])
    cores = comum.cores_finalistas(nomes)
    for coluna, nome in zip(st.columns(2), nomes):
        linha = ultima[ultima["nm_urna"] == nome].iloc[0]
        with coluna:
            comum.cartao(f"{nome} ({linha['sg_partido']})", comum.pct(linha["pct_validos"], 2),
                         f"{comum.numero(linha['qt_votos'])} votos", cor=cores[nome])
    st.caption("Placar oficial do TSE nos votos válidos, sem projeção (a projeção deste site é só para Presidente).")


agora = datetime.now(FUSO_BRASILIA)
NOITE_GRAVADA = comum.existe("noite_2026_2t") and "AO_VIVO_ELEICAO" not in os.environ
if NOITE_GRAVADA:
    noite_2026 = comum.ler("noite_2026_2t")
    st.subheader("2º turno de 2026: resultado")
    resultado_2026(noite_2026)
elif "AO_VIVO_ELEICAO" in os.environ or agora >= INICIO - timedelta(minutes=15):
    st.subheader("2º turno de 2026")
    painel_ao_vivo()
    st.subheader("Governador, 2º turno (DF e outros 5 estados)")
    painel_governador()
else:
    st.info(
        "**Na noite de 25/10**, a partir do fechamento das urnas (17h, horário de Brasília), esta página vai "
        "mostrar o placar oficial do 2º turno e a projeção, atualizados a cada minuto. Até lá, ela mostra o teste "
        "feito com as duas apurações de 2022.",
        icon=":material/schedule:",
    )
    if INICIO - agora < timedelta(hours=12):
        @st.fragment(run_every=60)
        def aguardar_inicio() -> None:
            """Quem abriu a página antes das 16h45 entra no modo ao vivo sem precisar recarregar."""
            if datetime.now(FUSO_BRASILIA) >= INICIO - timedelta(minutes=15):
                st.rerun()

        aguardar_inicio()


def momento_em(teste: pd.DataFrame, fracao: float) -> pd.Series:
    return teste[teste["pct_secoes"] >= fracao].iloc[0]


def mostrar_noite(teste: pd.DataFrame, nome_a: str, eixo_y: str, fonte: str, chave: str) -> None:
    final = teste["pct_a_final"].iloc[0]
    # publicada a partir de 5% do que a projeção já tinha lido (em 2022, o mesmo que o % apurado)
    vista = teste["pct_secoes_projecao"] if "pct_secoes_projecao" in teste else teste["pct_secoes"]
    publicada = teste[(vista >= MINIMO_APURADO) & teste["pct_a_mediana"].notna()]
    em10, em50 = momento_em(teste, 0.10), momento_em(teste, 0.50)
    cobertura = publicada.loc[publicada["pct_secoes"] <= FIM_COBERTURA, "final_no_intervalo"].astype(float).mean()

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
                     "das atualizações da projeção entre 5% e 99,5% apurado (margem de 90%)")

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
    fig.update_yaxes(tickformat=".0%", title=eixo_y,
                     range=[min(0.40, teste["pct_a_apurado"].min() - 0.01), max(0.60, teste["pct_a_apurado"].max() + 0.01)])
    comum.estilo(fig, altura=430)

    tabela = teste.iloc[::5]
    publicado = (vista.loc[tabela.index] >= MINIMO_APURADO) & tabela["pct_a_mediana"].notna()
    comum.mostrar(
        fig,
        tabela=pd.DataFrame({
            "Horário": tabela["momento"].dt.strftime("%H:%M"),
            "Seções apuradas": tabela["pct_secoes"].map(lambda x: comum.pct(x, 0)),
            f"Placar oficial ({nome_a})": tabela["pct_a_apurado"].map(comum.pct),
            f"Projeção ({nome_a})": [comum.pct(m) if p else "—" for m, p in zip(tabela["pct_a_mediana"], publicado)],
            "Erro do placar": tabela["erro_placar_pp"].map(lambda x: comum.pontos(x / 100)),
            "Erro da projeção": [comum.pontos(e / 100) if p else "—"
                                 for e, p in zip(tabela["erro_projecao_pp"], publicado)],
        }),
        fonte=fonte,
        chave=chave,
    )


def explicar_noite(noite: pd.DataFrame) -> str:
    """Os números do texto vêm da gravação, não escritos à mão."""
    final = noite["pct_a_final"].iloc[0]
    publicada = noite[noite["pct_a_mediana"].notna()].reset_index(drop=True)
    dentro = publicada["final_no_intervalo"].astype(bool)
    comeco_fora = publicada.iloc[:int(dentro.idxmax()) if dentro.any() else len(publicada)]   # primeiras, fora da margem
    longe = publicada[publicada["erro_projecao_pp"].abs() >= 1]
    perto_desde = publicada[publicada["momento"] > longe["momento"].max()] if len(longe) else publicada
    lado_final = final > 0.5
    errado = noite[(noite["pct_a_apurado"] > 0.5) != lado_final]
    virada = noite[noite["momento"] > errado["momento"].max()].iloc[0] if len(errado) else None
    certo = ((publicada["pct_a_mediana"] > 0.5) == lado_final).mean()
    partes = []
    if len(comeco_fora):
        erros = comeco_fora["erro_projecao_pp"].abs() / 100
        partes.append(
            f"Nas primeiras atualizações da projeção ({comeco_fora['momento'].iloc[0]:%Hh%M} a "
            f"{comeco_fora['momento'].iloc[-1]:%Hh%M}, com até {comum.pct(comeco_fora['pct_secoes_projecao'].max(), 0)} "
            f"do eleitorado já lido), ela ficou de {comum.pontos(erros.min()).split()[0]} a {comum.pontos(erros.max())} longe do "
            "resultado final, que ficou fora da margem.")
    if len(perto_desde):
        partes.append(f"A partir de {perto_desde['momento'].iloc[0]:%Hh%M}, o erro ficou sempre abaixo de 1 ponto.")
    if virada is not None:
        partes.append(f"O placar oficial só passou a mostrar à frente quem venceu às {virada['momento']:%Hh%M}, com "
                      f"{comum.pct(virada['pct_secoes'], 0)} das seções apuradas.")
    partes.append(f"A projeção ficou do lado de quem venceu em {comum.pct(certo, 0)} das atualizações publicadas.")
    return " ".join(partes)


if NOITE_GRAVADA:
    st.subheader("A noite de 25/10/2026: placar oficial × projeção")
    st.markdown(
        "A votação foi prorrogada até as 19h por decisão do STF, e o TSE parou a divulgação com 0,25% das seções "
        "apuradas, das 17h06 às 19h01. O gráfico mostra a noite a partir daí, lida do TSE a cada minuto pelo mesmo "
        f"código deste site. {explicar_noite(noite_2026)}"
    )
    mostrar_noite(noite_2026, A["nm_urna"], f"% de {A['nm_urna']} nos votos válidos",
                  "TSE (resultados divulgados ao vivo em 25/10/2026, lidos a cada minuto); projeção calculada pelo "
                  "projeto.", "noite_2026")
    st.caption(
        f"**Como ler:** % de {A['nm_urna']} nos votos válidos (o de {B['nm_urna']} é 100% menos esse valor). A linha "
        "azul é o placar que o TSE mostrava em cada momento; a laranja, a projeção, com a faixa da margem. Entre "
        "19h30 e 19h53 e depois das 20h40 o servidor do TSE recusou parte dos pedidos, e a projeção trabalhou com "
        "menos municípios do que o TSE já tinha apurado. Os detalhes, inclusive o que deu errado, estão em "
        "docs/previsao.md."
    )
    st.subheader("Governador, 2º turno (DF e outros 5 estados)")
    governador_2026(comum.ler("noite_2026_governador"))

st.subheader("O teste: a noite de 2022 reproduzida seção por seção")
st.markdown(
    "Usando a hora em que cada boletim de urna chegou ao TSE, reconstruímos a apuração de 2022 minuto a minuto e "
    "rodamos a projeção como se fosse aquela noite, sem saber o resultado final. O gráfico mostra o % do "
    "1º colocado do 1º turno (LULA) nos votos dos dois primeiros (o de JAIR BOLSONARO é 100% menos esse valor)."
)

FONTE_2022 = "TSE (boletins de urna e histórico da totalização do {}º turno de 2022); cálculo do projeto."
abas = st.tabs(["2º turno de 2022", "1º turno de 2022"])
with abas[0]:
    mostrar_noite(comum.ler("apuracao_2022_2t"), "LULA", "% de LULA nos votos válidos", FONTE_2022.format(2),
                  "noite_2")
    st.caption(
        "**Como ler:** a linha azul é o placar que o TSE mostrava em cada momento; a laranja, a projeção, com a "
        "faixa da margem. Naquela noite o placar oficial só virou às 18h44, com 68% apurado; a projeção ficou do "
        "lado do vencedor desde que começou a ser publicada (5% apurado)."
    )
with abas[1]:
    mostrar_noite(comum.ler("apuracao_2022_1t"), "LULA", "% de LULA nos votos dos dois primeiros",
                  FONTE_2022.format(1), "noite_1")
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

O teste de 2022 ajudou a desenhar a projeção; o teste realmente independente foi a noite de 25/10/2026,
mostrada no início desta página, com acertos e erros.
"""
)
comum.rodape("docs/previsao.md")
