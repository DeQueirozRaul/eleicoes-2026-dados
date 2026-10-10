import comum
import streamlit as st

comum.cabecalho("Dinheiro de campanha", "Quanto cada candidatura arrecadou e gastou, e de onde veio o dinheiro.")
st.info(
    "Esta página entra em novembro de 2026. Os candidatos têm até 30 dias depois da eleição para "
    "entregar a prestação de contas final ao TSE; antes disso os números são parciais e mudariam "
    "a cada semana.",
    icon=":material/event:",
)
st.markdown(
    "**O que vai ter aqui:**\n"
    "- custo por voto de cada candidatura;\n"
    "- fundo eleitoral: se os partidos repassaram a mulheres e a pessoas negras o que a regra exige;\n"
    "- onde se gasta: anúncios em redes sociais, material impresso, pessoal;\n"
    "- quanto os candidatos põem do próprio bolso e quem são os maiores doadores."
)
comum.rodape()
