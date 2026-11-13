"""Prepara a página "Dinheiro de campanha" (app/paginas/dinheiro.py): quanto as candidaturas de 2026
arrecadaram e gastaram, de onde veio o dinheiro e quanto custou cada voto.

Fonte: TSE, Portal de Dados Abertos, prestação de contas eleitorais dos candidatos de 2026
(https://dadosabertos.tse.jus.br/dataset/prestacao-de-contas-eleitorais-2026), arquivo atualizado
todo dia:
    https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2026.zip

Regras de contagem:
- só a **prestação final do 1º turno** de cada candidato. As contas do 2º turno dos 14 finalistas
  (Presidente e Governador em 6 UFs) vencem em 24/11 e ficam de fora; quem só entregou relatórios
  parciais também (são contados à parte);
- **doações de um candidato a outro não entram no total**: o dinheiro já foi contado onde entrou
  (no partido ou no primeiro candidato), e somar de novo contaria duas vezes. Pelo mesmo motivo, as
  despesas não incluem os repasses a outros candidatos ou partidos;
- receitas "estimáveis" (serviços e bens doados, não dinheiro) entram, com o valor declarado;
- votos: arquivos de resultado do 1º turno do TSE, baixados por scripts/site_candidatos.py;
  cor ou raça e gênero: cadastro das candidaturas (o mesmo da página Perfil dos candidatos).

Nenhum nome de doador pessoa física é gravado: a página mostra só somas e a concentração.

Antes: scripts/site_candidatos.py.

    python scripts/site_dinheiro.py
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
BRUTOS = RAIZ / "dados" / "brutos" / "contas"
CANDIDATOS = RAIZ / "dados" / "brutos" / "candidatos"
SAIDA = RAIZ / "app" / "dados"
URL = ("https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/"
       "prestacao_de_contas_eleitorais_candidatos_2026.zip")
ARQUIVOS = {
    "receitas": ("receitas_candidatos_2026_BRASIL.csv",
                 ["SQ_CANDIDATO", "DS_CARGO", "SG_UF", "SG_PARTIDO", "DS_FONTE_RECEITA", "DS_ORIGEM_RECEITA",
                  "DS_NATUREZA_RECEITA", "NR_CPF_CNPJ_DOADOR", "VR_RECEITA", "DT_GERACAO"]),
    "despesas": ("despesas_contratadas_candidatos_2026_BRASIL.csv",
                 ["SQ_CANDIDATO", "DS_CARGO", "SG_PARTIDO", "DS_ORIGEM_DESPESA", "VR_DESPESA_CONTRATADA"]),
}
CARGOS = {"Deputado Distrital": "Deputado Estadual ou Distrital", "Deputado Estadual": "Deputado Estadual ou Distrital"}
ORDEM_CARGOS = ["Presidente", "Governador", "Senador", "Deputado Federal", "Deputado Estadual ou Distrital"]
CATEGORIAS = ["Fundo eleitoral", "Fundo partidário", "Partido (outros recursos)", "Pessoas físicas",
              "Recursos próprios", "Outros"]


# --- dados -------------------------------------------------------------------------
def baixar() -> None:
    """Baixa o zip (~450 MB), guarda só a prestação final do 1º turno em Parquet e apaga os CSVs."""
    BRUTOS.mkdir(parents=True, exist_ok=True)
    if all((BRUTOS / f"{nome}.parquet").exists() for nome in ARQUIVOS):
        return
    zip_local = BRUTOS / "candidatos_2026.zip"
    if not zip_local.exists():
        print("  baixando a prestação de contas dos candidatos (~450 MB)", flush=True)
        with requests.get(URL, stream=True, timeout=600) as r, open(zip_local, "wb") as f:
            r.raise_for_status()
            for bloco in r.iter_content(8 * 1024 * 1024):
                f.write(bloco)
    with zipfile.ZipFile(zip_local) as zf:
        for nome, (membro, colunas) in ARQUIVOS.items():
            if (BRUTOS / f"{nome}.parquet").exists():
                continue
            csv = Path(zf.extract(membro, BRUTOS))
            para_utf8(csv)
            duckdb.sql(f"""
                copy (
                    select {", ".join(colunas)}
                    from read_csv('{csv.as_posix()}', delim = ';', all_varchar = true)
                    where ST_TURNO = '1' and upper(TP_PRESTACAO_CONTAS) = 'FINAL'   -- "FINAL" nas receitas, "Final" nas despesas
                ) to '{(BRUTOS / f"{nome}.parquet").as_posix()}' (format parquet)
            """)
            if nome == "receitas":   # quem só entregou parcial: contado à parte
                duckdb.sql(f"""
                    copy (
                        select SQ_CANDIDATO, bool_or(upper(TP_PRESTACAO_CONTAS) = 'FINAL') as tem_final
                        from read_csv('{csv.as_posix()}', delim = ';', all_varchar = true)
                        where ST_TURNO = '1' group by 1
                    ) to '{(BRUTOS / "prestadores.parquet").as_posix()}' (format parquet)
                """)
            csv.unlink()
    # só apaga o zip se as duas tabelas saíram com linhas (senão, dá para investigar sem baixar de novo)
    if all(duckdb.sql(f"select count(*) from '{(BRUTOS / f'{nome}.parquet').as_posix()}'").fetchall()[0][0]
           for nome in ARQUIVOS):
        zip_local.unlink()
    else:
        raise RuntimeError("uma das tabelas da prestação de contas saiu vazia; o zip foi mantido")


def para_utf8(csv: Path) -> None:
    """Regrava o CSV em UTF-8. O leitor de CSV recusa como latin-1 o arquivo de despesas de 2026 (tem bytes
    nulos e outros soltos); o Python decodifica latin-1 sem falhar. Em pedaços, sem carregar 1 GB na memória."""
    limpo = csv.with_suffix(".utf8")
    with open(csv, "rb") as origem, open(limpo, "wb") as destino:
        while bloco := origem.read(64 * 1024 * 1024):
            destino.write(bloco.replace(b"\x00", b"").decode("latin-1").encode("utf-8"))
    limpo.replace(csv)


def valor(coluna: str) -> str:
    return f"replace({coluna}, ',', '.')::double"


def carregar(con) -> None:
    con.execute(f"""
        create or replace table receitas as
        select SQ_CANDIDATO as sq_candidato, DS_CARGO as ds_cargo, SG_PARTIDO as sg_partido,
               DS_FONTE_RECEITA as fonte, DS_ORIGEM_RECEITA as origem, DS_NATUREZA_RECEITA as natureza,
               NR_CPF_CNPJ_DOADOR as doador, {valor("VR_RECEITA")} as valor, DT_GERACAO as dt_geracao,
               case
                   when DS_FONTE_RECEITA = 'FUNDO ESPECIAL' or DS_ORIGEM_RECEITA like 'Fundo Especial%'
                       then 'Fundo eleitoral'
                   when DS_FONTE_RECEITA = 'FUNDO PARTIDARIO' or DS_ORIGEM_RECEITA = 'Fundo Partidário'
                       then 'Fundo partidário'
                   when DS_ORIGEM_RECEITA = 'Recursos de partido político' then 'Partido (outros recursos)'
                   when DS_ORIGEM_RECEITA in ('Recursos de pessoas físicas', 'Doações pela Internet')
                       then 'Pessoas físicas'
                   when DS_ORIGEM_RECEITA = 'Recursos próprios' then 'Recursos próprios'
                   else 'Outros'
               end as categoria
        from read_parquet('{(BRUTOS / "receitas.parquet").as_posix()}')
        -- doação de um candidato a outro: o dinheiro já foi contado onde entrou
        where DS_ORIGEM_RECEITA <> 'Recursos de outros candidatos'
    """)
    con.execute(f"""
        create or replace table despesas as
        select SQ_CANDIDATO as sq_candidato, DS_CARGO as ds_cargo, DS_ORIGEM_DESPESA as categoria,
               {valor("VR_DESPESA_CONTRATADA")} as valor
        from read_parquet('{(BRUTOS / "despesas.parquet").as_posix()}')
        -- repasse a outro candidato ou partido não é gasto de campanha: quem recebe é que gasta
        where DS_ORIGEM_DESPESA <> 'Doações financeiras a outros candidatos/partidos'
    """)


def votos_1t() -> pd.DataFrame:
    """Votos de cada candidato no 1º turno, dos arquivos de resultado do TSE."""
    linhas = []
    for caminho in sorted((CANDIDATOS / "resultados_2026").glob("*.json")):
        u = json.loads(caminho.read_text(encoding="utf-8"))
        for c in u["carg"]:
            for agr in c["agr"]:
                for par in agr["par"]:
                    for cand in par["cand"]:
                        linhas.append({"sq_candidato": str(cand["sqcand"]), "votos": int(cand.get("vap") or 0)})
    return pd.DataFrame(linhas).drop_duplicates("sq_candidato")


def candidatos() -> pd.DataFrame:
    c = pd.read_parquet(CANDIDATOS / "candidaturas.parquet").query("ano == 2026")
    c["sq_candidato"] = c["sq_candidato"].astype(str)
    c["cargo"] = c["ds_cargo"].replace(CARGOS)
    return c[["sq_candidato", "uf", "cargo", "sg_partido", "ds_genero", "ds_cor_raca", "eleito"]]


# --- tabelas da página -----------------------------------------------------------------
def resumo(con, cand: pd.DataFrame) -> pd.DataFrame:
    total = con.sql("select categoria, sum(valor) as valor from receitas group by 1").df().set_index("categoria")["valor"]
    pf = con.sql("""
        select doador, sum(valor) as valor from receitas
        where categoria = 'Pessoas físicas' and length(doador) = 11 and doador not in ('-1', '-4')
        group by 1 order by 2 desc
    """).df()
    top = pf.head(max(1, int(np.ceil(len(pf) * 0.01))))
    prestadores = pd.read_parquet(BRUTOS / "prestadores.parquet")
    estimavel = con.sql("select sum(valor) from receitas where natureza = 'ESTIMÁVEL'").fetchall()[0][0]
    linha = {
        "receitas": total.sum(),
        **{f"receitas_{c}": total.get(c, 0.0) for c in CATEGORIAS},
        "parte_fundos_publicos": (total.get("Fundo eleitoral", 0) + total.get("Fundo partidário", 0)) / total.sum(),
        "parte_estimavel": estimavel / total.sum(),
        "despesas_contratadas": con.sql("select sum(valor) from despesas").fetchall()[0][0],
        "candidatos_com_contas": int(prestadores["tem_final"].sum()),
        "candidatos_so_parcial": int((~prestadores["tem_final"]).sum()),
        "candidatos_foram_a_voto": len(cand),
        "doadores_pessoas_fisicas": len(pf),
        "parte_1pct_doadores": top["valor"].sum() / pf["valor"].sum() if len(pf) else np.nan,
        "dt_geracao": con.sql("select max(dt_geracao) from receitas").fetchall()[0][0],
    }
    return pd.DataFrame([linha])


def por_cargo(con, cand: pd.DataFrame) -> pd.DataFrame:
    """Receitas por cargo e categoria, e o valor mediano por candidato (só quem foi a voto)."""
    r = con.sql("select sq_candidato, categoria, sum(valor) as valor from receitas group by all").df()
    r = r.merge(cand[["sq_candidato", "cargo"]], on="sq_candidato")
    tabela = r.pivot_table(index="cargo", columns="categoria", values="valor", aggfunc="sum", fill_value=0)
    tabela = tabela.reindex(columns=CATEGORIAS, fill_value=0)
    por_candidato = r.groupby(["cargo", "sq_candidato"])["valor"].sum().reset_index()
    todos = cand[["sq_candidato", "cargo"]].merge(por_candidato, on=["sq_candidato", "cargo"], how="left").fillna(
        {"valor": 0})
    tabela["candidatos"] = todos.groupby("cargo").size()
    tabela["mediana_por_candidato"] = todos.groupby("cargo")["valor"].median()
    proprios = r[r["categoria"] == "Recursos próprios"].groupby("sq_candidato")["valor"].sum()
    todos["proprios"] = todos["sq_candidato"].map(proprios).fillna(0)
    todos["mais_da_metade_proprio"] = todos["proprios"] > todos["valor"] / 2
    tabela["parte_candidatos_mais_da_metade_proprio"] = todos[todos["valor"] > 0].groupby("cargo")[
        "mais_da_metade_proprio"].mean()
    return tabela.reindex(ORDEM_CARGOS).reset_index()


def fundo_por_grupo(con, cand: pd.DataFrame) -> pd.DataFrame:
    """Fundo eleitoral recebido do partido, por partido: total e quanto foi para candidaturas de mulheres
    e de pessoas pretas e pardas, ao lado da parte delas entre quem foi a voto."""
    f = con.sql("""
        select sq_candidato, sum(valor) as fundo from receitas
        where categoria = 'Fundo eleitoral' and origem = 'Recursos de partido político' group by 1
    """).df()
    d = cand.merge(f, on="sq_candidato", how="left").fillna({"fundo": 0})
    d["mulher"] = d["ds_genero"] == "Feminino"
    d["negra"] = d["ds_cor_raca"].isin(["Preta", "Parda"])
    linhas = []
    for partido, g in [*d.groupby("sg_partido"), ("Todos os partidos", d)]:
        total = g["fundo"].sum()
        if total <= 0:
            continue
        linhas.append({"sg_partido": partido, "candidatos": len(g), "fundo": total,
                       "parte_candidatas_mulheres": g["mulher"].mean(),
                       "parte_fundo_mulheres": g.loc[g["mulher"], "fundo"].sum() / total,
                       "parte_candidatos_negros": g["negra"].mean(),
                       "parte_fundo_negros": g.loc[g["negra"], "fundo"].sum() / total})
    return pd.DataFrame(linhas)


def despesas_por_tipo(con) -> pd.DataFrame:
    d = con.sql("select categoria, sum(valor) as valor, count(*) as lancamentos from despesas group by 1").df()
    d = d.sort_values("valor", ascending=False).reset_index(drop=True)
    principais = d.head(10)
    resto = d.iloc[10:]
    if len(resto):
        principais = pd.concat([principais, pd.DataFrame([{"categoria": "Outras despesas", "valor": resto["valor"].sum(),
                                                           "lancamentos": resto["lancamentos"].sum()}])])
    principais["parte"] = principais["valor"] / d["valor"].sum()
    return principais.reset_index(drop=True)


def custo_por_voto(con, cand: pd.DataFrame, votos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Despesas contratadas ÷ votos do 1º turno, para eleitos e não eleitos de cada cargo; e, para Deputado
    Federal, a chance de ser eleito em cada faixa de gasto (décimos)."""
    gasto = con.sql("select sq_candidato, sum(valor) as gasto from despesas group by 1").df()
    d = cand.merge(votos, on="sq_candidato").merge(gasto, on="sq_candidato", how="left").fillna({"gasto": 0})
    d = d[(d["votos"] > 0) & (d["cargo"] != "Presidente")]
    d["custo_voto"] = d["gasto"] / d["votos"]
    grupos = (d.assign(grupo=np.where(d["eleito"], "Eleitos", "Não eleitos"))
              .groupby(["cargo", "grupo"])
              .agg(candidatos=("sq_candidato", "size"), mediana_custo_voto=("custo_voto", "median"),
                   mediana_gasto=("gasto", "median"), mediana_votos=("votos", "median")).reset_index())
    dep = d[d["cargo"] == "Deputado Federal"].copy()
    dep["faixa"] = pd.qcut(dep["gasto"].rank(method="first"), 10, labels=range(1, 11)).astype(int)
    faixas = dep.groupby("faixa").agg(gasto_min=("gasto", "min"), gasto_max=("gasto", "max"),
                                      mediana_gasto=("gasto", "median"), parte_eleitos=("eleito", "mean"),
                                      eleitos=("eleito", "sum"), candidatos=("eleito", "size")).reset_index()
    return grupos, faixas


def gravar(tabela: pd.DataFrame, nome: str) -> None:
    caminho = SAIDA / f"{nome}.parquet"
    tabela.to_parquet(caminho, index=False)
    print(f"  {caminho.relative_to(RAIZ)}: {len(tabela)} linhas")


def main() -> int:
    baixar()
    con = duckdb.connect()
    carregar(con)
    cand = candidatos()
    votos = votos_1t()
    r = resumo(con, cand)
    gravar(r, "dinheiro_resumo")
    gravar(por_cargo(con, cand), "dinheiro_cargo")
    gravar(fundo_por_grupo(con, cand), "dinheiro_fundo_grupos")
    gravar(despesas_por_tipo(con), "dinheiro_despesas")
    grupos, faixas = custo_por_voto(con, cand, votos)
    gravar(grupos, "dinheiro_custo_voto")
    gravar(faixas, "dinheiro_faixas_gasto")
    print(r.T.to_string(header=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
