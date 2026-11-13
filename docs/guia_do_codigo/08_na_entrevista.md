# Parte 8: na entrevista

## A apresentação em 30 segundos

> "Fiz um projeto sobre as eleições de 2026 só com dados oficiais do TSE e do IBGE.
> É um pipeline de ponta a ponta: Python baixa e limpa os dados, DuckDB e SQL
> organizam, modelos estatísticos preveem o 2º turno, e um site em Streamlit mostra
> tudo. Na noite da eleição, o site projetou o resultado ao vivo. Ele acertou o lado
> do vencedor o tempo todo, mas começou errando, e depois eu descobri por quê com os
> dados oficiais."

## Em 2 minutos (se pedirem para detalhar)

1. **O problema:** o placar parcial da apuração engana, porque as regiões apuram
   em ritmos diferentes.
2. **Os dados:** resultados de 2002 a 2026 por município, boletins de urna,
   candidatos, eleitorado. Arquivos grandes, com muita pegadinha de formato.
3. **O que construí:**
   - um banco em DuckDB com checagens que conferem as somas com o oficial;
   - um modelo que prevê o 2º turno só com o 1º, validado deixando cada eleição de
     fora;
   - uma projeção ao vivo que roda dentro do site.
4. **O resultado:**
   - **Previsão de antes da eleição:** o resultado ficou dentro do intervalo.
   - **Noite da apuração:** a projeção ficou do lado de quem venceu em todas as
     atualizações, e o placar oficial só virou às 20h25.
5. **O que aprendi:**
   - **O erro:** a projeção começou errando 3 pontos. Refiz a noite com os dados
     oficiais e separei o erro do modelo do erro da coleta.
   - **A causa:** uma suposição do modelo sobre as primeiras seções de cada
     município.

## Números para saber de cor

| O quê | Número |
|---|---|
| Resultado do 2º turno | FLAVIO BOLSONARO 48,21% × LULA 51,79% |
| Previsão de antes da eleição | 50,0% (intervalo de 42,3% a 57,4%), erro de 1,7 ponto |
| Validação histórica | dentro do intervalo em 5 de 6 eleições (2002 a 2022) |
| Projeção ao vivo, 25% apurado | 0,1 ponto de erro, contra 2,3 do placar oficial |
| Projeção ao vivo, começo | 3 pontos de erro com 5% apurado |
| Conferência | soma das 499.248 seções = resultado oficial, voto a voto |
| Dados brutos | mais de 3 GB; o site lê poucos MB |
| Testes | ~130 testes automáticos |

## Histórias para contar

Use a estrutura: **situação → o que eu fiz → resultado → o que aprendi.**

### 1. A noite da eleição

- **Situação:** às 19h30 o servidor do TSE começou a recusar pedidos (erro 429). A
  projeção ficou atrasada em relação ao TSE.
- **O que fiz:**
  - **Menos pedidos:** reduzi o número de pedidos e priorizei os municípios que
    mais tinham avançado.
  - **Reinício sem perda:** fiz o gravador salvar o estado, para poder reiniciar sem
    baixar tudo de novo.
  - **Um bug escondido:** no meio disso, percebi que 331 municípios apareciam como
    apurados com zero votos. O cache do TSE entregava um arquivo mais velho que o
    andamento. Corrigi e escrevi um teste para o caso.
- **Resultado:** a gravação seguiu até o fim, sem falhas.
- **Aprendizado:** dados ao vivo falham de jeitos que um teste com dados parados não
  mostra. Hoje cada um desses casos tem um teste.

### 2. Descobrir a causa de um erro

- **Situação:** a projeção começou errando 3 pontos. Podia ser a coleta (atraso,
  arquivos atrasados) ou o modelo.
- **O que fiz:** com arquivos que o TSE publicou depois, refiz a noite de três jeitos:
  - como saiu ao vivo;
  - com a coleta perfeita;
  - com os votos chegando na ordem do 1º turno.
- **Resultado:**
  - **O modelo:** com a coleta perfeita, o erro continuava. Então era do modelo.
  - **A causa:** as primeiras seções de cada município puxavam para o mesmo lado, e o
    modelo tratava isso como ruído independente.
- **Aprendizado:** antes de corrigir, montar um experimento que separe as hipóteses.

### 3. Vazamento de dados

- **Situação:** depois da eleição, o banco passou a ter o 2º turno de 2026.
- **O que fiz:** percebi que o script de previsão treinava com "todas as eleições
  com 2º turno", ou seja, passaria a usar o resultado que deveria prever. Restringi o
  treino aos anos anteriores.
