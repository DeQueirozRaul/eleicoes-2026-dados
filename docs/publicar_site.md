# Como publicar o site (Streamlit Community Cloud, grátis)

O site fica num endereço como `https://eleicoes-2026-dados.streamlit.app`, que
qualquer pessoa abre no navegador ou no celular. É esse link que vai no
currículo e no LinkedIn.

## 1. Deixar o repositório público (uma vez só)

O recrutador precisa ver o código, e a publicação grátis do Streamlit funciona
com repositórios públicos.

No GitHub, abra o repositório **eleicoes-2026-dados** →
**Settings** → role até o fim (**Danger Zone**) → **Change visibility** →
**Change to public** e confirme.

> O que fica visível: o código, a documentação, os arquivos pequenos de
> `app/dados/` e o histórico de commits (inclusive o nome e o e-mail usados nos
> commits). Os dados grandes (`dados/`) não vão para o GitHub. Não há senhas
> nem chaves no repositório.

## 2. Criar o app no Streamlit (uma vez só)

1. Entre em <https://share.streamlit.io> com a sua conta (a mesma que você já
   criou, ligada ao GitHub).
2. Clique em **Create app** (canto superior direito) e escolha publicar um app
   que já está no GitHub.
3. Preencha:

   | Campo | O que colocar |
   |---|---|
   | Repository | `DeQueirozRaul/eleicoes-2026-dados` |
   | Branch | `main` |
   | Main file path | `app/site.py` |
   | App URL | um nome curto, ex.: `eleicoes-2026-dados` |

4. Em **Advanced settings**, escolha **Python 3.12** (ou a mais nova oferecida).
5. Clique em **Deploy**. A primeira vez leva alguns minutos (ele instala as
   bibliotecas de `app/requirements.txt`). Depois o site abre sozinho.

Se aparecer erro, clique em **Manage app** (canto inferior direito do site) para
ver o registro (log) e me mande o trecho em vermelho.

## 3. Atualizar o site

Não precisa fazer nada: sempre que um pull request entra na `main`, o
Streamlit percebe e atualiza o site em 1 ou 2 minutos.

Para atualizar os dados (ex.: quando o TSE publicar algo novo), rode no seu
computador `scripts\preparar_site.py`, faça commit dos arquivos de
`app/dados/` e mande para a `main`.

## 4. Na noite de 25/10

- A página **Apuração ao vivo** começa a buscar os resultados no TSE sozinha às
  16h45 (horário de Brasília) e atualiza a cada minuto. Não precisa deixar o
  seu computador ligado.
- **Abra o site umas 16h30.** Sites do plano grátis "dormem" quando ficam um
  tempo sem visitas; se aparecer um botão para acordar o app, clique e espere
  cerca de 1 minuto.
- **Não mande mudanças para a `main` durante a apuração.** Cada atualização
  reinicia o site, e o gráfico da noite recomeça do zero (o placar e a
  projeção continuam certos, só o histórico do gráfico se perde).
- Se quiser guardar a noite inteira para analisar depois, rode também no seu
  computador os dois comandos da seção "Na noite do 2º turno" do
  [guia](como_rodar.md).

## 5. Ver o site no seu computador antes de publicar

```bat
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app/site.py
```

Abre em <http://localhost:8501>. Para fechar: `Ctrl+C` no terminal.
