# Como rodar o projeto no seu computador

Guia passo a passo para **Windows** (no Linux e no Mac os comandos estão no
final). Não precisa saber nada além de copiar e colar comandos num terminal.

## 1. O que instalar (uma vez só)

1. **Python 3.11 ou mais novo:** baixe em <https://www.python.org/downloads/>.
   Na primeira tela do instalador, **marque "Add python.exe to PATH"**.
2. **GitHub Desktop** (mais fácil que o git de linha de comando):
   <https://desktop.github.com/>. Entre com a sua conta do GitHub.

Espaço em disco: ~1 GB para o modo essencial, ~5 GB para o completo.

## 2. Baixar o projeto

No GitHub Desktop: **File → Clone repository → eleicoes-2026-dados → Clone**.
Anote a pasta onde ele salvou (por exemplo `C:\Users\voce\Documents\GitHub\eleicoes-2026-dados`).

Para atualizar depois: botão **Fetch origin / Pull origin** no GitHub Desktop.

## 3. Abrir um terminal na pasta do projeto

No GitHub Desktop: **Repository → Open in Command Prompt** (ou "Open in
PowerShell"). O terminal já abre na pasta certa.

## 4. Preparar o ambiente (uma vez só)

Cole, uma linha de cada vez:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

A primeira linha cria um "ambiente virtual" (uma cópia do Python só para este
projeto); a segunda instala as bibliotecas (pandas, DuckDB etc.). Leva 1–3 min.

## 5. Rodar

```bat
.venv\Scripts\python scripts\rodar_tudo.py
```

Esse é o **modo essencial** (~5 min). Ele mostra cada etapa e onde fica o
resultado:

| Etapa | O que faz | Onde fica o resultado |
|---|---|---|
| 1 | Baixa o 1º turno de 2026 (Presidente), município a município | `dados\ao_vivo\` |
| 2 | Baixa os resultados de Presidente de 2002 a 2022 | `dados\brutos\` |
| 3 | Monta o banco de dados e confere a qualidade dos dados | `dados\eleicoes.duckdb` |
| 4 | Testa o modelo do 2º turno nas eleições passadas e prevê 2026 | `dados\modelo\` |
| 5 | Cenários de transferência dos votos dos eliminados | `dados\modelo\` |
| 6 | Exporta as tabelas em CSV | `dados\exportar\` |

Para rodar **tudo** (inclui a reprodução das apurações de 2022, os gráficos e
os votos nulos nas disputas apertadas; ~1h30 e ~2 GB de download):

```bat
.venv\Scripts\python scripts\rodar_tudo.py --completo
```

Se cair a internet no meio, é só rodar de novo: o que já foi baixado não é
baixado outra vez.

## 6. Ver os resultados

- **Excel ou Power BI:** abra os arquivos de `dados\exportar\`. Estão com `;`
  como separador e vírgula decimal. No Power BI: **Obter dados → Texto/CSV**.
- **Gráficos:** `docs\img\` (depois do modo completo).
- **SQL direto no banco:** com o DuckDB dá para consultar tudo em SQL:

  ```bat
  .venv\Scripts\python -c "import duckdb; duckdb.connect('dados/eleicoes.duckdb').sql('select ano, count(*) from transicao_turnos group by ano order by ano').show()"
  ```

  Ou instale o [DBeaver](https://dbeaver.io/) (gratuito), crie uma conexão
  **DuckDB** e aponte para `dados\eleicoes.duckdb`: dá para navegar nas tabelas
  e escrever SQL como em qualquer banco.

### O que tem em cada arquivo de resultado

| Arquivo | O que é |
|---|---|
| `validacao_historica.csv` | cada eleição de 2002 a 2022 prevista com as outras: previsto × real |
| `previsao_2026_uf.csv` | previsão do 2º turno de 2026 por estado |
| `cenarios_transferencia_2026.csv` | resultado do 2º turno em cada cenário de fidelidade dos eleitores dos eliminados |
| `teste_ao_vivo_2022_1t.csv` e `_2t.csv` | a cada 2 minutos da noite de 2022: placar oficial × projeção |
| `disputas_governador.csv` | quantos votos bastariam para mudar cada disputa de Governador |
| `nulos_disputas_apertadas.csv` | nas disputas apertadas: votos nulos com número de presidenciável × margem |

## 7. Conferir que está tudo certo (testes automáticos)

```bat
.venv\Scripts\python -m pytest
```

Deve terminar com "passed" e nenhum "failed".

## 8. Na noite do 2º turno (25/10)

Abra **dois** terminais na pasta do projeto:

```bat
:: terminal 1: baixa a apuração a cada minuto
.venv\Scripts\python scripts\coletar_ao_vivo.py --eleicao 6258 --cargo 1 --intervalo 60

:: terminal 2: calcula a projeção a cada minuto (aparece a partir de 5% apurado)
.venv\Scripts\python scripts\previsao_ao_vivo.py --eleicao 6258 --intervalo 60
```

## Problemas comuns

| Mensagem | O que fazer |
|---|---|
| `'python' não é reconhecido` | reinstale o Python marcando **"Add python.exe to PATH"** e abra um terminal novo |
| `ModuleNotFoundError` | faltou o passo 4, ou o comando foi rodado com `python` em vez de `.venv\Scripts\python` |
| erro de conexão / `403` | o site do TSE às vezes limita downloads; espere alguns minutos e rode de novo |
| `No space left on device` / disco cheio | libere espaço; a pasta `dados\brutos\` pode ser apagada e baixada de novo |

## Linux e Mac

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/rodar_tudo.py            # ou --completo
.venv/bin/python -m pytest
```