- **Aprendizado:** vazamento de dados é sutil. O código funcionava, mas o número
  ficaria "bom demais" sem ninguém perceber.

### 4. Uma ideia sofisticada que perdeu para a simples

- **Situação:** parecia óbvio que saber "de que lado" eram os eleitores dos
  eliminados melhoraria a previsão.
- **O que fiz:** implementei inferência ecológica (regressão com restrições, em SciPy)
  e testei do mesmo jeito que o modelo principal.
- **Resultado:** errou mais (3,4 pontos contra 2,7). Ficou só para cenários.
- **Aprendizado:** a decisão é da validação, não da intuição.

### 5. Dados que mudam de formato

- **Situação:**
  - **Despesas de campanha:** um filtro devolveu zero despesas, porque um arquivo
    escrevia "Final" e outro "FINAL".
  - **Mapa do DF:** o servidor de mapas passou a devolver página vazia para o Python.
- **O que fiz:** corrigi cada caso, e o script passou a **parar** quando uma tabela
  sai vazia, em vez de gravar silenciosamente.
- **Aprendizado:** um erro que grava resultado vazio é pior que um que quebra.

## Perguntas prováveis

**Por que DuckDB e não pandas ou PostgreSQL?**
Pandas carrega tudo na memória; alguns arquivos têm 1 GB. PostgreSQL exige um
servidor. O DuckDB lê CSV e Parquet direto, roda dentro do Python e é muito rápido
para análise. O banco inteiro é um arquivo.

**Por que trabalhar em logit?**
Porque a porcentagem tem limites (0 e 100%) e o logit não: somar uma mudança nunca
dá uma porcentagem impossível. E uma mudança perto dos extremos pesa diferente de
uma perto de 50%, o que o logit já trata.

**Como você sabe que o modelo funciona?**
Validação deixando cada eleição de fora: treino com cinco, prevejo a sexta sem ver o
resultado. E em 2026, o teste de verdade, sem ajuste nenhum depois.

**O que significa "intervalo de 90%"?**
Que, se o modelo estiver bem calibrado, o resultado cai dentro dele em 9 de cada 10
vezes. Por isso medi quantas vezes o resultado ficou dentro: 92% das atualizações ao
vivo entre 5% e 99,5% apurado.

**Como garantiu neutralidade?**
Com regras no código, e não na boa vontade:
- candidatos sempre em ordem alfabética;
- cores que não lembram partido;
- a mesma análise para todos;
- textos que descrevem dados, sem adjetivo;
- "ponto de atenção não é acusação".

**Como você lidou com arquivos grandes?**
Três coisas:
- **Ler só o necessário:** pedidos HTTP parciais para ler só o arquivo de dentro do
  zip que importa.
- **Parquet no lugar de CSV.**
- **Separar o pesado do site:** os scripts resumem tudo antes, e o site só lê arquivos
  pequenos.

**O que você faria diferente?**
- **O modelo ao vivo:** um termo de erro comum às apurações parciais.
- **Testes ao vivo:** simular falhas do servidor, como o 429 e o cache atrasado,
  antes da noite.
- **O Power BI:** começar mais cedo, em paralelo ao site.

**Qual foi a parte mais difícil?**
Escolha uma das histórias acima e conte com detalhes. Responder com uma situação
concreta vale mais que uma resposta genérica.

## Sobre ter usado IA no projeto

É provável que perguntem como o projeto foi feito. A melhor resposta é a verdadeira.
Algo como:

> "Usei um assistente de IA como par de programação: ele escreveu boa parte do
> código comigo. As decisões eram minhas: o que analisar, as regras de neutralidade,
> o que publicar. E eu conferi e entendi cada parte. Posso explicar qualquer trecho."

E então **mostre que entende**: abra um arquivo e explique. É para isso que este
guia existe. Dizer a verdade e demonstrar domínio do que foi feito pesa mais do que
qualquer outra coisa.

## O que mostrar (e em que ordem)

1. **O site, página inicial:** o resultado e os achados. 30 segundos.
2. **A página Apuração ao vivo:** o gráfico da noite e "o que a prorrogação mudou".
   É a história mais forte.
3. **O README no GitHub:** a tabela "Quão bem funciona", que mostra que tudo foi
   testado.
4. **Um arquivo de código**, se pedirem: `eleicoes/ao_vivo.py` ou
   `eleicoes/modelo_2t.py`, que têm a explicação no começo.
5. **O painel do Power BI**, quando estiver pronto.

## Para praticar

Grave você mesmo (no celular) explicando o projeto em 2 minutos. Assista. Onde você
travou é o que precisa reler neste guia.
