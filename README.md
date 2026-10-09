# Eleições 2026 em dados

Análise dos dados públicos das eleições brasileiras de 2026, com comparações
históricas, um olhar para o Brasil inteiro e um recorte específico do
**Distrito Federal**. Tudo é feito a partir de dados oficiais e abertos (TSE e
IBGE), com código aberto e reprodutível.

![Placar oficial e projeção ao vivo na noite do 2º turno de 2022](docs/img/apuracao_2022_2t.png)

*Teste da previsão ao vivo reproduzindo a apuração do 2º turno de 2022 seção por
seção: a projeção ficou do lado do vencedor desde 5% apurado, mais de uma hora
antes de o placar oficial virar (o mesmo aconteceu no 1º turno).
[Como funciona](docs/previsao.md#parte-2-ao-vivo-durante-a-apuração).*

**Para rodar no seu computador:** [passo a passo](docs/como_rodar.md).

## ⚖️ Compromisso de neutralidade

Este é um projeto **apartidário**. Ele não apoia, critica nem faz campanha
para nenhum candidato, partido ou campo político. Na prática:

- **Só dados oficiais e públicos** (TSE, IBGE), com a fonte citada em cada análise.
- **Mesmo tratamento para todos:** toda análise é aplicada igualmente a todos os
  candidatos e partidos, nunca a um só.
- **Ordem e cores neutras:** candidatos sempre em ordem alfabética do nome de urna
  e cores que não lembram nenhum partido.
- **Linguagem descritiva:** os textos dizem o que os dados mostram ("teve 47,0% dos
  votos válidos"), sem adjetivos nem juízo de valor.
- **Previsões são probabilidades,** sempre com margem de incerteza, nunca
  "fulano vai ganhar". O modelo usa só resultados oficiais: não é pesquisa
  eleitoral e não entrevista eleitores.
- **Ponto de atenção não é acusação:** quando um critério objetivo destaca algo
  (ex.: um gasto fora do padrão), o critério vale para todos e o caso é
  apresentado como algo a verificar.
- **Reprodutível:** o código e o passo a passo estão aqui; qualquer pessoa pode
  refazer as contas.
- **Erros são corrigidos em público,** com registro do que mudou.
- **O resultado oficial é sempre o do TSE.**

## Quão bem funciona (e quanto erra)

Toda análise foi testada contra dados reais antes de ser usada.

> **Como ler os números:** "ponto" (ou ponto percentual) é a diferença entre duas
> porcentagens. Se a projeção dizia 50,4% e o resultado final foi 50,9%, o erro
> foi de **0,5 ponto**.

| Análise | Como testamos | Resultado |
|---|---|---|
| **Coletor ao vivo** | Somamos os votos dos 5.757 municípios e comparamos com o total do Brasil divulgado pelo TSE (1º turno de 2026). | Bateu exatamente: nenhum voto de diferença. |
| **Base histórica (2002–2022)** | Em cada município, conferimos se a soma dos votos dos candidatos é igual ao total de votos válidos. | Bateu em todos os municípios. Única exceção: 18.876 votos de 2006 que não fecham nos próprios arquivos do TSE (0,02% do total). |
| **Previsão do 2º turno antes da eleição** | "Escondemos" o resultado de cada eleição de 2002 a 2022 e tentamos prevê-lo usando só as outras cinco. | Em metade das eleições o erro foi de até 1,5 ponto; no pior caso (2006), 8,7 pontos. O resultado real ficou dentro da margem de erro do modelo em 5 das 6 eleições. |
| **Cenários de transferência dos eliminados** | O mesmo teste, de 2006 a 2022. | Errou em média 3,4 pontos, mais que o modelo principal (2,7). Por isso é usado só para montar cenários, não como previsão. |
| **Reprodução da apuração de 2022** | Reconstruímos a noite da apuração urna por urna e comparamos, minuto a minuto, com o registro oficial do TSE. | Quase idêntica: diferença média de 0,4 ponto no total de urnas apuradas e de 0,07 ponto no placar. |
| **Previsão ao vivo: 2º turno de 2022** | Rodamos a previsão como se fosse aquela noite e comparamos com o resultado final (LULA 50,9%). | Com 10% das urnas apuradas, a projeção estava a **0,5 ponto** do resultado final, enquanto o placar oficial estava a **2,9 pontos**. Com metade apurada: 0,6 contra 1,2. Em 93% das atualizações, o resultado final estava dentro da margem de erro da projeção. |
| **Previsão ao vivo: 1º turno de 2022** | O mesmo teste, com o placar entre LULA e JAIR BOLSONARO. | Com 10% apurado: **0,7 ponto** de erro, contra **5,8** do placar oficial. Com metade apurada: 0,4 contra 3,8. O resultado final esteve dentro da margem de erro em 100% das atualizações. |
| **Leitura dos votos digitados na urna (RDV)** | Nas 9 disputas de Governador analisadas, somamos os votos de cada candidato lidos voto a voto no RDV e comparamos com o resultado oficial. | Bateu exatamente em 6 disputas; nas outras 3, diferença de no máximo 0,02% (uma urna ilegível no RS e votos em candidaturas indeferidas em SC e na BA). |

## Destaque: votos para Governador anulados com o número de um presidenciável

Quem digita para Governador o número de um candidato a Presidente (por exemplo, 13 ou 22) e
não existe candidato a Governador com esse número no estado tem o voto anulado.
O TSE publica o registro de cada voto digitado (RDV), então dá para contar.

Nas 9 disputas de Governador mais apertadas de 2022 e 2026:

- **Em 7 das 9**, esses votos eram mais do que os que bastariam para mudar o
  resultado. Exemplo: no DF em 2026, faltaram 2.177 votos para a disputa
  terminar no 1º turno, e 30.034 votos foram anulados assim.
- Supondo que cada eleitor queria votar no candidato da coligação do partido
  daquele número, **o resultado mudaria em 4** (DF, AC, ES e PR, todas em 2026,
  nos dois sentidos).
- O RDV não diz a intenção do eleitor e **o resultado oficial é o do TSE**; a
  análise mede quanto a confusão entre números pesa em disputas apertadas.

[Tabela completa, método e ressalvas](docs/nulos.md).

## Dificuldades e aprendizados

- **A "API" ao vivo do TSE não é documentada.** Os caminhos foram mapeados a
  partir do arquivo de configuração do próprio site e podem mudar. Os arquivos
  do 2º turno de 2026 ainda não estavam publicados em 07/10.
- **Arquivos grandes e servidor que limita downloads.** Os resultados históricos
  somam ~1,9 GB e os boletins de urna mais ~1,2 GB. A solução foi ler só o
  pedaço necessário de cada zip (HTTP Range) e baixar em partes, com volta ao
  download simples quando o servidor recusa.
- **Dados com pegadinhas.** Codificação Latin-1, `;` como separador, códigos
  como `#NULO#` e `-1`, código de município do TSE diferente do IBGE, votos
  anulados apurados em separado, voto em trânsito como se fosse uma UF ("VT") em
  2010 e 18.876 votos de 2006 que não fecham. Cada caso virou uma checagem
  automática em `sql/checagens`.
- **Pouca história para aprender.** Há só seis 2º turnos desde 2002, e um deles
  (2006) foi atípico. Por isso a previsão de antes da eleição tem margem grande.
  Estreitar sem pesquisas seria fingir precisão.
- **Uma boa ideia que não funcionou.** Prever o 2º turno pela "tendência" dos
  eleitores dos eliminados (de que lado votaram na eleição anterior) errou mais
  que o modelo simples. A inferência ecológica também é instável por
  candidato: a estimativa para um mesmo candidato variou de 32% a 62% conforme
  a forma de agrupar os municípios.
- **A previsão ao vivo falhou antes de funcionar.** Na primeira versão, o
  intervalo de 90% continha o resultado em só 8% dos momentos; nos primeiros
  minutos a projeção oscilava muito; e no 1º turno ficou 2 pontos enviesada por
  horas, porque os municípios pequenos apuram primeiro e votaram diferente das
  capitais. Cada falha virou um ajuste documentado em
  [docs/previsao.md](docs/previsao.md).
- **Arquivo binário sem leitor pronto.** O RDV vem em ASN.1 (formato binário)
  e o formato mudou entre 2022 e 2026 (nome do arquivo e posição da lista de
  votos). Uma leitura errada derrubou horas de processamento; agora valores
  impossíveis são rejeitados, a leitura é salva em partes e a soma é sempre
  conferida com o resultado oficial.
- **Cuidado para não se enganar.** Os testes de 2022 já ajudaram a desenhar a
  previsão ao vivo. O teste realmente independente será a noite de 25/10/2026,
  e o resultado será publicado aqui, acertando ou errando.

## Fontes de dados

| Fonte | O que usamos |
|---|---|
| [Resultados do TSE](https://resultados.tse.jus.br) (JSON ao vivo) | Apuração minuto a minuto, por município |
| [Portal de Dados Abertos do TSE](https://dadosabertos.tse.jus.br) | Candidatos, bens, prestação de contas, eleitorado, votação por seção, boletins de urna, registro digital do voto (RDV) e histórico da totalização (2014 a 2026) |
| IBGE | População, Censo 2022, PIB municipal |

Códigos das eleições de 2026 nos arquivos ao vivo:

| Código | Eleição |
|---|---|
| 6257 | Presidente, 1º turno |
| 6258 | Presidente, 2º turno |
| 6259 | Governador, Senador, deputados (1º turno) |
| 6260 | Governador, 2º turno |

## Estrutura

```
eleicoes/          código reutilizável (leitura dos dados do TSE e modelo de 2º turno)
scripts/           coletas e rotinas executáveis
sql/               transformações em SQL (DuckDB) e checagens de qualidade (sql/checagens)
tests/             testes automatizados (com arquivos reais do TSE em tests/fixtures)
docs/              metodologia
dados/             dados baixados e gerados (fora do git; recriados pelos scripts)
```

## Como rodar

**Passo a passo completo, pensado para Windows: [docs/como_rodar.md](docs/como_rodar.md).**

Resumo:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt

:: essencial (~5 min): 1º turno de 2026, histórico, banco, previsão e cenários
.venv\Scripts\python scripts\rodar_tudo.py

:: tudo (~1h30): também as apurações de 2022, gráficos e votos nulos nas disputas apertadas
.venv\Scripts\python scripts\rodar_tudo.py --completo

:: testes automáticos
.venv\Scripts\python -m pytest
```

Os resultados ficam em `dados\` e, prontos para Excel e Power BI, em `dados\exportar\`.
No Linux e no Mac, troque `.venv\Scripts\python` por `.venv/bin/python`.

O banco `dados/eleicoes.duckdb` tem as tabelas:

| Tabela | Conteúdo |
|---|---|
| `votos_presidente` | votos por eleição, turno, município e candidato (2002 a 2026) |
| `comparecimento_presidente` | aptos, comparecimento, abstenção, brancos, nulos e válidos |
| `municipios` | cadastro com códigos TSE e IBGE e região |
| `finalistas` | os dois primeiros colocados de cada eleição |
| `transicao_turnos` | base do modelo: 1º e 2º turno lado a lado, por município |
| `composicao_eleitorado` | eleitorado de cada município por opção (candidato, branco/nulo, abstenção) |
| `secoes_2022` | 2022, por seção: votos dos finalistas e hora em que o boletim chegou ao TSE |

```sql
-- % de cada candidato no 1º turno de 2026, por região
select m.regiao, v.nm_urna,
       round(100 * sum(v.qt_votos) / sum(sum(v.qt_votos)) over (partition by m.regiao), 2) as pct
from votos_presidente v
join municipios m using (uf, cd_municipio_tse)
where v.ano = 2026 and v.turno = 1
group by m.regiao, v.nm_urna
order by m.regiao, pct desc;
```

## Roteiro

- [x] Coletor dos resultados ao vivo, testado com o 1º turno de 2026 (a soma dos
      5.757 municípios e cidades do exterior bate com o total nacional)
- [x] Base histórica de Presidente (2002 a 2026) em DuckDB, com códigos TSE ↔ IBGE
      e checagens de qualidade
- [x] Modelo de previsão do 2º turno, validado nas eleições de 2002 a 2022
      ([metodologia e resultados](docs/previsao.md))
- [x] Cenários de transferência dos votos dos eliminados, com a origem dos
      eleitores estimada por inferência ecológica ([resultados](docs/previsao.md#cenários-para-onde-vão-os-eleitores-dos-eliminados))
- [x] Previsão ao vivo durante a apuração, testada reproduzindo as duas
      apurações de 2022 seção por seção ([resultados](docs/previsao.md#parte-2-ao-vivo-durante-a-apuração))
- [x] Votos para Governador anulados com número de presidenciável nas disputas
      apertadas, contados voto a voto no RDV ([resultados](docs/nulos.md))
- [ ] Análises: resultados, perfil dos candidatos, patrimônio, eleitorado,
      dinheiro de campanha
- [ ] Recorte do Distrito Federal
- [ ] Site público (Streamlit) e painéis em Power BI
