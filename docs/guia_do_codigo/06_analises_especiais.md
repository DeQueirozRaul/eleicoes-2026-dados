# Parte 6: análises especiais

Cada página do site tem uma ideia própria. Aqui estão as que têm uma técnica que
vale a pena entender.

## 1. Votos no número errado (RDV)

Arquivos: [`eleicoes/rdv.py`](../../eleicoes/rdv.py),
[`scripts/nulos_disputas_apertadas.py`](../../scripts/nulos_disputas_apertadas.py),
resultados em [`docs/nulos.md`](../nulos.md).

**A pergunta:** quando alguém digita para Governador o número de um candidato a
Presidente (ex.: 22 ou 13), o voto é anulado. Nas disputas de Governador muito
apertadas, quantos votos assim existiram, e eles poderiam mudar o resultado?

**Onde está a resposta:** o **RDV** (registro digital do voto) de cada urna lista
todos os votos, embaralhados e sem identificar ninguém. Nos votos nulos, ficam
registrados os dígitos digitados.

**Problema 1: o formato.** O RDV é um arquivo binário em **ASN.1/DER**. Não há
leitor pronto em Python para o formato do TSE, então
[`rdv.py`](../../eleicoes/rdv.py) percorre a estrutura na mão. DER é uma sequência
de blocos **TLV** (tag, tamanho, valor): cada bloco diz o que é, quantos bytes tem e
depois traz os bytes, que podem conter outros blocos dentro. `_tlv` lê um
cabeçalho; `_filhos` lista os blocos de dentro de um bloco; `ler_rdv` desce pela
árvore (eleição → cargo → voto) e conta `(eleição, cargo, tipo, dígitos)`.

**Problema 2: o tamanho.** Os zips de cada estado têm, para cada urna, o boletim,
a imagem do boletim, o log e o RDV. Só o RDV interessa (~5% dos bytes).
[`ZipRemotoRDV`](../../eleicoes/rdv.py) usa a mesma ideia da parte 2: lê o índice
do zip e pede ao servidor só os bytes de cada RDV, em 4 linhas de execução em
paralelo.

**Problema 3: ler errado sem perceber.** O formato mudou de 2022 para 2026 (nome
do arquivo e posição da lista de votos). Uma leitura errada não dá erro, dá números
absurdos. Por isso `ler_rdv` **recusa valores impossíveis** (cargo acima de 100,
dígitos não numéricos...) e o script **confere a soma dos votos nominais com o
resultado oficial**: bateu exatamente em 5 disputas e com diferença de no máximo
0,02% nas outras 3 (todas explicadas).

**O resultado:** em 6 das 8 disputas apertadas, os votos anulados com número de
presidenciável foram mais do que a diferença entre os dois primeiros. Sob uma
**hipótese** (quem digitou o número do presidenciável queria votar no candidato a
Governador da coligação dele), o resultado mudaria em 4. A página deixa claro que é
uma hipótese: o RDV não diz a intenção de ninguém.

## 2. Conferência dos dados e Lei de Benford

Arquivos: [`scripts/site_conferencia.py`](../../scripts/site_conferencia.py),
[`app/paginas/conferencia.py`](../../app/paginas/conferencia.py).

A página faz as perguntas que alguém desconfiado faria, e responde com somas:

- A soma das 499.248 seções bate com o resultado oficial? (Sim, voto a voto. Os
  5.246 votos no nº 28, de uma candidatura que renunciou, aparecem nas seções mas
  contam como nulos, e isso também fecha.)
- A reconstrução da apuração de 2022 bate com o histórico oficial? (Diferença média
  de 0,07 ponto no placar.)

E explica por que a **Lei de Benford não prova fraude**. Benford diz que, em
números que se espalham por várias ordens de grandeza (1, 10, 100, 1.000...), o
primeiro dígito é 1 em ~30% dos casos:

```python
valores = np.log10(1 + 1 / digitos)          # P(1) = 30,1%, P(2) = 17,6%, ..., P(9) = 4,6%
```

Mas uma seção tem algumas centenas de eleitores: os votos por seção não se espalham
por várias ordens de grandeza, então **não deveriam seguir Benford**, com ou sem
fraude. A página mostra isso com os dados de todos os candidatos: todos "falham"
igualmente, o que mostra que o teste é inadequado, não que houve fraude.

## 3. Mapa do DF: em qual região fica cada local de votação

Arquivo: [`scripts/site_df.py`](../../scripts/site_df.py).

O TSE informa a latitude e a longitude de cada local de votação, mas não a região
administrativa (RA). As RAs vêm do IPE-DF como polígonos. Para cada local: **em
qual polígono o ponto está?**

```python
arvore = STRtree(geometrias)                                   # índice espacial
...
ponto = Point(x, y)
dentro = [i for i in arvore.query(ponto) if geometrias[i].contains(ponto)]
if dentro:
    saida.append(ras[dentro[0]]["ra"])
    continue
i = arvore.nearest(ponto)                                      # caiu fora de todas?
saida.append(ras[i]["ra"] if geometrias[i].distance(ponto) < 0.02 else None)
```

