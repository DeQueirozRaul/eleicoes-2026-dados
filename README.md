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

Toda análise é testada contra dados reais antes de ser usada:

| Análise | Como foi testada | Resultado |
|---|---|---|
| Coletor ao vivo | soma dos 5.757 municípios × total nacional (1º turno de 2026) | 0 votos de diferença |
| Base histórica (2002–2022) | soma dos candidatos × votos válidos, município a município | 0 diferenças (exceto 18.876 votos sem explicação nos arquivos de 2006, 0,02%) |
| Previsão do 2º turno antes da eleição | cada eleição de 2002 a 2022 prevista com as outras cinco | erro nacional mediano de 1,5 ponto (médio 2,6; pior caso 8,7, em 2006); 3,1 pontos por município; resultado dentro do intervalo de 90% em 5 de 6 |
| Cenários de transferência dos eliminados | mesmo teste, de 2006 a 2022 | erro médio de 3,4 pontos, pior que o modelo principal (2,7); por isso fica só como cenário |
| Reprodução da apuração de 2022 | curva reproduzida × histórico oficial de totalização | 0,4 ponto no % apurado e 0,07 ponto no % do candidato |
| Previsão ao vivo, 2º turno de 2022 | erro em relação ao resultado final | 0,5 ponto com 10% apurado (placar oficial: 2,9); 0,6 com 50% (placar: 1,2); final dentro do intervalo de 90% em 93% dos momentos |
| Previsão ao vivo, 1º turno de 2022 | erro em relação ao resultado final | 0,7 ponto com 10% apurado (placar oficial: 5,8); 0,4 com 50% (placar: 3,8); final dentro do intervalo em 100% dos momentos |

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
- **Cuidado para não se enganar.** Os testes de 2022 já ajudaram a desenhar a
  previsão ao vivo. O teste realmente independente será a noite de 25/10/2026,
  e o resultado será publicado aqui, acertando ou errando.

## Fontes de dados

| Fonte | O que usamos |
|---|---|
| [Resultados do TSE](https://resultados.tse.jus.br) (JSON ao vivo) | Apuração minuto a minuto, por município |
| [Portal de Dados Abertos do TSE](https://dadosabertos.tse.jus.br) | Candidatos, bens, prestação de contas, eleitorado, votação por seção, boletins de urna e histórico da totalização (2014 a 2026) |
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

```bash
python -m venv .venv
source .venv/bin/activate          # no Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# 1. resultado do 1º turno de 2026 para Presidente, município a município (~2 min)
python scripts/coletar_ao_vivo.py --eleicao 6257 --cargo 1

# 2. resultados presidenciais de 2002 a 2022 (só os arquivos nacionais, ~15 s)
python scripts/baixar_historico.py

# 3. monta o banco dados/eleicoes.duckdb e roda as checagens de qualidade
python scripts/montar_base.py

# 4. valida o modelo nas eleições passadas e gera a previsão do 2º turno de 2026
python scripts/prever_2t.py

# 5. de onde vieram os eleitores dos eliminados e cenários de transferência
python scripts/cenarios_transferencia.py

# 6. teste da previsão ao vivo reproduzindo as apurações de 2022
python scripts/baixar_boletins_2022.py --turno 2    # e --turno 1 (~1,2 GB de download)
python scripts/reproduzir_apuracao_2022.py
python scripts/testar_ao_vivo_2022.py --turno 2     # e --turno 1
python scripts/grafico_apuracao_2022.py

# na noite do 2º turno (25/10), em dois terminais:
python scripts/coletar_ao_vivo.py --eleicao 6258 --cargo 1 --intervalo 60
python scripts/previsao_ao_vivo.py --eleicao 6258 --intervalo 60

pytest
```

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
- [ ] Análises: resultados, perfil dos candidatos, patrimônio, eleitorado,
      dinheiro de campanha
- [ ] Recorte do Distrito Federal
- [ ] Site público (Streamlit) e painéis em Power BI
