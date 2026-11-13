# Parte 7: testes e qualidade

Arquivos: a pasta [`tests/`](../../tests), [`pytest.ini`](../../pytest.ini) e as
checagens em [`sql/checagens/`](../../sql/checagens).

O projeto se protege de erros em três camadas:

| Camada | Pergunta | Onde |
|---|---|---|
| **Testes de código** | o programa faz o que deveria? | `tests/` (pytest) |
| **Checagens de dados** | os dados fazem sentido? As somas batem? | `sql/checagens/` e conferências dentro dos scripts |
| **Revisão visual** | o site mostra certo? | `tests/test_site.py` e as fotos de `scripts/ver_site.py` |

## 1. Testes de código com pytest

Para rodar todos (uns 10 segundos):

```bat
.venv\Scripts\python -m pytest
```

O [`pytest.ini`](../../pytest.ini) diz onde estão os testes e põe a raiz do
projeto no caminho de importação (por isso os testes conseguem fazer
`from eleicoes.ao_vivo import projetar`).

Um teste é uma função que começa com `test_` e usa `assert`:

```python
def test_tudo_apurado_projecao_igual_ao_placar():
    df = apurar(municipios(), 1.0)
    p = projetar(df, cenarios=500)
    assert p.pct_secoes == pytest.approx(1)
    assert p.pct_a_mediana == pytest.approx(p.pct_a_apurado, abs=1e-6)
    assert p.pct_a_superior - p.pct_a_inferior < 1e-6
```

Repare no **nome**: ele diz o que deveria acontecer. Quando um teste falha, o nome
já explica o que quebrou.

## 2. Testar sem internet: dados inventados e "falsos"

Os testes nunca acessam o TSE. Três técnicas:

**Dados inventados com resposta conhecida.** Em
[`test_ao_vivo.py`](../../tests/test_ao_vivo.py), `municipios()` cria 300
municípios em que o resultado real é a previsão + 0,10. O teste confere se a
projeção **descobre** esse erro de 0,10 com parte dos municípios apurados. Como
você criou os dados, você sabe a resposta certa.

**Objetos falsos ("fakes").** Em [`test_acompanhamento.py`](../../tests/test_acompanhamento.py),
`ClienteFalso` tem os mesmos métodos do `ClienteTSE` (`andamento`, `resultado`),
mas devolve dados fixos, e dá para mandar ele falhar de propósito:

```python
class ClienteFalso:
    def resultado(self, eleicao, cargo, uf="br", municipio=""):
        if municipio in self.falhar:
            self.falhar.discard(municipio)
            raise requests.HTTPError("403 Forbidden")   # recusa passageira do servidor do TSE
        ...
```

O motor da apuração recebe o cliente como parâmetro
(`Acompanhamento(..., cliente=ClienteFalso())`). Isso se chama **injeção de
dependência**, e é o que torna o motor testável: em produção ele recebe o cliente
de verdade; no teste, o falso.

Os erros da noite de 25/10 viraram testes assim: o TSE recusando um arquivo, o
arquivo de um município mais velho que o andamento, o gravador reiniciando no meio.
**Todo bug corrigido ganha um teste**, para não voltar.

**Arquivos de verdade, pequenos.** Em [`tests/fixtures/`](../../tests/fixtures) há
um JSON real do TSE e dois RDVs reais (um de 2022, um de 2026). Os testes do leitor
de RDV usam esses arquivos: se o formato mudar de novo, o teste pega.

## 3. Testar o site

[`tests/test_site.py`](../../tests/test_site.py) abre cada página com o `AppTest`
do Streamlit (sem navegador) e falha se alguma der erro:

```python
@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_abre_sem_erro(pagina):
    app = AppTest.from_file(str(APP / "site.py"), default_timeout=60)
    app.run()
    app.switch_page(f"paginas/{pagina}").run()
    assert not app.exception, [e.message for e in app.exception]
```

`parametrize` roda o mesmo teste uma vez para cada página. Já pegou, por exemplo,
a página de patrimônio quebrando depois do 2º turno: ela supunha que sempre
haveria candidatos "no 2º turno".

## 4. Checagens de dados

Explicadas na parte 2: cada SQL em `sql/checagens/` lista as linhas com problema.
Além delas, os scripts conferem as somas com o oficial e **param** quando algo não
bate:

```python
for nr in (22, 13):
    print(f"  {NOMES_2026[nr]}: soma dos municípios − oficial = "
          f"{int(m[f'votos_{nr}'].sum()) - int(numeros[nr])}")
```

Um ponto que custou caro aprender: **um script que grava um resultado vazio sem
reclamar é pior do que um que quebra.** Depois que um filtro devolveu zero despesas
de campanha (por causa do "Final" × "FINAL"), o script passou a conferir que as
tabelas têm linhas antes de seguir.

## 5. Neutralidade como regra de código

As regras de neutralidade não dependem de lembrar delas a cada gráfico: estão no
código.

- `cores_finalistas(nomes)` sempre dá violeta ao 1º em ordem alfabética, em todas
  as páginas.
- Listas de candidatos são ordenadas com `sorted(...)`.
- O texto dos "pontos de atenção" é o mesmo para todos os partidos, gerado a partir
  dos dados, e sempre acompanhado de "ponto de atenção não é acusação".

## 6. Git: o histórico como documentação

- **Commits pequenos, com mensagem que explica o porquê.** Ex.: "Apuração ao vivo:
  arquivo de município atrasado e limite de pedidos", com o que mudou e por quê.
- **Mudanças em ramo separado e pull request** para a `main`. A `main` é o site
  publicado; nada vai para ela sem os testes passarem.
- **Nada de mudança na `main` durante a apuração:** cada atualização reinicia o site.

## Para praticar

1. Quebre algo de propósito: em [`app/comum.py`](../../app/comum.py), troque
   `"pontos"` por `"pts"` em `pontos()`. Rode `pytest`. Algum teste pega? (Se não,
   escreva um que pegue.)
2. Escreva um teste para `chave_pessoa` em
   [`site_candidatos.py`](../../scripts/site_candidatos.py): com CPF, a chave começa
   com `cpf:`; sem CPF, usa nome sem acento e data de nascimento.

## Na entrevista

> "Tenho testes em três níveis: testes de código com pytest, com dados inventados
> onde eu sei a resposta e objetos falsos no lugar do TSE; checagens de dados em SQL
> que listam o que não bate; e um teste que abre cada página do site. Todo bug que
> apareceu, inclusive os da noite da eleição, virou um teste."
