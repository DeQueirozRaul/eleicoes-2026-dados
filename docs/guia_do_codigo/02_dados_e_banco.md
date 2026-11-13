# Parte 2: dados e banco

Arquivos principais: [`eleicoes/tse_arquivos.py`](../../eleicoes/tse_arquivos.py),
[`eleicoes/tse_ao_vivo.py`](../../eleicoes/tse_ao_vivo.py),
[`scripts/baixar_historico.py`](../../scripts/baixar_historico.py),
[`scripts/coletar_ao_vivo.py`](../../scripts/coletar_ao_vivo.py),
[`scripts/montar_base.py`](../../scripts/montar_base.py) e a pasta [`sql/`](../../sql).

## 1. De onde vêm os dados

| Fonte | Formato | Usado para |
|---|---|---|
| **Portal de Dados Abertos do TSE** (`cdn.tse.jus.br`) | zips com CSV, separador `;`, codificação Latin-1 | resultados de 2002 a 2026, candidatos, bens, eleitorado, boletins de urna, prestação de contas |
| **Site de resultados do TSE** (`resultados.tse.jus.br`) | JSON, um arquivo por UF, município e cargo | apuração ao vivo e resultados de 2026 |
| **IBGE** (API do SIDRA e de malhas) | JSON e GeoJSON | população do Censo, inflação (IPCA), contorno dos municípios |
| **IPE-DF** (WFS) | GeoJSON | contorno das 35 regiões administrativas do DF |

## 2. Baixar só o que precisa: leitura parcial de zip (HTTP Range)

O zip com os resultados de 2022 tem **640 MB**: um CSV por UF e um nacional. Só
precisamos do nacional (~40 MB). Baixar 640 MB para usar 40 é desperdício.

O truque está em [`ArquivoRemoto`](../../eleicoes/tse_arquivos.py). Duas coisas
tornam isso possível:

1. **O índice do zip fica no fim do arquivo.** Um zip guarda, no final, uma lista
   com o nome, a posição e o tamanho de cada arquivo de dentro. Lendo só o fim,
   sabemos onde está o CSV que queremos.
2. **O servidor aceita pedidos parciais.** Com o cabeçalho HTTP
   `Range: bytes=1000-1999`, o servidor manda só aqueles bytes.

`ArquivoRemoto` finge ser um arquivo comum (herda de `io.RawIOBase`): tem `seek`
(ir para uma posição) e `readinto` (ler bytes). Por baixo, cada leitura vira um
pedido `Range`. Como o módulo `zipfile` do Python só usa `seek` e `read`, ele
funciona com o arquivo remoto sem saber que é remoto:

```python
def _bloco(self, indice: int) -> bytes:
    inicio = indice * self.bloco
    fim = min(inicio + self.bloco, self.tamanho) - 1
    resposta = self.sessao.get(self.url, headers={"Range": f"bytes={inicio}-{fim}"}, ...)
```

Os blocos são de 4 MB e os mais recentes ficam guardados (`self._cache`), porque o
`zipfile` volta um pouco às vezes. Resultado: 40 MB baixados em vez de 640.

**Por que assim?** A alternativa era baixar tudo e apagar o resto. Funciona, mas
em conexões lentas leva muito tempo e pode encher o disco. A mesma ideia é usada no
RDV (parte 6), onde a economia é ainda maior.

## 3. Ler os CSVs do TSE sem cair nas pegadinhas

[`ler_csv_tse`](../../eleicoes/tse_arquivos.py) resolve três problemas de uma vez:

```python
pd.read_csv(caminho, sep=";", encoding="latin-1", dtype=str, usecols=colunas,
            na_values=SEM_INFORMACAO, keep_default_na=False)
```

- `encoding="latin-1"`: o TSE não usa UTF-8. Sem isso, "Eleição" vira "EleiÃ§Ã£o".
- `dtype=str`: tudo entra como texto e a conversão é feita depois, coluna a coluna.
  Senão o código de município `01120` viraria o número `1120`, perdendo o zero.
- `na_values=["#NULO#", "#NE#", ...]`: o TSE escreve "sem informação" de vários
  jeitos; todos viram nulo.

Outras pegadinhas que apareceram (cada uma virou uma regra no código, com um
comentário explicando):

- **Voto em trânsito de 2010:** aparece como se fosse uma UF, "VT".
- **2006:** 18.876 votos não fecham nos próprios arquivos do TSE (0,02% do total).
  A checagem aceita essa diferença conhecida.
- **Um arquivo de 2026** trocou o nome de uma coluna (`CD_GRAU_ESCOLARIDADE` →
  `CD_GRAU_INSTRUCAO`); o código detecta qual existe.
- **O 2º turno de 2026 foi publicado antes da eleição já preenchido**, com
  abstenção zero; o código filtra.
- **No arquivo de despesas de campanha**, o tipo da prestação está escrito "Final";
  no de receitas, "FINAL". O arquivo também tem bytes que o leitor de CSV recusa;
  o script converte para UTF-8 antes de ler.

## 4. O cliente do site de resultados (JSON)

[`ClienteTSE`](../../eleicoes/tse_ao_vivo.py) baixa os mesmos arquivos que o
aplicativo Resultados do TSE usa. Não é uma API documentada: os caminhos foram
descobertos lendo o arquivo de configuração do próprio site (`ele-c.json`):

```
/oficial/ele2026/6258/dados/sp/sp-e006258-ab.json            andamento de cada município de SP
/oficial/ele2026/6258/dados/sp/sp71072-c0001-e006258-u.json  resultado de Presidente em São Paulo
```

Três cuidados:

1. **Repetir quando falha, esperando cada vez mais** (2, 4, 8 segundos). Isso se
   chama *backoff exponencial*: não sobrecarrega o servidor e dá tempo para um
   problema passageiro passar.
