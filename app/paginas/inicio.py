import json

import comum
import pandas as pd
import streamlit as st

comum.cabecalho(
    "Eleições 2026 em dados",
    "Quem venceu e onde, como a apuração andou minuto a minuto, quem se candidatou, quanto declarou ter e quanto "
    "gastou: as eleições de 2026 contadas com os dados oficiais do TSE e do IBGE. Projeto apartidário, com código "
    "aberto.",
)

ENCERRADA = comum.existe("resultados_2t")
config = json.loads((comum.DADOS / "ao_vivo_config.json").read_text(encoding="utf-8"))
A, B = sorted([config["finalistas"]["A"]["nm_urna"], config["finalistas"]["B"]["nm_urna"]])
CORES = comum.cores_finalistas([A, B])
NUMERO = {config["finalistas"][k]["nm_urna"]: config["finalistas"][k]["nr_candidato"] for k in ("A", "B")}


def destaque(pagina: str, icone: str, tema: str, numero: str, frase: str) -> None:
    """Um achado: o número grande, a frase que explica e o link para a página com os detalhes."""
    with st.container(border=True):
        st.caption(tema)
        st.markdown(f"<div style='font-size:1.9rem;font-weight:600;color:{comum.TINTA};line-height:1.2'>{numero}</div>",
                    unsafe_allow_html=True)
        st.markdown(frase)
        st.page_link(pagina, label="Ver a análise", icon=icone)


# --- o resultado --------------------------------------------------------------------
if ENCERRADA:
    segundo = comum.ler("resultados_2t")
    votos = {nome: int(segundo[f"votos_{NUMERO[nome]}"].sum()) for nome in (A, B)}
    validos = sum(votos.values())
    no_mapa = segundo[segundo["cd_municipio_ibge"].notna()]
    st.subheader("O resultado: 2º turno para Presidente, 25 de outubro")
    colunas = st.columns(3)
    for coluna, nome in zip(colunas, (A, B)):
        with coluna:
            n = int((no_mapa["mais_votado"] == nome).sum())
            comum.cartao(nome, comum.pct(votos[nome] / validos, 2),
                         f"{comum.numero(votos[nome])} votos · à frente em {comum.numero(n)} municípios",
                         cor=CORES[nome])
    with colunas[2]:
        comum.cartao("Foram votar", comum.pct(segundo["qt_comparecimento"].sum() / segundo["qt_aptos"].sum()),
                     f"{comum.numero(segundo['qt_comparecimento'].sum() / 1e6, 1)} milhões de pessoas")
    diferenca = abs(votos[A] - votos[B])
    st.caption(f"Diferença de {comum.numero(diferenca)} votos ({comum.pontos((votos[A] - votos[B]) / validos)}). "
               "Candidatos em ordem alfabética. O resultado oficial é sempre o do TSE.")
else:
    presidente = comum.ler("inicio_presidente_1t_2026").sort_values("qt_votos", ascending=False)
    st.subheader("1º turno para Presidente, 4 de outubro de 2026")
    colunas = st.columns(2)
    for coluna, nome in zip(colunas, sorted(presidente.head(2)["nm_urna"])):
        linha = presidente.set_index("nm_urna").loc[nome]
        with coluna:
            comum.cartao(nome, comum.pct(linha["pct_validos"]), "dos votos válidos · vai ao 2º turno", cor=CORES[nome])

# --- destaques ----------------------------------------------------------------------
st.subheader("O que os dados mostram")
achados = []
if ENCERRADA:
    viraram = no_mapa[no_mapa["mudou_desde_o_1t"] & no_mapa["mais_votado"].isin([A, B])]
    achados.append(("paginas/resultados.py", ":material/map:", "Resultados e mapa",
                    f"{comum.numero(len(viraram))} municípios",
                    "mudaram de quem ficou à frente do 1º para o 2º turno. O mapa mostra a vantagem em cada um, "
                    "e o que mudou desde 2022."))
if comum.existe("noite_2026_2t"):
    noite = comum.ler("noite_2026_2t")
    final = noite["pct_a_final"].iloc[0]
    errado = noite[(noite["pct_a_apurado"] > 0.5) != (final > 0.5)]
    virada = noite[noite["momento"] > errado["momento"].max()].iloc[0] if len(errado) else None
    if virada is not None:
        achados.append(("paginas/apuracao.py", ":material/timer:", "A noite da apuração",
                        f"{virada['momento']:%Hh%M}",
                        f"foi a hora em que o placar oficial passou a mostrar à frente quem venceu, com "
                        f"{comum.pct(virada['pct_secoes'], 0)} das seções apuradas. A projeção ao vivo deste site "
                        "apontava esse lado desde a primeira atualização, mas começou errando por 3 pontos."))
if comum.existe("noite_2026_prorrogacao"):
    urnas = comum.ler("noite_2026_prorrogacao").set_index("encerramento")
    achados.append(("paginas/apuracao.py", ":material/schedule:", "A prorrogação até as 19h",
                    comum.pct(urnas.loc["até 17h30", "pct_secoes"]),
                    "das urnas foram encerradas até 17h30, mesmo com a votação prorrogada. O que mudou foi a ordem "
                    "da contagem, e é isso que explica o erro do começo da projeção."))
