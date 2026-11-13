# Guia do código

Este guia explica o projeto por dentro: o que cada parte faz, por que foi feita
assim e o que deu errado no caminho. Foi escrito para quem vai **explicar o
projeto numa entrevista** e para quem quer aprender com ele.

Cada parte tem:

- os arquivos envolvidos, com links;
- trechos do código explicados linha a linha quando a ideia não é óbvia;
- **"Por que assim?"**: a decisão e a alternativa que foi descartada;
- **"Para praticar"**: um exercício curto para fixar;
- **"Na entrevista"**: como contar aquela parte em poucas frases.

## Partes

| # | Parte | O que você vai entender |
|---|---|---|
| 1 | [Visão geral](01_visao_geral.md) | o caminho dos dados, do TSE até o site; as pastas; as ferramentas e por que cada uma |
| 2 | [Dados e banco](02_dados_e_banco.md) | como os arquivos do TSE são baixados (sem baixar o que não precisa), limpos e organizados num banco DuckDB com SQL |
| 3 | [Previsão do 2º turno](03_previsao_do_2o_turno.md) | o modelo estatístico que prevê o 2º turno só com o 1º, e como ele foi testado |
| 4 | [Apuração ao vivo](04_apuracao_ao_vivo.md) | a projeção minuto a minuto, o motor que roda dentro do site e a noite de 25/10, inclusive os erros |
| 5 | [O site](05_o_site.md) | como o Streamlit funciona, como as páginas são montadas, os mapas e a publicação |
| 6 | [Análises especiais](06_analises_especiais.md) | votos no número errado (RDV), conferência e Benford, mapa do DF, candidatos, patrimônio e dinheiro de campanha |
| 7 | [Testes e qualidade](07_testes_e_qualidade.md) | como o projeto se protege de erros: testes, checagens de soma, regras de neutralidade |
| 8 | [Na entrevista](08_na_entrevista.md) | como apresentar o projeto, histórias para contar e perguntas prováveis |

## Como estudar

1. Leia a parte 1 inteira: ela é o mapa.
2. Em cada parte seguinte, abra os arquivos citados ao lado do texto. Ler o
   código de verdade, com o guia explicando, fixa muito mais do que só ler o guia.
3. Faça os exercícios "Para praticar". Eles são pequenos de propósito: o
   objetivo é você mexer no código e ver o que acontece.
4. Antes de uma entrevista, releia a parte 8 e os quadros "Na entrevista".

Não precisa decorar fórmulas. Precisa saber **o que cada parte resolve, por que
foi feita daquele jeito e como você sabe que funciona**.