2. **404 não é erro.** Antes da eleição, o arquivo ainda não existe; o método
   devolve `None` e quem chamou decide o que fazer.
3. **Converter o formato do TSE para tabela.** O JSON é aninhado (cargo →
   coligação → partido → candidato) e os números vêm como texto (`"47,03"`).
   [`ler_resultado`](../../eleicoes/tse_ao_vivo.py) percorre os níveis e devolve
   uma tabela com uma linha por candidato, só com contagens inteiras. As
   porcentagens são recalculadas, nunca copiadas.

## 5. O banco: DuckDB e SQL

[`scripts/montar_base.py`](../../scripts/montar_base.py) é curto. Ele roda os
arquivos de [`sql/`](../../sql) em ordem e depois as checagens:

```python
for arquivo in sorted((RAIZ / "sql").glob("*.sql")):
    con.execute(arquivo.read_text(encoding="utf-8"))
```

As tabelas, na ordem em que são criadas:

| Arquivo | Tabela | Uma linha por |
|---|---|---|
| `01_votos_presidente.sql` | `votos_presidente` | ano, turno, município e candidato |
| `02_comparecimento_presidente.sql` | `comparecimento_presidente` | ano, turno e município (aptos, comparecimento, brancos, nulos) |
| `03_municipios.sql` | `municipios` | município, com códigos TSE e IBGE e região |
| `04_transicao_turnos.sql` | `finalistas`, `transicao_turnos` | ano e município: 1º e 2º turno lado a lado (é a base do modelo) |
| `05_composicao_eleitorado.sql` | `composicao_eleitorado` | ano, turno, município e opção (candidato, branco/nulo, abstenção) |

Alguns recursos de SQL que valem a pena entender, todos usados aqui:

**DuckDB lê CSV e Parquet direto, sem importar antes:**

```sql
from read_csv('dados/brutos/votacao_candidato_munzona_*_BR.csv',
              delim = ';', encoding = 'latin-1', all_varchar = true, union_by_name = true)
```

O `*` lê todos os anos de uma vez; `union_by_name` junta arquivos cujas colunas
mudaram de ordem entre um ano e outro.

**`qualify` filtra pelo resultado de uma função de janela.** O coletor ao vivo
guarda vários retratos do mesmo município; queremos só o mais recente:

```sql
qualify row_number() over (
    partition by turno, uf, cd_municipio_tse, nr_candidato order by dt_coleta desc
) = 1
```

Em SQL comum, isso exigiria uma subconsulta.

**`filter` dentro da soma.** Em `04_transicao_turnos.sql`, uma só passada pela
tabela soma os votos de A, de B e dos eliminados:

```sql
sum(v.qt_votos) filter (where f.finalista = 'A') as qt_a,
sum(v.qt_votos) filter (where f.finalista = 'B') as qt_b,
sum(v.qt_votos) filter (where f.finalista is null) as qt_eliminados
```

**`group by all`:** o DuckDB agrupa por todas as colunas que não são somas, sem
precisar repetir a lista.

## 6. Checagens: o banco se confere sozinho

Cada arquivo em [`sql/checagens/`](../../sql/checagens) é uma consulta que lista
**as linhas com problema**. O esperado é nenhuma linha. Exemplo:

```sql
-- A soma dos votos dos candidatos deve ser igual aos votos válidos do município.
select v.ano, v.turno, v.uf, v.cd_municipio_tse, sum(v.qt_votos) as soma_candidatos, c.qt_validos
from votos_presidente v
join comparecimento_presidente c using (ano, turno, uf, cd_municipio_tse)
group by all
having sum(v.qt_votos) <> c.qt_validos;
```

`montar_base.py` roda todas e devolve código de erro se alguma achar problema. É
um **teste de dados**: o teste de código (parte 7) confere se o programa faz o
que deve; o teste de dados confere se os dados fazem sentido.

**Por que assim?** Uma checagem que lista os problemas é melhor que uma que diz
só "falhou": você já vê os municípios errados e começa a investigar dali.

## 7. Parquet como formato intermediário

Quase todo arquivo que um script grava é Parquet (`.to_parquet(...)` no pandas,
`copy (...) to 'x.parquet'` no DuckDB). Comparado a CSV:

- **Menor:** comprimido e colunar (guarda cada coluna junta, e colunas repetitivas
  comprimem muito). O CSV de despesas de campanha tem 1,1 GB; filtrado e em
  Parquet, cerca de 10 MB.
- **Com tipos:** um número continua número e uma data continua data. Não tem
  vírgula decimal nem codificação para dar errado.
- **Rápido:** o DuckDB e o pandas leem só as colunas pedidas.

## Para praticar

1. Com o banco montado, abra um Python e rode:

   ```python
   import duckdb
   con = duckdb.connect("dados/eleicoes.duckdb", read_only=True)
   con.sql("select ano, turno, sum(qt_abstencoes) / sum(qt_aptos) as abstencao "
           "from comparecimento_presidente group by all order by all")
   ```

   Compare com a página Resultados do site.
2. Escreva uma checagem nova: "todo município com 2º turno também tem 1º turno".
   Dica: `left join` e `where ... is null`.

## Na entrevista

> "Os dados do TSE têm muita pegadinha: codificação antiga, códigos para 'sem
> informação', formatos que mudam de um ano para outro. Leio tudo como texto e
> converto coluna a coluna. Para não baixar 640 MB para usar 40, leio só o pedaço
> do zip que interessa, com pedidos HTTP parciais. O banco é DuckDB, montado com
> arquivos SQL em ordem, e tem checagens que listam as linhas que não batem. Se
> alguma acha problema, o processo para."
