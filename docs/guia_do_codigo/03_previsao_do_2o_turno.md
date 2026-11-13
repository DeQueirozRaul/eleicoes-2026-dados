# Parte 3: previsão do 2º turno

Arquivos: [`eleicoes/modelo_2t.py`](../../eleicoes/modelo_2t.py) (o modelo),
[`scripts/prever_2t.py`](../../scripts/prever_2t.py) (validação e previsão),
[`eleicoes/transferencia.py`](../../eleicoes/transferencia.py) e
[`scripts/cenarios_transferencia.py`](../../scripts/cenarios_transferencia.py)
(cenários). Resultados em [`docs/previsao.md`](../previsao.md).

## O problema

Depois do 1º turno, só sabemos quanto cada candidato teve. A pergunta é: **o que o
1º turno, sozinho, diz sobre o 2º?** Sem pesquisa: só resultados oficiais de
2002 a 2022, as seis eleições com 2º turno.

## Por que trabalhar em "logit"

O modelo não trabalha com a porcentagem direto, mas com o logit dela:

```python
def logit(p):
    return np.log(p / (1 - p))
```

| % | logit |
|---|---|
| 50% | 0 |
| 60% | 0,41 |
| 90% | 2,20 |
| 99% | 4,60 |

Dois motivos:

1. **A porcentagem tem limites (0% e 100%); o logit não.** Se o modelo somar uma
   mudança de +15 pontos a um município com 90%, dá 105%, impossível. Em logit,
   somar qualquer valor sempre volta para uma porcentagem válida (com `logistica`,
   a função inversa).
2. **A mesma mudança "pesa" diferente perto dos extremos.** Ganhar 5 pontos onde o
   candidato tem 50% é fácil; onde ele tem 95%, quase impossível. O logit já trata
   isso naturalmente.

## O modelo, em duas etapas

A = 1º colocado do 1º turno no país, B = 2º colocado. Para cada município *i*:
`z_i` é o logit do % de A entre os dois no 1º turno, `e_i` é a parte dos votos
válidos que foi para os eliminados, e `y_i` é o que queremos: o logit do % de A
no 2º turno. As mesmas letras em maiúscula (Z, E, Y) são o total do país.

### Etapa 1: quanto o placar muda no país

```
delta = Y − Z = k × E + choque
```

A mudança entre os turnos (`delta`) tende a ser proporcional ao tamanho do voto
nos eliminados (`E`): sem eliminados, não há quem mude o placar. `k` é estimado
com as eleições passadas, numa regressão sem intercepto
([`ajustar`](../../eleicoes/modelo_2t.py)):

```python
k = float((delta * nac["E"]).sum() / soma_e2)          # mínimos quadrados sem intercepto
residuos = delta - k * nac["E"]
tau = float(np.sqrt((residuos ** 2).sum() / max(len(nac) - 1, 1)))   # tamanho do "choque"
```

`tau` mede o quanto as eleições fogem da regra. Em 2006 o choque foi grande:
o 1º colocado ganhou muito mais do que os eliminados explicariam.

### Etapa 2: como a mudança se distribui pelos municípios

```
y_i = z_i + delta
      + lambda × delta × (e_i / E − 1)     muda mais onde há mais eliminados
      + gamma × e_i × (z_i − Z)            eliminados se dividem de forma mais equilibrada que o município
      + efeito da UF + ruído do município
```

`lambda` e `gamma` vêm de uma regressão por **mínimos quadrados ponderados** (cada
município pesa pelos seus votos, para um povoado de 800 eleitores não pesar como
São Paulo). O ruído de cada município tem duas partes: uma fixa (`sigma_mun`) e
uma que diminui com o tamanho (`c / votos`), porque município pequeno varia mais
por acaso.

**Por que esses termos e não outros?** Foram testadas seis versões
(tabela em [`docs/previsao.md`](../previsao.md)). A escolhida (λ + γ) foi a que
errou menos por município nas eleições passadas. Um termo de "regressão à média"
parecia razoável, mas piorou o erro e saiu. **Decidir pelos números da validação,
e não pela intuição**, é uma das coisas mais importantes do projeto.

## A incerteza: simular milhares de cenários

O modelo não dá um número só. [`simular`](../../eleicoes/modelo_2t.py) sorteia
10.000 cenários. Em cada um:

1. sorteia o `delta` do país. A distribuição é uma **t de Student**, e não a normal,
   porque com só seis eleições de treino a incerteza sobre o próprio `tau` é grande;
   a t tem caudas mais grossas e dá mais chance a surpresas;
2. sorteia um efeito para cada UF e um ruído para cada município;
3. calcula o % de A em cada município e soma, pesando pelos votos.

Com os 10.000 resultados nacionais, a previsão é a mediana, o intervalo de 90% vai
do percentil 5 ao 95 e a "chance de vencer" é a fração de cenários acima de 50%.

