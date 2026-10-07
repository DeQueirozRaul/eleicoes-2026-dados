# Metodologia da previsão do 2º turno

> Rascunho da abordagem. Os números de erro e incerteza serão preenchidos com
> os testes históricos antes de qualquer previsão ser publicada.

A previsão tem duas partes: uma **antes da eleição** (com base no 1º turno) e
uma **ao vivo** (atualizada durante a apuração). As duas usam só resultados
oficiais do TSE e dados do IBGE. O modelo não entrevista eleitores e, portanto,
não é pesquisa eleitoral. O resultado é sempre apresentado como probabilidade
com margem de incerteza.

Por neutralidade, o modelo trata os candidatos como "finalista A" e
"finalista B" (em ordem alfabética do nome de urna). Nada no modelo depende de
quem é o candidato ou de qual é o partido.

## Parte 1: antes do 2º turno

**Unidade:** município (5.571, mais as cidades do exterior).

**Pergunta:** sabendo como cada município votou no 1º turno, qual será a
porcentagem de cada finalista no 2º turno?

Entre um turno e outro mudam três coisas:

1. os votos dos candidatos eliminados se redistribuem (em 2026, cerca de 7,8%
   dos votos válidos);
2. parte de quem votou branco, nulo ou não foi votar muda de comportamento;
3. uma pequena parte dos eleitores troca de finalista.

**Modelo:** aprender com os 2º turnos presidenciais anteriores (2014, 2018 e
2022) a relação, município a município, entre o 1º e o 2º turno:

```
logit(% de A no 2º turno) ~ logit(% de A entre os dois finalistas no 1º turno)
                          + % dos eliminados + variação do comparecimento
                          + características do município (região, renda, IDHM, ...)
```

**Validação:** treinar com duas eleições e prever a terceira (ex.: treinar com
2014 e 2018 e prever 2022), medindo o erro em cada município e no total
nacional.

**Incerteza:** simulação de Monte Carlo com três camadas de erro, calibradas
pelos erros dos testes históricos:

- **nacional:** todos os municípios erram juntos para o mesmo lado (é a
  maior fonte de incerteza);
- **regional/UF;**
- **municipal.**

**Saída:** porcentagem projetada para cada finalista, com intervalo, e a
probabilidade de cada um terminar à frente.

**Limitação:** o modelo não usa pesquisas, então não capta o que a campanha
muda entre os turnos. A comparação com pesquisas registradas no TSE pode ser
uma análise à parte.

## Parte 2: ao vivo, durante a apuração

O placar parcial engana porque as urnas não chegam em ordem aleatória: cada
região apura num ritmo diferente. No 2º turno de 2022 (histórico oficial de
totalização do TSE):

- com 50% das seções apuradas (18h27), o candidato que venceu tinha 49,7% dos
  votos válidos;
- a liderança no placar só mudou às 18h44, com 68% das seções apuradas;
- o resultado final foi 50,9%.

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
   apurar. É isso que faz a previsão convergir rápido.
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
