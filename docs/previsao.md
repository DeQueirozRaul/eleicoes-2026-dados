# Metodologia da previsão do 2º turno

A previsão tem duas partes: uma **antes da eleição** (com base no 1º turno) e
uma **ao vivo** (atualizada durante a apuração). As duas usam só resultados
oficiais do TSE. O modelo não entrevista eleitores e, portanto, não é pesquisa
eleitoral. O resultado é sempre apresentado como probabilidade com margem de
incerteza.

Os candidatos aparecem com o nome real. Dentro do modelo, "A" é o 1º colocado
no total nacional do 1º turno e "B" o 2º; as mesmas regras valem para os dois e
nada no modelo depende de partido.

## Parte 1: antes do 2º turno

Código: [`eleicoes/modelo_2t.py`](../eleicoes/modelo_2t.py) e
[`scripts/prever_2t.py`](../scripts/prever_2t.py).
Dados: votação para Presidente por município em todos os 2º turnos desde 2002
(2002, 2006, 2010, 2014, 2018 e 2022) e o 1º turno de 2026.

**Pergunta:** sabendo como cada município votou no 1º turno, qual será a
porcentagem de cada finalista no 2º turno?

### Etapa nacional: quanto o placar muda entre os turnos

A maior parte da mudança vem dos votos dos candidatos eliminados. Um padrão
aparece nas eleições passadas: **em 5 das 6, o 1º colocado do 1º turno ficou com
menos da metade dos votos que eram dos eliminados**.

| Ano | 1º colocado no 1º turno | Votos nos eliminados | Parte que foi para o 1º colocado* |
|---|---|---|---|
| 2002 | LULA | 30,4% | 49% |
| 2006 | LULA | 9,8% | 125% |
| 2010 | DILMA | 20,5% | 45% |
| 2014 | DILMA | 24,9% | 40% |
| 2018 | JAIR BOLSONARO | 24,7% | 37% |
| 2022 | LULA | 8,4% | 30% |

\* Conta simplificada: quanto o 1º colocado cresceu entre os turnos, dividido
pelos votos dos eliminados. Passar de 100% (2006) significa que o 2º colocado
também perdeu votos de um turno para o outro.

O modelo transforma isso em: a mudança do placar entre os finalistas (na escala
logit) é proporcional à fatia dos eliminados, mais um choque que não depende
dela:

```
delta = k × (fatia dos eliminados) + choque
```

`k` e o tamanho típico do choque são estimados com as eleições anteriores.
2006 é o que deixa o choque grande.

### Etapa municipal: como essa mudança se distribui pelo país

```
logit(% de A no 2º turno no município) =
      logit(% de A entre os dois finalistas no 1º turno)
    + delta                                         mudança nacional
    + λ × delta × (eliminados no município / eliminados no país − 1)
    + γ × eliminados no município × (logit local − logit nacional)
    + efeito da UF + ruído do município
```

- **λ = 0,30:** a mudança é maior onde os eliminados tiveram mais votos (30%
  proporcional, 70% igual em todo lugar).
- **γ = −0,69:** os eleitores dos eliminados acompanham o voto do município,
  mas de forma mais equilibrada; onde um finalista domina, a vantagem dele
  diminui um pouco no 2º turno.
- O ruído do município é maior em municípios pequenos.

Comparamos seis versões dessa etapa (de "mudança igual em todo o país" até a
versão com todos os termos) prevendo cada eleição com as outras cinco. A
escolhida teve o menor erro médio por município:

| Versão | Erro médio por município (pontos) |
|---|---|
| Mudança igual em todo o país | 3,59 |
| + regressão à média | 3,36 |
| + mais mudança onde há mais eliminados (λ) | 3,84 |
| λ + regressão à média | 3,48 |
| **λ + γ (escolhida)** | **3,12** |
| λ + γ + regressão à média | 3,22 |

### Incerteza

Simulação de Monte Carlo (20 mil cenários) com três camadas de erro, todas
calibradas pelas eleições anteriores:

- **nacional:** todos os municípios erram juntos para o mesmo lado (é a maior
  fonte de incerteza);
- **por UF;**
- **por município.**

### Validação: cada eleição prevista com o modelo treinado nas outras

| Ano | A (1º no 1º turno) | B | Resultado de A | Previsto | Intervalo 90% | Chance de A | Erro nacional | Erro por município |
|---|---|---|---|---|---|---|---|---|
| 2002 | LULA | JOSÉ SERRA | 61,3% | 63,6% | 52,7% a 73,1% | 97% | +2,3 | 5,1 |
| 2006 | LULA | GERALDO ALCKMIN | 60,8% | 52,2% | 49,7% a 54,7% | 93% | −8,7 | 3,5 |
| 2010 | DILMA | JOSÉ SERRA | 56,1% | 56,1% | 46,2% a 65,4% | 87% | 0,0 | 2,0 |
| 2014 | DILMA | AÉCIO NEVES | 51,6% | 52,0% | 42,3% a 61,6% | 64% | +0,3 | 3,3 |
| 2018 | JAIR BOLSONARO | FERNANDO HADDAD | 55,1% | 58,9% | 49,9% a 67,1% | 95% | +3,7 | 4,0 |
| 2022 | LULA | JAIR BOLSONARO | 50,9% | 51,6% | 42,6% a 60,7% | 64% | +0,7 | 0,8 |

