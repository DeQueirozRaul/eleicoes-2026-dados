"""Site do projeto Eleições 2026 em dados.

Para abrir no seu computador:   .venv\\Scripts\\python -m streamlit run app/site.py
"""

import streamlit as st

st.set_page_config(page_title="Eleições 2026 em dados", page_icon=":material/how_to_vote:", layout="wide")

paginas = {
    "": [
        st.Page("paginas/inicio.py", title="Início", icon=":material/home:", default=True),
    ],
    "Resultados": [
        st.Page("paginas/resultados.py", title="Resultados e mapa", icon=":material/map:", url_path="resultados"),
        st.Page("paginas/nulos.py", title="Votos no número errado", icon=":material/dialpad:", url_path="numero-errado"),
    ],
    "Quem se candidatou": [
        st.Page("paginas/candidatos.py", title="Perfil dos candidatos", icon=":material/groups:", url_path="candidatos"),
        st.Page("paginas/patrimonio.py", title="Patrimônio declarado", icon=":material/account_balance:", url_path="patrimonio"),
        st.Page("paginas/dinheiro.py", title="Dinheiro de campanha", icon=":material/payments:", url_path="campanha"),
    ],
    "Quem vota": [
        st.Page("paginas/eleitorado.py", title="Eleitorado", icon=":material/person_check:", url_path="eleitorado"),
    ],
    "2º turno": [
        st.Page("paginas/previsao.py", title="Previsão do 2º turno", icon=":material/insights:", url_path="previsao"),
        st.Page("paginas/apuracao.py", title="Apuração ao vivo", icon=":material/timer:", url_path="apuracao"),
    ],
    "Distrito Federal": [
        st.Page("paginas/df.py", title="Mapa do DF", icon=":material/location_city:", url_path="df"),
    ],
    "Sobre os dados": [
        st.Page("paginas/conferencia.py", title="Conferência dos dados", icon=":material/fact_check:", url_path="conferencia"),
    ],
}

st.navigation(paginas, expanded=True).run()