if comum.existe("previsao_nacional"):
    prev = comum.ler("previsao_nacional").query("variante == 'modelo principal'").iloc[0]
    frase = "era a chance de cada finalista só com o 1º turno: empate."
    if comum.existe("noite_2026_2t"):
        pct_final = comum.ler("noite_2026_2t")["pct_a_final"].iloc[0]
        dentro = prev["pct_a_inferior"] <= pct_final <= prev["pct_a_superior"]
        frase += (f" O resultado ficou {'dentro' if dentro else 'fora'} da margem de erro da previsão, a "
                  f"{comum.pontos(abs(prev['pct_a_mediana'] - pct_final))} do valor mais provável.")
    achados.append(("paginas/previsao.py", ":material/insights:", "Previsão do 2º turno",
                    f"{comum.pct(prev['prob_a_vence'], 0)} × {comum.pct(1 - prev['prob_a_vence'], 0)}", frase))
if comum.existe("nulos_disputas_apertadas"):
    nulos = comum.ler("nulos_disputas_apertadas")
    achados.append(("paginas/nulos.py", ":material/dialpad:", "Votos no número errado",
                    f"{int(nulos['em_jogo_maior_que_margem'].sum())} de {len(nulos)}",
                    "disputas de Governador mais apertadas (2022 e 2026) tiveram mais votos anulados com o número "
                    "de um candidato a Presidente do que a diferença entre os dois primeiros."))
if comum.existe("candidatos_perfil"):
    perfil = comum.ler("candidatos_perfil")
    g = perfil[(perfil["ano"] == 2026) & (perfil["dimensao"] == "Gênero") & (perfil["cargo"] == "Todos os cargos")]
    g = g.pivot_table(index="categoria", columns="grupo", values="n", aggfunc="sum")
    if {"Candidatos", "Eleitos"} <= set(g.columns) and "Mulheres" in g.index:
        achados.append(("paginas/candidatos.py", ":material/groups:", "Perfil dos candidatos",
                        comum.pct(g.loc["Mulheres", "Eleitos"] / g["Eleitos"].sum(), 0),
                        f"dos eleitos em 2026 são mulheres, contra {comum.pct(g.loc['Mulheres', 'Candidatos'] / g['Candidatos'].sum(), 0)} "
                        "das candidaturas e mais da metade da população adulta."))
if comum.existe("patrimonio_resumo"):
    resumo = comum.ler("patrimonio_resumo").set_index("chave")["valor"]
    if "parcela_1pct_maiores_2026" in resumo:
        achados.append(("paginas/patrimonio.py", ":material/account_balance:", "Patrimônio declarado",
                        comum.pct(resumo["parcela_1pct_maiores_2026"], 0),
                        "de todo o patrimônio declarado pelos candidatos de 2026 está com o 1% que declarou mais."))
if comum.existe("eleitorado_brasil_perfil"):
    idade = comum.ler("eleitorado_brasil_perfil").query("dimensao == 'faixa_etaria'").set_index("categoria")["qt_eleitores"]
    facultativo = idade[[c for c in idade.index if c in ("16 anos", "17 anos") or c[:2] in ("70", "75", "80", "85", "90",
                                                                                         "95", "10")]].sum()
    achados.append(("paginas/eleitorado.py", ":material/person_check:", "Eleitorado",
                    f"{comum.numero(facultativo / 1e6, 1)} milhões",
                    "de eleitores tinham 16 ou 17 anos, ou 70 anos ou mais: idades em que votar é opcional (para "
                    "quem não sabe ler e escrever também)."))
if comum.existe("dinheiro_resumo"):
    din = comum.ler("dinheiro_resumo").iloc[0]
    achados.append(("paginas/dinheiro.py", ":material/payments:", "Dinheiro de campanha",
                    f"R$ {comum.numero(din['receitas'] / 1e9, 1)} bilhões",
                    f"arrecadados pelas candidaturas; {comum.pct(din['parte_fundos_publicos'], 0)} vieram dos fundos "
                    "públicos (eleitoral e partidário)."))
if comum.existe("conferencia_resumo"):
    conf = comum.ler("conferencia_resumo").iloc[0]
    achados.append(("paginas/conferencia.py", ":material/fact_check:", "Conferência dos dados",
                    f"{comum.numero(conf['diferenca_validos'])} votos",
                    f"de diferença entre a soma das {comum.numero(conf['secoes_detalhe'])} seções e o resultado "
                    "oficial do 1º turno. E por que a Lei de Benford não serve para provar fraude."))

for i in range(0, len(achados), 3):
    for coluna, achado in zip(st.columns(3), achados[i:i + 3]):
        with coluna:
            destaque(*achado)