Testar o ponto contra as 35 regiões funcionaria, mas o **índice espacial**
(`STRtree`, da biblioteca Shapely) descarta primeiro as que estão longe, olhando só
os retângulos em volta de cada polígono (`query`), e só então faz o teste exato
(`contains`). É a mesma ideia de um índice de banco de dados, só que para geometria.

Cuidados:

- Um ponto na divisa, com a coordenada um pouco imprecisa, pode cair fora de todas
  as regiões. Nesse caso fica a região mais próxima, se estiver a menos de ~2 km
  (`nearest` + `distance`).
- Coordenadas fora do DF (erro de cadastro, ou "-1" para "sem coordenada") viram
  nulo, e o local fica em "Sem localização".
- A soma das seções por região é conferida com o resultado oficial do DF em cada
  disputa.

## 4. Candidatos e patrimônio

Arquivo: [`scripts/site_candidatos.py`](../../scripts/site_candidatos.py).

**Quem conta.** Só as candidaturas que **foram a voto** (estavam na urna e os
votos contaram como válidos). Quem desistiu ou foi barrado fica de fora. Em 2026,
o resultado vem dos arquivos de resultado do TSE e, para quem foi ao 2º turno, do
resultado do 2º turno.

**A mesma pessoa em anos diferentes.** Para saber como o patrimônio de alguém
mudou de 2018 para 2026, é preciso saber que é a mesma pessoa:

```python
def chave_pessoa(cpf, nome, nascimento):
    """CPF quando existe; senão nome sem acento + data de nascimento."""
```

**Descontar a inflação.** R$ 1 milhão em 2018 não vale R$ 1 milhão em 2026. O
IPCA vem do IBGE (SIDRA, tabela 1737) como variação mensal; o código monta um
**número-índice** (multiplicando as variações acumuladas) e o fator de cada ano é
`índice de 2026 ÷ índice do ano`:

```python
return (1 + variacao.sort_index() / 100).cumprod()     # número-índice
```

**Mediana, não média.** Patrimônio é muito concentrado (o 1% que mais declarou tem
47% de todo o patrimônio declarado em 2026). A média seria puxada por poucos
milionários; a mediana mostra o candidato típico. E grupos com menos de 10 pessoas
não têm valor publicado: com 3 pessoas, o "típico" seria uma pessoa só.

## 5. Eleitorado

Arquivo: [`scripts/site_eleitorado.py`](../../scripts/site_eleitorado.py).

Perfil dos eleitores (idade, gênero, escolaridade) e quem deixou de votar, por
perfil. Dois cuidados que aparecem no código:

- **O TSE mudou o nome de uma coluna** de 2022 para 2026. `coluna_escolaridade`
  olha o cabeçalho do arquivo e usa a que existir.
- **O 2º turno de 2026 foi publicado antes da eleição, já preenchido** (todo mundo
  "compareceu"). O código só usa um turno se ele tiver abstenção.

## 6. Dinheiro de campanha

Arquivos: [`scripts/site_dinheiro.py`](../../scripts/site_dinheiro.py),
[`app/paginas/dinheiro.py`](../../app/paginas/dinheiro.py).

O cuidado principal é **não contar o mesmo real duas vezes**:

- O partido repassa R$ 100 do fundo eleitoral para o candidato A, e A repassa R$ 30
  para B. Somando as receitas de A e de B, daria R$ 130, mas só existiram R$ 100.
  Por isso as receitas com origem "Recursos de outros candidatos" não entram no
  total, e as despesas "Doações a outros candidatos/partidos" também não.
- Só a **prestação final** de cada candidato entra. Os relatórios parciais
  repetiriam as mesmas receitas.

Outras decisões:

- **Nenhum nome de doador pessoa física** é gravado; a página mostra só somas e a
  concentração ("o 1% que mais doou deu 35% do valor").
- **O fundo eleitoral para mulheres e para pessoas pretas e pardas** é comparado,
  partido a partido, com a parte delas entre as candidaturas e com o mínimo de 30%.
  O texto diz que é um "ponto de atenção, não acusação": a conferência oficial é da
  Justiça Eleitoral e inclui gastos que esta soma não capta.
- **Gasto e votos andam juntos, mas isso não prova que dinheiro elege.** Os partidos
  concentram o fundo em quem já tem mais chance. A página diz isso ao lado do
  gráfico.

## Para praticar

1. Na página de conferência, a lei de Benford é testada no **2º dígito** também.
   Leia `benford(posicao=2)` em [`site_conferencia.py`](../../scripts/site_conferencia.py)
   e explique por que o 2º dígito é mais uniforme que o 1º.
2. Em [`site_dinheiro.py`](../../scripts/site_dinheiro.py), calcule quanto as
   candidaturas a Senador receberam de recursos próprios, em reais e em %.

## Na entrevista

Escolha uma, a que você achar mais interessante, e conte em 1 minuto. Sugestão,
a do RDV:

> "Queria saber quantos votos para Governador foram anulados porque o eleitor
> digitou o número de um candidato a Presidente. Isso só está no registro digital
> do voto, um arquivo binário em ASN.1. Escrevi um leitor que percorre a estrutura
> byte a byte e, para não baixar gigabytes, leio só os pedaços do zip que são RDV.
> Como uma leitura errada não dá erro, dá número absurdo, o leitor recusa valores
> impossíveis e o script confere os votos com o resultado oficial."
