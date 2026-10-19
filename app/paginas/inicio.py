import comum
import streamlit as st

comum.cabecalho(
    "Eleições 2026 em dados",
    "Análises feitas com os dados oficiais do TSE e do IBGE: resultados, candidatos, eleitores, previsão do "
    "2º turno e um recorte do Distrito Federal. Projeto apartidário, com código aberto.",
)

presidente = comum.ler("inicio_presidente_1t_2026").sort_values("qt_votos", ascending=False)
comparecimento = comum.ler("inicio_comparecimento_1t_2026").iloc[0]
finalistas = presidente.head(2)["nm_urna"].tolist()
CORES = comum.cores_finalistas(finalistas)

st.subheader("1º turno para Presidente, 4 de outubro de 2026")
colunas = st.columns(4)
with colunas[0]:
    comum.cartao("Eleitores aptos", f"{comum.numero(comparecimento['qt_aptos'] / 1e6, 1)} mi",
                 "milhões de pessoas podiam votar")
with colunas[1]:
    comum.cartao("Foram votar", comum.pct(comparecimento["qt_comparecimento"] / comparecimento["qt_aptos"]),
                 f"{comum.numero(comparecimento['qt_comparecimento'] / 1e6, 1)} milhões de pessoas")
for coluna, nome in zip(colunas[2:], sorted(finalistas)):
    linha = presidente.set_index("nm_urna").loc[nome]
    with coluna:
        comum.cartao(nome, comum.pct(linha["pct_validos"]),
                     f"dos votos válidos ({comum.numero(linha['qt_votos'] / 1e6, 1)} milhões) · vai ao 2º turno",
                     cor=CORES[nome])
outros = presidente[~presidente["nm_urna"].isin(finalistas)]
st.caption(
    f"Os outros {len(outros)} candidatos somaram {comum.pct(outros['pct_validos'].sum())} dos votos válidos. "
    "O 2º turno é em **25 de outubro**. Candidatos em ordem alfabética."
)

# --- o que tem no site ----------------------------------------------------------
st.subheader("O que tem aqui")
SECOES = [
    ("paginas/resultados.py", "Resultados e mapa", ":material/map:",
     "Quem ganhou em cada município, quem mudou de lado desde 2022, brancos, nulos e abstenção."),
    ("paginas/nulos.py", "Votos no número errado", ":material/dialpad:",
     "Votos para Governador anulados com o número de um candidato a Presidente, nas disputas apertadas."),
    ("paginas/candidatos.py", "Perfil dos candidatos", ":material/groups:",
     "Gênero, cor, idade e escolaridade de candidatos e eleitos, comparados com a população."),
    ("paginas/patrimonio.py", "Patrimônio declarado", ":material/account_balance:",
     "Bens declarados por cargo e partido, e a evolução desde 2018 descontada a inflação."),
    ("paginas/eleitorado.py", "Eleitorado", ":material/person_check:",
     "Quem pode votar: idade, gênero, escolaridade, jovens de 16 e 17 anos."),
    ("paginas/previsao.py", "Previsão do 2º turno", ":material/insights:",
     "O que o 1º turno, sozinho, diz sobre o 2º, com margem de erro e testes nas eleições passadas."),
    ("paginas/apuracao.py", "Apuração ao vivo", ":material/timer:",
     "Na noite de 25/10, placar e projeção a cada minuto. Até lá, o teste com a noite de 2022."),
    ("paginas/df.py", "Mapa do DF", ":material/location_city:",
     "Como votou cada região do Distrito Federal."),
    ("paginas/conferencia.py", "Conferência dos dados", ":material/fact_check:",
     "As somas batem com o oficial? E por que a Lei de Benford não prova fraude."),
    ("paginas/dinheiro.py", "Dinheiro de campanha", ":material/payments:",
     "Arrecadação e gastos, quando as prestações de contas fecharem (novembro)."),
]
for i in range(0, len(SECOES), 2):
    colunas = st.columns(2)
    for coluna, (pagina, titulo, icone, descricao) in zip(colunas, SECOES[i:i + 2]):
        with coluna:
            st.page_link(pagina, label=f"**{titulo}**", icon=icone)
            st.caption(descricao)

# --- quão bem funciona ----------------------------------------------------------
st.subheader("Quão bem funciona")
st.markdown(
    """
Toda análise foi testada com dados reais antes de ser publicada. Alguns resultados:

- **A coleta confere:** a soma dos 5.757 municípios e cidades do exterior bate exatamente com o total do Brasil
  divulgado pelo TSE, sem nenhum voto de diferença.
- **A previsão do 2º turno foi testada nas seis eleições desde 2002**, cada uma prevista sem ver o resultado dela:
  o resultado real ficou dentro da margem de erro em 5 das 6.
- **A projeção ao vivo, testada na noite de 2022:** com 10% das urnas apuradas, errava o resultado final por
  0,5 ponto, enquanto o placar oficial naquele momento estava 2,9 pontos longe do final.
- **A leitura voto a voto (RDV)** bate com o resultado oficial nas disputas de Governador analisadas.

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
4. Modelos estatísticos em Python para a previsão, testados nas eleições passadas.
5. Este site em **Streamlit**, com gráficos em Plotly; as tabelas também saem prontas para o **Power BI**.

Tudo pode ser refeito por qualquer pessoa: o código e o passo a passo estão no GitHub.
"""
    )
    st.link_button("Ver o código no GitHub", comum.REPOSITORIO, icon=":material/code:")

comum.rodape()
