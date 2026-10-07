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
eleicoes/          código reutilizável (leitura e limpeza dos dados)
scripts/           coletas e rotinas executáveis
tests/             testes automatizados (com arquivos reais do TSE em tests/fixtures)
docs/              metodologia
dados/             dados baixados e gerados (fora do git; recriados pelos scripts)
```

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate          # no Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# baixa o resultado do 1º turno de 2026 para Presidente, município a município
python scripts/coletar_ao_vivo.py --eleicao 6257 --cargo 1

# na noite do 2º turno: uma varredura por minuto até o fim da apuração
python scripts/coletar_ao_vivo.py --eleicao 6258 --cargo 1 --intervalo 60

pytest
```

Os dados ficam em `dados/ao_vivo/` em Parquet e podem ser consultados direto com
DuckDB:

```sql
select nm_urna, sum(qt_votos) as votos
from 'dados/ao_vivo/e6257_c1/*/candidatos.parquet'
where cd_municipio_tse <> ''
group by nm_urna
order by nm_urna;
```

## Roteiro

- [x] Coletor dos resultados ao vivo, testado com o 1º turno de 2026 (a soma dos
      5.757 municípios e cidades do exterior bate com o total nacional)
- [ ] Base histórica (2014, 2018, 2022 e 2026) em DuckDB, com códigos TSE ↔ IBGE
- [ ] Modelo de previsão do 2º turno ([metodologia](docs/previsao.md))
- [ ] Previsão ao vivo durante a apuração, testada reproduzindo a apuração de 2022
- [ ] Análises: resultados, perfil dos candidatos, patrimônio, eleitorado,
      dinheiro de campanha
- [ ] Recorte do Distrito Federal
- [ ] Site público (Streamlit) e painéis em Power BI
