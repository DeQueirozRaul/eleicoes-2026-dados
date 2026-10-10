"""Padrões comuns a todas as páginas do site: leitura dos dados, cores, números
no formato brasileiro e o jeito de mostrar gráficos e tabelas.

Regras de neutralidade que valem para o site inteiro (ver README):
- candidatos sempre em ordem alfabética do nome de urna;
- cores que não lembram partido: o 1º finalista em ordem alfabética é VIOLETA,
  o 2º é VERDE_AGUA (par validado para daltonismo, nos dois sentidos);
- textos descritivos, sem adjetivos; previsões sempre com margem de incerteza.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DADOS = Path(__file__).parent / "dados"
REPOSITORIO = "https://github.com/DeQueirozRaul/eleicoes-2026-dados"

# --- cores -------------------------------------------------------------------
# Candidatos (identidade). Só duas cores de identidade: com mais candidatos,
# use uma cor única (SERIE) e o nome escrito em cada barra.
VIOLETA = "#6250d6"
VERDE_AGUA = "#199e70"
# Série única que não representa candidato (ex.: % de mulheres por partido).
SERIE = "#2a78d6"
# Destaque de "um item contra o resto" e itens secundários.
DESTAQUE = "#eb6834"
APAGADO = "#c3c2b7"

TINTA = "#0b0b0b"       # texto principal
TINTA_2 = "#52514e"     # texto secundário
MUDO = "#898781"        # eixos e rótulos
GRADE = "#e1e0d9"       # linhas de grade
EIXO = "#c3c2b7"        # linha de base
SUPERFICIE = "#fcfcfb"
NEUTRO = "#f0efec"      # meio de escala divergente ("nem um, nem outro")

# Escala sequencial (magnitude): um só tom, do claro ao escuro.
SEQUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
# Escala divergente para dois finalistas: VIOLETA <- cinza -> VERDE_AGUA.
DIVERGENTE = [[0.0, "#2e2380"], [0.25, VIOLETA], [0.5, NEUTRO], [0.75, VERDE_AGUA], [1.0, "#0b5a3e"]]

FONTE = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"


def cores_finalistas(nomes) -> dict[str, str]:
    """{nome: cor} para dois candidatos, pela ordem alfabética do nome de urna."""
    a, b = sorted(nomes)
    return {a: VIOLETA, b: VERDE_AGUA}


# --- dados -------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def ler(nome: str) -> pd.DataFrame:
    """Lê app/dados/<nome>.parquet (arquivos pequenos, gerados por scripts/preparar_site.py)."""
    return pd.read_parquet(DADOS / f"{nome}.parquet")


def existe(nome: str) -> bool:
    return (DADOS / f"{nome}.parquet").exists()


# --- números no formato brasileiro --------------------------------------------
def numero(x: float, casas: int = 0) -> str:
    """1234567.8 -> '1.234.567,8'."""
    texto = f"{x:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(fracao: float, casas: int = 1) -> str:
    """0.4993 -> '49,9%'."""
    return numero(100 * fracao, casas) + "%"


def pontos(diferenca: float, casas: int = 1) -> str:
    """Diferença entre duas porcentagens (em fração): 0.005 -> '0,5 ponto'."""
    valor = abs(100 * diferenca)
    return f"{numero(valor, casas)} {'ponto' if round(valor, casas) <= 1 else 'pontos'}"


# --- gráficos ----------------------------------------------------------------
def estilo(fig: go.Figure, altura: int = 380, legenda: bool = True) -> go.Figure:
    """Aplica o visual padrão: fundo limpo, grade discreta, barras finas com ponta
    arredondada, números com vírgula decimal e ponto de milhar."""
    fig.update_layout(
        height=altura,
        font=dict(family=FONTE, size=13, color=TINTA_2),
        separators=",.",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=16, t=40 if legenda else 16, b=8),
        showlegend=legenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None,
                    font=dict(color=TINTA_2)),
        hoverlabel=dict(bgcolor="white", bordercolor=GRADE, font=dict(family=FONTE, color=TINTA)),
        barcornerradius=4,
        bargap=0.35,
    )
    # automargin: o Plotly abre espaço para os rótulos dos eixos (sem ele, nomes longos são cortados)
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=EIXO, ticks="", automargin=True,
                     tickfont=dict(color=MUDO), title_font=dict(color=TINTA_2))
    fig.update_yaxes(gridcolor=GRADE, gridwidth=1, zeroline=False, ticks="", automargin=True,
                     tickfont=dict(color=MUDO), title_font=dict(color=TINTA_2))
    return fig


def mostrar(fig: go.Figure, tabela: pd.DataFrame | None = None, fonte: str | None = None,
            chave: str | None = None) -> None:
    """Mostra o gráfico, a fonte e, num quadro que abre e fecha, a tabela com os
    mesmos números (quem não enxerga bem as cores ou quer o valor exato lê ali)."""
    # Os mapas do Plotly baixam um contorno do mundo de cdn.plot.ly (o endereço padrão).
    # Não troque por um caminho do próprio site: no Streamlit Cloud ele não existe e os mapas somem.
    st.plotly_chart(fig, config={"displayModeBar": False, "scrollZoom": False}, theme=None, key=chave)
    if fonte:
        st.caption(f"Fonte: {fonte}")
    if tabela is not None:
        with st.expander("Ver os números em tabela"):
            st.dataframe(tabela, hide_index=True)


def cabecalho(titulo: str, subtitulo: str | None = None) -> None:
    st.title(titulo)
    if subtitulo:
        st.markdown(f"<p style='color:{TINTA_2};font-size:1.05rem;margin-top:-0.6rem'>{subtitulo}</p>",
                    unsafe_allow_html=True)


def cartao(rotulo: str, valor: str, detalhe: str | None = None, cor: str | None = None) -> None:
    """Cartão com um número em destaque. `cor` (opcional) desenha um quadradinho
    ao lado do rótulo para ligar o número ao gráfico; o texto nunca usa a cor."""
    marca = (f"<span style='display:inline-block;width:10px;height:10px;border-radius:2px;"
             f"background:{cor};margin-right:6px'></span>") if cor else ""
    detalhe_html = f"<div style='color:{TINTA_2};font-size:0.9rem;margin-top:2px'>{detalhe}</div>" if detalhe else ""
    st.markdown(
        f"<div style='padding:12px 14px;border:1px solid {GRADE};border-radius:8px;background:{SUPERFICIE};"
        f"margin-bottom:8px'>"
        f"<div style='color:{TINTA_2};font-size:0.9rem'>{marca}{rotulo}</div>"
        f"<div style='color:{TINTA};font-size:1.9rem;font-weight:600;line-height:1.25'>{valor}</div>"
        f"{detalhe_html}</div>",
        unsafe_allow_html=True,
    )


def rodape(metodologia: str | None = None) -> None:
    """Rodapé de toda página: neutralidade, fonte oficial e link para o código."""
    st.divider()
    partes = ["Projeto apartidário: só dados oficiais do TSE e do IBGE, a mesma análise para todos "
              "os candidatos, nomes em ordem alfabética. O resultado oficial é sempre o do TSE."]
    if metodologia:
        partes.append(f"[Metodologia]({REPOSITORIO}/blob/main/{metodologia})")
    partes.append(f"[Código e dados]({REPOSITORIO})")
    st.caption(" · ".join(partes))


def em_construcao(o_que: str) -> None:
    st.info(f"Em construção: {o_que}", icon=":material/construction:")