- O resultado real ficou dentro do intervalo de 90% em 5 das 6 eleições. A
  exceção é 2006: treinado só nas outras cinco, o modelo não conhecia um 2º
  turno em que um finalista perde votos.
- O vencedor teve mais de 50% de chance em todas, mas isso diz pouco: em todas
  elas o 1º colocado do 1º turno venceu o 2º.
- Os intervalos são largos (cerca de ±9 pontos). Com só seis eleições, uma delas
  atípica, isso é o que os dados permitem afirmar.

### Previsão para 2026

Candidatos em ordem alfabética:

| Candidato | 1º turno (válidos) | Previsto no 2º turno | Intervalo 90% | Chance de vencer |
|---|---|---|---|---|
| FLAVIO BOLSONARO | 47,0% | 50,0% | 42,3% a 57,4% | 50% |
| LULA | 45,2% | 50,0% | 42,6% a 57,7% | 50% |

**Leitura:** só com o 1º turno, o 2º está empatado. A vantagem de 1,9 ponto do
1º colocado é compensada pelo padrão histórico de o 1º colocado receber menos
da metade dos votos dos eliminados (7,8% em 2026). A margem de erro é grande
porque a história inclui uma virada atípica (2006).

**Sensibilidade a escolhas do modelo** (chance de FLAVIO BOLSONARO; a de LULA é
o complemento):

| Escolha | Previsto | Intervalo 90% | Chance |
|---|---|---|---|
| Modelo principal | 50,0% | 42,3% a 57,4% | 50% |
| Sem 2006 no treino | 49,7% | 47,3% a 52,1% | 42% |
| Mudança igual em todos os municípios | 50,1% | 42,4% a 57,6% | 51% |

Tirar 2006 deixa o intervalo bem mais estreito, mas não há motivo objetivo para
descartar uma eleição real, então o modelo principal usa todas.

A previsão por UF e por município fica em `dados/modelo/` (gerada pelo script).

### Limitações

- Não usa pesquisas, então não capta o que a campanha muda entre os turnos.
  Pesquisas podem entrar numa versão futura, se melhorarem a validação.
- Pondera os municípios pelos votos válidos do 1º turno; mudanças de
  comparecimento no 2º turno não são modeladas.
- Seis eleições é pouco: os parâmetros nacionais têm muita incerteza, e ela
  está refletida nos intervalos.

## Parte 2: ao vivo, durante a apuração

O placar parcial engana porque as urnas não chegam em ordem aleatória: cada
região apura num ritmo diferente. No 2º turno de 2022 (histórico oficial de
totalização do TSE):

- com 50% das seções apuradas (18h27), LULA tinha 49,7% dos votos válidos e
  JAIR BOLSONARO, 50,3%;
- a liderança no placar só mudou às 18h44, com 68% das seções apuradas;
- o resultado final foi LULA 50,9% e JAIR BOLSONARO 49,1%.

A previsão ao vivo corrige isso olhando para o que já chegou **e** para o que
ainda falta chegar:

1. **Coleta:** a cada minuto, o `scripts/coletar_ao_vivo.py` baixa o andamento de
   todas as UFs e o resultado dos municípios que mudaram.
2. **Votos que faltam:** para cada município, eleitores das seções ainda não
   apuradas × comparecimento esperado.
3. **Como esses votos devem se dividir:** começa pela previsão da Parte 1 para o
   município e vai se aproximando do resultado parcial do próprio município à
   medida que ele é apurado (com cautela, porque dentro de uma cidade as
   seções também não chegam em ordem aleatória).
4. **Aprender com o próprio erro:** quando um município termina, comparamos o
   resultado real com a previsão. Se o modelo está errando 1 ponto para o
   mesmo lado nos municípios já apurados de uma UF, provavelmente erra também
   nos que faltam; esse desvio (nacional e por UF) é aplicado ao que falta
   apurar. É isso que faz a previsão convergir rápido, e é aqui que a incerteza
   grande da Parte 1 deve encolher nos primeiros minutos da apuração.
5. **Simulação:** milhares de cenários para o que falta apurar, gerando a
   porcentagem final projetada com intervalo e a probabilidade de cada
   finalista, atualizadas a cada minuto.

### Teste reproduzindo a apuração de 2022

Os boletins de urna de 2022 trazem, para cada seção, os votos e a hora em que
o boletim chegou ao TSE (`DT_BU_RECEBIDO`). Com isso dá para reproduzir a
noite do 2º turno de 2022 minuto a minuto:

- conferir que a curva reproduzida bate com o histórico oficial de totalização;
- rodar o modelo ao vivo como se fosse aquela noite;
- medir com quantos % das seções apuradas a projeção ficou a menos de 0,5 ponto
  do resultado final, e se o intervalo de incerteza conteve o resultado real.

Só publicamos a previsão ao vivo de 2026 se ela passar nesse teste.

## O que será publicado

- Projeção com intervalo e probabilidade, sempre ao lado do placar oficial do TSE.
- Gráfico da noite: placar oficial × projeção ao longo da apuração.
- Depois da eleição: previsão × resultado real, incluindo os erros do modelo.
