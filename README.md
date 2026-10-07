# Eleições 2026 em dados

Análise dos dados públicos das eleições brasileiras de 2026, com comparações
históricas, um olhar para o Brasil inteiro e um recorte específico do
**Distrito Federal**. Tudo é feito a partir de dados oficiais e abertos (TSE e
IBGE), com código aberto e reprodutível.

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

# na noite do 2º turno: uma varredura por minuto até o fim da apuração
python scripts/coletar_ao_vivo.py --eleicao 6258 --cargo 1 --intervalo 60

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
- [ ] Previsão ao vivo durante a apuração, testada reproduzindo a apuração de 2022
- [ ] Análises: resultados, perfil dos candidatos, patrimônio, eleitorado,
      dinheiro de campanha
- [ ] Recorte do Distrito Federal
- [ ] Site público (Streamlit) e painéis em Power BI