```python
for inicio in range(0, cenarios, lote):        # 500 cenários de cada vez
    d = delta[inicio:inicio + lote]
    base = np.stack([prever_municipios(modelo, df, di) for di in d])
    u = rng.normal(0, modelo.sigma_uf, size=(len(d), len(ufs)))[:, uf_idx]
    eps = rng.normal(0, 1, size=base.shape) * sd_mun
    s = logistica(base + u + eps)
```

**Por que em lotes de 500?** Cada lote é uma matriz de cenários × 5.700
municípios. Com 10.000 cenários de uma vez seriam 57 milhões de números (mais de
400 MB). Em lotes, a memória fica pequena e o resultado é o mesmo.

Repare no `[:, uf_idx]`: o efeito sorteado da UF é **copiado para todos os
municípios daquela UF**. É assim que o modelo diz que municípios do mesmo estado
erram juntos.

## A validação: deixar uma eleição de fora

Como saber se o modelo funciona? [`prever_2t.py`](../../scripts/prever_2t.py)
faz a **validação "deixa uma de fora"**: para cada eleição de 2002 a 2022, treina
com as outras cinco e prevê aquela, sem ver o resultado dela.

```python
for ano in sorted(dados.loc[dados["y"].notna(), "ano"].unique()):
    modelo = ajustar(dados[dados["ano"] != ano])     # treina sem o ano
    r = simular(modelo, dados[dados["ano"] == ano]).resumo()   # prevê o ano
```

| Ano | Real (A) | Previsto | Erro | Dentro do intervalo de 90%? |
|---|---|---|---|---|
| 2002 | 61,3% | 63,6% | +2,3 | sim |
| 2006 | 60,8% | 52,2% | −8,7 | **não** |
| 2010 | 56,1% | 56,1% | 0,0 | sim |
| 2014 | 51,6% | 52,0% | +0,3 | sim |
| 2018 | 55,1% | 58,9% | +3,7 | sim |
| 2022 | 50,9% | 51,6% | +0,7 | sim |

E em 2026, o teste de verdade: previsto 50,0% para FLAVIO BOLSONARO (intervalo de
42,3% a 57,4%, chance de 50%), resultado 48,21%. Erro de 1,7 ponto, dentro do
intervalo.

**Cuidado que o código tem de ter:** depois da eleição, o banco passa a ter o 2º
turno de 2026. Se o script treinasse com "todas as eleições que têm 2º turno", a
"previsão" de 2026 já saberia a resposta. Isso se chama **vazamento de dados**
(*data leakage*), e o script treina só com `ano < 2026`.

## Os cenários de transferência (e por que não viraram a previsão)

Uma ideia mais intuitiva: "os eleitores do candidato X eram de direita, então vão
para o candidato de direita". [`eleicoes/transferencia.py`](../../eleicoes/transferencia.py)
tenta estimar de onde vieram os eleitores de cada eliminado. Como não existe voto
individual, só totais por município, a técnica é a **inferência ecológica**
(regressão de Goodman com restrições):

```
fração do município que votou em k agora ≈ Σ_r  fração que votou em r antes × P[r, k]
```

`P[r, k]` é a parte de quem votou em `r` na eleição anterior que agora votou em
`k`. Com 5.500 municípios dá para estimar `P`, com a restrição de que cada valor
fique entre 0 e 1 e cada linha some 1. Isso é feito com `scipy.optimize.lsq_linear`
(mínimos quadrados com limites), e a "soma 1" entra como uma penalidade alta.

O resultado é interessante, mas na validação **errou mais** que o modelo simples
(3,4 pontos contra 2,7, em média). Por isso ficou como ferramenta de cenários
("e se 70% dos eleitores de X forem para Y?") e não como previsão. É um bom exemplo
para entrevista: **nem toda ideia sofisticada vence a simples, e você só sabe
testando.**

## Para praticar

1. Em [`modelo_2t.py`](../../eleicoes/modelo_2t.py), troque o `standard_t` por
   `standard_normal` na `simular` e rode `prever_2t.py`. O que acontece com os
   intervalos? E com 2006?
2. Calcule à mão: se `k = 0,5` e os eliminados tiveram 10% (`E = 0,1`), qual o
   `delta` esperado em logit? E em pontos, partindo de 50%?
   (Resposta: 0,05 em logit, ou cerca de 1,25 ponto.)

## Na entrevista

> "O modelo tem duas etapas: quanto o placar muda no país, proporcional ao voto
> nos eliminados, e como isso se distribui pelos municípios. Trabalho em logit
> para a porcentagem nunca passar de 0 a 100. A incerteza vem de simular 10 mil
> cenários com efeitos de UF e de município. Validei deixando cada eleição de fora:
> o resultado ficou dentro do intervalo em 5 de 6, e em 2026 também. Testei uma
> ideia mais sofisticada, a inferência ecológica, mas ela errou mais na validação,
> então ficou só para cenários."
