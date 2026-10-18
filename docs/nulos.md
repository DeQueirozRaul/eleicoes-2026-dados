# Votos para Governador anulados com o número de um candidato a Presidente

Código: [`eleicoes/rdv.py`](../eleicoes/rdv.py) e
[`scripts/nulos_disputas_apertadas.py`](../scripts/nulos_disputas_apertadas.py).

## A pergunta

Circularam relatos de eleitores que, na urna, digitaram para Governador o número
de um candidato a Presidente (por exemplo, 13 ou 22). Quando não há candidato a
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
  formato que o leitor não reconhece (98 votos ficam de fora); em SC (829) e na
  BA (427), há votos digitados para candidatos a Governador com candidatura
  indeferida (no RDV aparecem como votos no número; no resultado oficial, como
  anulados).

## Resultados

> **Atualização (18/10/2026):** em 10/10, depois da primeira versão desta análise, o
> TSE refez a totalização de Governador do Rio de Janeiro: os votos de GAROTINHO
> deixaram de ser válidos. DOUGLAS RUAS passou a ter 50,9% dos válidos e foi eleito
> no 1º turno. Para haver 2º turno seriam necessários 147.771 votos (1,8% dos
> válidos), acima do limite de 1,5%, e o RJ saiu da lista (eram 9 disputas, agora
> são 8). No RJ, os votos anulados com número de presidenciável (216.497) continuam
> maiores do que esses 147.771.

Das 66 disputas de Governador analisadas, **8** puderam ser mudadas com menos de
1,5% dos votos válidos. As 8, da mais apertada para a menos apertada:

| Disputa | Resultado oficial | Votos que bastariam para mudar o resultado | Votos anulados com número de presidenciável | Eram suficientes para mudar? | Na hipótese da coligação |
|---|---|---|---|---|---|
| RS 2022 | 2º turno entre EDUARDO LEITE e ONYX LORENZONI | 2.441 para mudar quem vai ao 2º turno | 29.060 | **Sim** | Não mudaria |
| DF 2026 | 2º turno entre CELINA LEÃO e LEANDRO GRASS | 2.177 para CELINA LEÃO vencer no 1º turno | 30.034 | **Sim** | **Mudaria:** CELINA LEÃO venceria no 1º turno |
| PR 2026 | SERGIO MORO venceu no 1º turno | 12.023 para haver 2º turno | 140.474 | **Sim** | **Mudaria:** haveria 2º turno entre REQUIÃO FILHO e SERGIO MORO |
| SC 2022 | 2º turno entre DÉCIO LIMA e JORGINHO MELLO | 17.433 para mudar quem vai ao 2º turno | 17.335 | Não | Não mudaria |
| AC 2026 | 2º turno entre ALAN RICK e MAILZA ASSIS | 2.127 para MAILZA ASSIS vencer no 1º turno | 31.469 | **Sim** | **Mudaria:** MAILZA ASSIS venceria no 1º turno |
| DF 2022 | IBANEIS ROCHA venceu no 1º turno | 10.223 para haver 2º turno | 37.274 | **Sim** | Não mudaria |
| ES 2026 | 2º turno entre LORENZO PAZOLINI e RICARDO FERRAÇO | 14.905 para LORENZO PAZOLINI vencer no 1º turno | 52.704 | **Sim** | **Mudaria:** LORENZO PAZOLINI venceria no 1º turno |
| BA 2022 | 2º turno entre ACM NETO e JERÔNIMO | 89.382 para JERÔNIMO vencer no 1º turno | 49.465 | Não | Não mudaria |

**Como ler uma linha (DF 2026):** CELINA LEÃO teve 49,93% dos votos válidos;
faltaram **2.177 votos** para passar de 50% e vencer no 1º turno. Nas urnas,
**30.034 votos para Governador** foram anulados porque o eleitor digitou o
número de um candidato a Presidente (26.603 deles digitaram 22), quase 14 vezes
o que faltou. Então esses votos **eram suficientes** para mudar o resultado,
dependendo de em quem o eleitor queria votar. Na hipótese da coligação (o 22 é
do PL, que estava na coligação de CELINA LEÃO), ela venceria no 1º turno.

**Em resumo:**

- **Em 6 das 8 disputas**, os votos anulados com número de presidenciável eram
  mais do que os votos que bastariam para mudar o resultado. Nas outras duas
  (SC 2022 e BA 2022), nem que todos fossem para o mesmo candidato o resultado
  mudaria.
- **Na hipótese da coligação, o resultado mudaria em 4 das 8, todas de 2026,**
  nos dois sentidos: no DF, no AC e no ES a disputa terminaria no 1º turno em
  vez de ir ao 2º; no PR, iria ao 2º turno em vez de terminar no 1º.
- O fenômeno foi maior em 2026 (de 1,7% a 6,4% de todos os votos para
  Governador) do que em 2022 (de 0,4% a 2,1%). O número de um presidenciável só
  vira nulo quando nenhum candidato a Governador do estado tem aquele número;
  por isso o tamanho depende de quais partidos lançaram candidato em cada estado.
- **Nada disso altera o resultado oficial.** Mostra que, em disputas muito
  apertadas, a confusão entre os números de cargos diferentes envolve votos
  suficientes para importar.

### Números mais digitados

Votos nulos para Governador com o número de um candidato a Presidente, por
número digitado (os quatro mais frequentes):

| Disputa | Votos para Governador (total) | Anulados com número de presidenciável | Números mais digitados (votos) |
|---|---|---|---|
| RS 2022 | 6.883.232 | 0,4% | 15: 22.033, 44: 3.697, 14: 2.749, 80: 419 |
| DF 2026 | 1.817.921 | 1,7% | 22: 26.603, 14: 2.077, 70: 773, 21: 357 |
| PR 2026 | 6.829.615 | 2,1% | 13: 127.535, 30: 6.416, 70: 4.668, 21: 1.134 |
| SC 2022 | 4.471.619 | 0,4% | 15: 13.558, 14: 2.558, 21: 710, 80: 360 |
| AC 2026 | 487.971 | 6,4% | 22: 19.428, 13: 9.657, 55: 1.303, 70: 537 |
| DF 2022 | 1.807.484 | 2,1% | 13: 18.456, 22: 17.135, 44: 1.077, 30: 521 |
| ES 2026 | 2.348.612 | 2,2% | 22: 45.222, 55: 3.506, 70: 2.348, 30: 388 |
| BA 2022 | 8.866.018 | 0,6% | 12: 26.700, 15: 15.783, 14: 4.631, 16: 676 |

### Conferência com o resultado oficial

Em todas as 8 disputas, os votos de cada candidato contados no RDV bateram com o
resultado oficial do TSE: diferença zero em 5 e, nas outras três, no máximo 0,02%
dos votos (RS: −98; SC: +829; BA: +427; explicações nas ressalvas acima). Os
números completos ficam em `dados/nulos/nulos_disputas_apertadas.csv`.
