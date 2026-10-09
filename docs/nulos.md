# Votos para Governador anulados com o número de um candidato a Presidente

Código: [`eleicoes/rdv.py`](../eleicoes/rdv.py) e
[`scripts/nulos_disputas_apertadas.py`](../scripts/nulos_disputas_apertadas.py).

## A pergunta

Circularam relatos de eleitores que, na urna, digitaram para Governador o número
de um candidato a Presidente (por exemplo, 22 ou 13). Quando não há candidato a
Governador com esse número no estado, o voto é anulado. Quantas vezes isso
aconteceu? E, nas disputas mais apertadas, esses votos poderiam ter mudado o
resultado?

## De onde vem o dado

O boletim de urna só mostra o total de votos nulos. Mas o TSE também publica o
**RDV (Registro Digital do Voto)** de cada urna: a lista de todos os votos,
embaralhados e sem identificar o eleitor, com o tipo de voto e **os dígitos
digitados**. Nos votos nulos, o número digitado fica registrado.

Os RDVs ficam dentro dos "arquivos transmitidos para totalização" do Portal de
Dados Abertos (um zip por UF e turno, de centenas de MB). O leitor baixa só os
bytes de cada arquivo `.rdv` (uns 10 KB por urna), sem baixar o zip inteiro.

**Conferência:** em cada disputa, os votos de cada candidato contados no RDV
foram comparados com o resultado oficial. A tabela de resultados mostra a
diferença; ela é zero ou mínima (explicações abaixo).

## Como as disputas foram escolhidas

Para cada disputa de Governador (1º e 2º turnos de 2022 e 1º turno de 2026),
calculamos **quantos votos bastariam para mudar o resultado**, considerando a
mudança mais fácil entre:

- **virar o 2º turno:** diferença entre o 1º e o 2º colocado;
- **vencer no 1º turno:** votos que faltaram para o mais votado passar de 50% dos
  válidos;
- **forçar um 2º turno:** votos que, somados aos outros candidatos, teriam
  deixado o eleito abaixo de 50%;
- **trocar quem vai ao 2º turno:** diferença entre o 2º e o 3º colocado.

Entraram as disputas em que isso era **menos de 1,5% dos votos válidos**
(a lista completa, com todas as disputas, fica em `dados/nulos/disputas_governador.csv`).

## Duas formas de responder "teria mudado o resultado?"

1. **Teto (sem suposições):** se os nulos com número de presidenciável são
   **menos** que os votos necessários, eles não poderiam ter mudado o
   resultado, qualquer que fosse a intenção dos eleitores. Se são **mais**,
   poderiam, dependendo de para quem o eleitor queria votar.
2. **Hipótese da coligação (uma suposição explícita):** quem digitou o número
   de um presidenciável queria votar no candidato a Governador cuja coligação
   (ou federação) inclui o partido desse presidenciável. Os votos são somados a
   esse candidato e o resultado é recalculado. A regra vale igualmente para
   todos os números e partidos. Se o partido não estava em nenhuma coligação
   para Governador no estado, o voto continua nulo.

## Ressalvas

- **O RDV não diz a intenção.** Parte desses votos pode ser nulo de propósito
  (protesto). Por isso a hipótese da coligação é só um cenário, não uma
  afirmação sobre o que o eleitor queria.
- **Só dá para ver a confusão que virou nulo.** Se o número digitado era de um
  candidato a Governador existente, o voto foi para ele e não dá para separar
  do voto intencional.
- **Voto nulo é uma escolha legítima e o resultado oficial é o do TSE.** Esta
  análise mede um fenômeno de informação ao eleitor; não questiona o resultado.
- **Diferenças RDV × oficial:** uma urna do RS (de 27 mil) tem um RDV num
  formato que o leitor não reconhece (98 votos ficam de fora); em SC, 829 votos
  foram digitados para um candidato a Governador com candidatura indeferida (no
  RDV aparecem como votos no número; no resultado oficial, como anulados).

## Resultados

<!-- RESULTADOS -->