# --- todas as páginas -----------------------------------------------------------------
st.subheader("Todas as páginas")
SECOES = [
    ("paginas/resultados.py", "Resultados e mapa", ":material/map:",
     "Quem ficou à frente em cada município nos dois turnos, quem mudou de lado desde 2022, brancos, nulos, "
     "abstenção e como funciona o quociente eleitoral."),
    ("paginas/apuracao.py", "Apuração ao vivo", ":material/timer:",
     "A noite de 25/10 minuto a minuto: o placar oficial, a projeção, onde ela errou e o que a prorrogação mudou."),
    ("paginas/previsao.py", "Previsão do 2º turno", ":material/insights:",
     "O que o 1º turno, sozinho, dizia sobre o 2º, testado nas seis eleições desde 2002, e como ficou."),
    ("paginas/nulos.py", "Votos no número errado", ":material/dialpad:",
     "Votos para Governador anulados porque o eleitor digitou o número de um candidato a Presidente."),
    ("paginas/candidatos.py", "Perfil dos candidatos", ":material/groups:",
     "Gênero, cor, idade e escolaridade de quem se candidatou e de quem foi eleito, comparados com a população."),
    ("paginas/patrimonio.py", "Patrimônio declarado", ":material/account_balance:",
     "Bens declarados por cargo e partido, e quanto mudaram desde 2018, já descontada a inflação."),
    ("paginas/dinheiro.py", "Dinheiro de campanha", ":material/payments:",
     "Quanto as candidaturas arrecadaram e gastaram, de onde veio o dinheiro e quanto custou cada voto."),
    ("paginas/eleitorado.py", "Eleitorado", ":material/person_check:",
     "Quem pode votar: idade, gênero, escolaridade, o voto facultativo e quem deixou de votar."),
    ("paginas/df.py", "Mapa do DF", ":material/location_city:",
     "Como votou cada uma das 35 regiões administrativas e cada local de votação do Distrito Federal."),
    ("paginas/conferencia.py", "Conferência dos dados", ":material/fact_check:",
     "As somas batem com o oficial? Os testes feitos em cada etapa, e o que eles provam e não provam."),
]
for i in range(0, len(SECOES), 2):
    for coluna, (pagina, titulo, icone, descricao) in zip(st.columns(2), SECOES[i:i + 2]):
        with coluna:
            st.page_link(pagina, label=f"**{titulo}**", icon=icone)
            st.caption(descricao)

# --- quão bem funciona ----------------------------------------------------------------
st.subheader("Quão bem funciona (e onde errou)")
st.markdown(
    """
Toda análise foi testada com dados reais, e os erros também estão publicados:

- **As somas conferem:** os votos de todos os municípios, seções e boletins de urna batem com o resultado oficial
  do TSE, voto a voto, nos dois turnos.
- **A previsão de antes da eleição** foi testada nas seis eleições desde 2002 e, em 2026, o resultado ficou dentro
  da margem de erro.
- **A projeção ao vivo da noite de 25/10** ficou do lado de quem venceu em todas as atualizações e, a partir de 20h,
  errou menos de 0,3 ponto. Mas começou errando por cerca de 3 pontos. Refazendo a noite com os dados oficiais, a
  causa apareceu: as primeiras seções contadas em cada município não representavam o resto. Está tudo explicado
  na página Apuração ao vivo.

"Ponto" é a diferença entre duas porcentagens: se a projeção dizia 50,4% e o resultado foi 50,9%, o erro foi de
0,5 ponto.
"""
)

# --- neutralidade e método --------------------------------------------------------------
esquerda, direita = st.columns(2)
with esquerda:
    st.subheader("Compromisso de neutralidade")
    st.markdown(
        """
- Só dados oficiais e públicos (TSE e IBGE), com a fonte em cada gráfico.
- A mesma análise vale para todos os candidatos e partidos.
- Candidatos em ordem alfabética e cores que não lembram nenhum partido.
- Textos descrevem os dados, sem adjetivos.
- Previsões são probabilidades, com margem de erro. Não é pesquisa eleitoral.
- Ponto de atenção não é acusação.
- O resultado oficial é sempre o do TSE.
"""
    )
with direita:
    st.subheader("Como foi feito")
    st.markdown(
        """
1. **Python** baixa os arquivos do TSE e do IBGE (alguns com milhões de linhas) e corrige as pegadinhas:
   codificação antiga, códigos de "sem informação", códigos de município diferentes entre TSE e IBGE.
2. Os dados ficam em **Parquet** e num banco **DuckDB**, consultado em **SQL**.
3. **Checagens automáticas** conferem as somas antes de qualquer análise.
4. Modelos estatísticos em Python para a previsão, testados nas eleições passadas e na noite real.
5. Este site em **Streamlit**, com gráficos em Plotly; as tabelas também saem prontas para o **Power BI**.

Tudo pode ser refeito por qualquer pessoa: o código e o passo a passo estão no GitHub.
"""
    )
    st.link_button("Ver o código no GitHub", comum.REPOSITORIO, icon=":material/code:")

comum.rodape()
