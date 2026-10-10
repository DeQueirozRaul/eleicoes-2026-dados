"""Dados da página "Eleitorado" do site: baixa os arquivos do TSE e do IBGE,
calcula e grava tabelas pequenas em app/dados/eleitorado_*.parquet.

Fontes:
- Perfil do eleitorado (TSE), um zip por eleição geral (2010, 2014, 2018, 2022
  e 2026), com o eleitorado por município, zona, gênero, faixa etária e grau de
  instrução no fechamento do cadastro para aquela eleição:
  https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_eleitorado/perfil_eleitorado_<ANO>.zip
  (catálogo: https://dadosabertos.tse.jus.br/dataset/eleitorado-2026)
- Perfil do comparecimento e da abstenção (TSE), por turno, gênero, idade e
  instrução: https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_comparecimento_abstencao/perfil_comparecimento_abstencao_<ANO>.zip
  (2022; o de 2026 ainda não tinha sido publicado em 10/10/2026 e entra
  sozinho quando o script for rodado depois da publicação).
- Transferência temporária do eleitorado de 2026 (TSE), para a conferência por UF:
  https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_eleitor_tte/transferencia_temporaria_2026.zip
- População dos municípios (IBGE, API do SIDRA):
  estimativa mais recente (2026), tabela 6579, variável 9324:
  https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/last%201
  e Censo 2022, tabela 4709, variável 93:
  https://apisidra.ibge.gov.br/values/t/4709/n6/all/v/93/p/2022
- Pessoas com 16, 17 e 100 anos ou mais no Censo 2022 (IBGE, SIDRA, tabela 9514):
  https://apisidra.ibge.gov.br/values/t/9514/n1/all/v/93/p/2022/c2/6794/c287/6573,6574,6653/c286/113635
- Banco local dados/eleicoes.duckdb: cadastro de municípios (código TSE <-> IBGE)
  e eleitores aptos e abstenção do resultado de Presidente, para conferência.

Saídas: app/dados/eleitorado_*.parquet (site; eleitorado_brasil_perfil serve a
outras páginas) e dados/brutos/eleitorado/eleitorado_2026_uf.parquet (eleitorado
de 2026 por UF, gênero, faixa etária e instrução, para o Power BI; fora do git).

Os CSVs do TSE são grandes (o de 2026 tem 2,2 GB descompactado). De cada zip só
são lidos os CSVs necessários (HTTP Range, sem baixar o zip inteiro), no máximo
3 ao mesmo tempo (o TSE recusa com 403 quando há muitas conexões), e cada CSV é
logo agregado com DuckDB (só as colunas usadas) num parquet pequeno em
dados/brutos/eleitorado/. O CSV é apagado depois; rodar de novo reaproveita os
agregados e não baixa nada.

    python scripts/site_eleitorado.py            # usa o que já foi baixado
    python scripts/site_eleitorado.py --forcar   # baixa e agrega tudo de novo
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.eleitorado import (  # noqa: E402
    mais_eleitores_que_habitantes,
    tabela_escolaridade,
    tabela_faixas,
    tabela_genero,
)
from eleicoes.tse_arquivos import CDN, ArquivoRemoto  # noqa: E402

BRUTOS = RAIZ / "dados" / "brutos" / "eleitorado"
BANCO = RAIZ / "dados" / "eleicoes.duckdb"
SAIDA = RAIZ / "app" / "dados"

ANOS_PERFIL = [2010, 2014, 2018, 2022, 2026]
ANOS_ABSTENCAO = [2022, 2026]
UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB",
       "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO", "ZZ"]
SIDRA = "https://apisidra.ibge.gov.br/values"
PARALELO = 3


def url_perfil(ano: int) -> str:
    return f"{CDN}/perfil_eleitorado/perfil_eleitorado_{ano}.zip"


def url_abstencao(ano: int) -> str:
    return f"{CDN}/perfil_comparecimento_abstencao/perfil_comparecimento_abstencao_{ano}.zip"


def url_transferencia(ano: int) -> str:
    """Eleitores com transferência temporária (voto em trânsito, presos provisórios,
    militares, mesários convocados etc.): votam em outra seção, às vezes em outra UF."""
    return f"{CDN}/perfil_eleitor_tte/transferencia_temporaria_{ano}.zip"


# --- download ----------------------------------------------------------------
def tentar(funcao, *args, tentativas: int = 6, espera: float = 10):
    """Chama funcao(*args) de novo quando o TSE recusa (403, 429, 5xx) ou a conexão cai."""
    for tentativa in range(1, tentativas + 1):
        try:
            return funcao(*args)
        except (requests.RequestException, zipfile.BadZipFile, OSError) as erro:
            if tentativa == tentativas:
                raise
            print(f"  tentativa {tentativa} falhou ({erro.__class__.__name__}: {str(erro)[:80]}); "
                  f"nova tentativa em {espera * tentativa:.0f} s", flush=True)
            time.sleep(espera * tentativa)


def escolher_membros(nomes: list[str]) -> list[str]:
    """CSVs a ler de um zip do TSE: os de cada UF (27 + exterior) quando estão todos
    lá; senão o nacional (_BRASIL) ou o único CSV do ano (ex.: perfil_eleitorado_2018.csv).

    O zip de comparecimento de 2022, por exemplo, não traz DF nem exterior em
    arquivos separados: só o _BRASIL tem tudo."""
    csvs = [n for n in nomes if n.lower().endswith(".csv")]
    por_uf = {}
    for n in csvs:
        achado = re.search(r"_([A-Z]{2})\.csv$", n)
        if achado:
            por_uf[achado.group(1)] = n
    if set(UFS) <= set(por_uf):
        return [por_uf[uf] for uf in UFS]
    nacional = [n for n in csvs if "_BRASIL" in n.upper()] or [n for n in csvs if re.search(r"_\d{4}\.csv$", n)]
    if len(nacional) == 1:
        return nacional
    raise RuntimeError(f"não encontrei os CSVs esperados no zip: {nomes}")


def membros_csv(url: str) -> list[str]:
    with zipfile.ZipFile(ArquivoRemoto(url)) as zf:
        return escolher_membros(zf.namelist())


def extrair(url: str, membro: str, destino: Path) -> Path:
    """Extrai `membro` do zip remoto para `destino` (grava em .parcial e renomeia no fim)."""
    parcial = destino.with_suffix(".parcial")
    remoto = io.BufferedReader(ArquivoRemoto(url), buffer_size=1024 * 1024)
    with zipfile.ZipFile(remoto) as zf, zf.open(membro) as origem, open(parcial, "wb") as saida:
        while bloco := origem.read(4 * 1024 * 1024):
            saida.write(bloco)
    parcial.replace(destino)
    return destino


def colunas_do_csv(caminho: Path) -> list[str]:
    with open(caminho, encoding="latin-1") as f:
        return [c.strip('"') for c in f.readline().strip().split(";")]


def sql_agregar_perfil(csv: Path) -> str:
    """Eleitorado por município, gênero, faixa etária e instrução (soma das zonas)."""
    colunas = colunas_do_csv(csv)
    ano = "AA_ELEICAO" if "AA_ELEICAO" in colunas else "ANO_ELEICAO"
    qt = "QT_ELEITORES" if "QT_ELEITORES" in colunas else "QT_ELEITORES_PERFIL"
    return f"""
        select {ano}::int as ano, SG_UF as uf, CD_MUNICIPIO as cd_municipio, NM_MUNICIPIO as nm_municipio,
               CD_GENERO::int as cd_genero, CD_FAIXA_ETARIA::int as cd_faixa, trim(DS_FAIXA_ETARIA) as ds_faixa,
               CD_GRAU_ESCOLARIDADE::int as cd_escolaridade,
               sum({qt}::bigint) as qt_eleitores, min(DT_GERACAO) as dt_geracao
        from read_csv('{csv.as_posix()}', delim=';', encoding='latin-1', all_varchar=true, header=true)
        group by all
    """


def sql_agregar_abstencao(csv: Path) -> str:
    """Aptos, comparecimento e abstenção por turno, UF, gênero, faixa etária e instrução."""
    return f"""
        select ANO_ELEICAO::int as ano, NR_TURNO::int as turno, SG_UF as uf,
               CD_GENERO::int as cd_genero, CD_FAIXA_ETARIA::int as cd_faixa, trim(DS_FAIXA_ETARIA) as ds_faixa,
               CD_GRAU_ESCOLARIDADE::int as cd_escolaridade,
               sum(QT_APTOS::bigint) as qt_aptos, sum(QT_COMPARECIMENTO::bigint) as qt_comparecimento,
               sum(QT_ABSTENCAO::bigint) as qt_abstencao, min(DT_GERACAO) as dt_geracao
        from read_csv('{csv.as_posix()}', delim=';', encoding='latin-1', all_varchar=true, header=true)
        group by all
    """


def sql_agregar_transferencia(csv: Path) -> str:
    """Eleitores com transferência temporária por turno e UF de origem e de destino."""
    return f"""
        select AA_ELEICAO::int as ano, NR_TURNO::int as turno, TP_TTE as tipo,
               SG_UF_ORIGEM as uf_origem, SG_UF_DESTINO as uf_destino,
               sum(QT_ELEITOR::bigint) as qt_eleitores, min(DT_GERACAO) as dt_geracao
        from read_csv('{csv.as_posix()}', delim=';', encoding='latin-1', all_varchar=true, header=true)
        group by all
    """


def baixar_e_agregar(url: str, membro: str, pasta: Path, sql, forcar: bool) -> Path:
    """Extrai um CSV, agrega com DuckDB num parquet em `pasta` e apaga o CSV."""
    destino = pasta / Path(membro).name.replace(".csv", ".parquet")
    if destino.exists() and not forcar:
        return destino
    pasta.mkdir(parents=True, exist_ok=True)
    csv = pasta / Path(membro).name
    inicio = time.time()
    tentar(extrair, url, membro, csv)
    baixado = time.time() - inicio
    with duckdb.connect() as con:
        con.execute("set threads = 2")
        con.execute(f"copy ({sql(csv)}) to '{destino.as_posix()}' (format parquet)")
    tamanho = csv.stat().st_size / 1e6
    csv.unlink()
    print(f"  {membro}: {tamanho:,.0f} MB lidos ({baixado:.0f} s para baixar, "
          f"{time.time() - inicio - baixado:.0f} s para agregar)", flush=True)
    return destino


def publicado(url: str) -> bool:
    """True se o arquivo existe no TSE (404 = ainda não publicado)."""
    def consultar():
        resposta = requests.head(url, timeout=60)
        if resposta.status_code != 404:
            resposta.raise_for_status()
        return resposta.status_code != 404
    return tentar(consultar)


def baixar_conjunto(url: str, pasta: Path, sql, forcar: bool) -> list[Path] | None:
    """Todos os CSVs necessários de um zip, 3 por vez. None se o zip ainda não existe."""
    completo = pasta / "completo.txt"  # gravado só quando todos os CSVs do zip foram agregados
    if completo.exists() and not forcar:
        return sorted(pasta.glob("*.parquet"))
    if not publicado(url):
        print(f"  ainda não publicado: {url}")
        return None
    membros = tentar(membros_csv, url)
    with ThreadPoolExecutor(max_workers=PARALELO) as executor:
        tarefas = [executor.submit(baixar_e_agregar, url, m, pasta, sql, forcar) for m in membros]
        arquivos = [t.result() for t in tarefas]
    completo.write_text(f"{url}\n" + "\n".join(membros) + "\n", encoding="utf-8")
    return arquivos


def baixar_tudo(forcar: bool) -> None:
    for ano in ANOS_PERFIL:
        print(f"Perfil do eleitorado {ano}", flush=True)
        baixar_conjunto(url_perfil(ano), BRUTOS / f"perfil_{ano}", sql_agregar_perfil, forcar)
    for ano in ANOS_ABSTENCAO:
        print(f"Comparecimento e abstenção {ano}", flush=True)
        baixar_conjunto(url_abstencao(ano), BRUTOS / f"abstencao_{ano}", sql_agregar_abstencao, forcar)
    print("Transferência temporária 2026", flush=True)
    baixar_conjunto(url_transferencia(2026), BRUTOS / "transferencia_2026", sql_agregar_transferencia, forcar)
    print("População dos municípios e por idade (IBGE)", flush=True)
    populacao_ibge(forcar)
    idades_censo_2022(forcar)


def sidra(caminho: str) -> pd.DataFrame:
    """Consulta a API do SIDRA (IBGE). A 1ª linha da resposta é o cabeçalho."""
    def consultar():
        resposta = requests.get(f"{SIDRA}/{caminho}", timeout=180)
        resposta.raise_for_status()
        return resposta.json()
    linhas = tentar(consultar)
    return pd.DataFrame(linhas[1:])


def populacao_ibge(forcar: bool = False) -> pd.DataFrame:
    """População de cada município: estimativa mais recente (tabela 6579) e Censo 2022 (tabela 4709)."""
    cache = BRUTOS / "populacao_ibge.parquet"
    if cache.exists() and not forcar:
        return pd.read_parquet(cache)
    estimativa = sidra("t/6579/n6/all/v/9324/p/last%201")
    censo = sidra("t/4709/n6/all/v/93/p/2022")
    tabela = pd.DataFrame({
        "cd_municipio_ibge": estimativa["D1C"],
        # "Davinópolis - GO" ou "Brasília (DF)" -> só o nome
        "nm_ibge": estimativa["D1N"].str.replace(r"\s*(\([A-Z]{2}\)|- [A-Z]{2})$", "", regex=True),
        "populacao": pd.to_numeric(estimativa["V"], errors="coerce"),
        "ano_populacao": estimativa["D3C"].astype(int),
    }).merge(pd.DataFrame({
        "cd_municipio_ibge": censo["D1C"],
        "populacao_censo_2022": pd.to_numeric(censo["V"], errors="coerce"),
    }), on="cd_municipio_ibge", how="outer")
    BRUTOS.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(cache, index=False)
    print(f"  {len(tabela)} municípios; estimativa de {tabela['ano_populacao'].max():.0f}")
    return tabela



def idades_censo_2022(forcar: bool = False) -> pd.DataFrame:
    """Pessoas com 16 anos, 17 anos e 100 anos ou mais no Brasil, Censo 2022 (tabela 9514)."""
    cache = BRUTOS / "censo_2022_idades.parquet"
    if cache.exists() and not forcar:
        return pd.read_parquet(cache)
    bruto = sidra("t/9514/n1/all/v/93/p/2022/c2/6794/c287/6573,6574,6653/c286/113635")
    coluna_idade = next(c for c in bruto.columns if c.endswith("N") and bruto[c].str.contains("anos").all())
    tabela = pd.DataFrame({"categoria": bruto[coluna_idade],
                           "populacao_censo_2022": pd.to_numeric(bruto["V"]).astype("int64")})
    tabela.to_parquet(cache, index=False)
    return tabela

# --- cálculo -----------------------------------------------------------------
def conectar() -> duckdb.DuckDBPyConnection:
    """DuckDB em memória com os agregados baixados (visões) e as tabelas de apoio."""
    con = duckdb.connect()
    for ano in ANOS_PERFIL:
        con.execute(f"""
            create view perfil_{ano} as
            select ano, uf, lpad(cast(cast(cd_municipio as int) as varchar), 5, '0') as cd_municipio_tse,
                   nm_municipio, cd_genero, cd_faixa, cd_escolaridade, qt_eleitores, dt_geracao
            from read_parquet('{(BRUTOS / f"perfil_{ano}").as_posix()}/*.parquet')""")
    con.execute("create view perfil as " + " union all ".join(f"select * from perfil_{a}" for a in ANOS_PERFIL))
    anos = [a for a in ANOS_ABSTENCAO if (BRUTOS / f"abstencao_{a}" / "completo.txt").exists()]
    con.execute("create view abstencao as " + " union all ".join(
        f"select * from read_parquet('{(BRUTOS / f'abstencao_{a}').as_posix()}/*.parquet')" for a in anos))
    con.execute(f"create view transferencia as select * from "
                f"read_parquet('{(BRUTOS / 'transferencia_2026').as_posix()}/*.parquet')")
    codigos = con.sql("select distinct cd_faixa from perfil union select distinct cd_faixa from abstencao").df()
    con.register("faixas", tabela_faixas(codigos["cd_faixa"]))
    con.register("escolaridades", tabela_escolaridade())
    con.register("generos", tabela_genero())
    con.register("populacao", populacao_ibge())
    con.execute(f"attach '{BANCO.as_posix()}' as banco (read_only)")
    return con


def piramide(con) -> pd.DataFrame:
    """Eleitorado de 2026 por local (Brasil, UF, exterior), gênero e faixa de 5 anos."""
    return con.sql("""
        select coalesce(p.uf, 'BR') as local, f.ordem_piramide as ordem, f.faixa_piramide as faixa,
               g.genero, sum(p.qt_eleitores)::bigint as qt_eleitores
        from perfil_2026 p join faixas f using (cd_faixa) join generos g using (cd_genero)
        where f.ordem_piramide is not null and p.cd_genero in (2, 4)
        group by grouping sets ((p.uf, f.ordem_piramide, f.faixa_piramide, g.genero),
                                (f.ordem_piramide, f.faixa_piramide, g.genero))
        order by local, ordem, genero
    """).df()


def locais(con) -> pd.DataFrame:
    """Resumo por eleição e local: total, gênero e as idades de voto facultativo."""
    return con.sql("""
        select p.ano, coalesce(p.uf, 'BR') as local,
               sum(qt_eleitores)::bigint as qt_eleitores,
               coalesce(sum(qt_eleitores) filter (where cd_genero = 4), 0)::bigint as qt_mulheres,
               coalesce(sum(qt_eleitores) filter (where cd_genero = 2), 0)::bigint as qt_homens,
               coalesce(sum(qt_eleitores) filter (where f.idade = 16), 0)::bigint as qt_16,
               coalesce(sum(qt_eleitores) filter (where f.idade = 17), 0)::bigint as qt_17,
               coalesce(sum(qt_eleitores) filter (where f.grupo_facultativo = '16 e 17 anos'), 0)::bigint as qt_16_17,
               coalesce(sum(qt_eleitores) filter (where f.grupo_facultativo = '70 anos ou mais'), 0)::bigint as qt_70_mais,
               coalesce(sum(qt_eleitores) filter (where f.idade is null), 0)::bigint as qt_idade_invalida,
               min(strptime(dt_geracao, '%d/%m/%Y'))::date as dt_geracao
        from perfil p join faixas f using (cd_faixa)
        group by grouping sets ((p.ano, p.uf), (p.ano))
        order by ano, local
    """).df()


def conferencia(con) -> pd.DataFrame:
    """Eleitorado do arquivo de perfil x eleitores aptos do 1º turno (resultado de Presidente).

    Em 2026 a diferença por UF é explicada pela transferência temporária entre UFs
    (voto em trânsito, militares, presos provisórios etc.): o perfil conta o eleitor
    na UF do título, e o resultado, na UF onde ele vota."""
    return con.sql("""
        with perfil_uf as (
            select ano, coalesce(uf, 'BR') as local, sum(qt_eleitores)::bigint as qt_perfil
            from perfil group by grouping sets ((ano, uf), (ano))),
        aptos as (
            select ano, coalesce(uf, 'BR') as local, sum(qt_aptos)::bigint as qt_aptos_1t
            from banco.comparecimento_presidente where turno = 1 group by grouping sets ((ano, uf), (ano))),
        trans as (
            select uf_destino as local, sum(qt_eleitores) as entrada, 0 as saida
            from transferencia where turno = 1 and uf_origem <> uf_destino group by 1
            union all
            select uf_origem, 0, sum(qt_eleitores)
            from transferencia where turno = 1 and uf_origem <> uf_destino group by 1),
        trans_uf as (select local, sum(entrada)::bigint as tte_entrada, sum(saida)::bigint as tte_saida
                     from trans group by 1)
        select p.ano, p.local, p.qt_perfil, a.qt_aptos_1t,
               case when p.ano = 2026 then coalesce(t.tte_entrada, 0) end as tte_entrada,
               case when p.ano = 2026 then coalesce(t.tte_saida, 0) end as tte_saida
        from perfil_uf p left join aptos a using (ano, local)
        left join trans_uf t on p.ano = 2026 and t.local = p.local
        where p.ano = 2026 or p.local = 'BR'
        order by p.ano, p.local
    """).df()


def municipios(con) -> pd.DataFrame:
    """Eleitorado de 2026 e população (IBGE) de cada município do Brasil."""
    tabela = con.sql("""
        with eleitores as (
            select uf, cd_municipio_tse, sum(qt_eleitores)::bigint as qt_eleitores
            from perfil_2026 where uf <> 'ZZ' group by all)
        select e.uf, e.cd_municipio_tse, m.cd_municipio_ibge, coalesce(p.nm_ibge, m.nm_municipio) as nm_municipio,
               e.qt_eleitores,
               p.populacao::bigint as populacao, p.ano_populacao,
               p.populacao_censo_2022::bigint as populacao_censo_2022
        from eleitores e
        left join banco.municipios m using (uf, cd_municipio_tse)
        left join populacao p using (cd_municipio_ibge)
        order by e.uf, m.nm_municipio
    """).df()
    sem_codigo = tabela["cd_municipio_ibge"].isna().sum()
    sem_populacao = tabela["populacao"].isna().sum()
    if sem_codigo or sem_populacao:
        print(f"  atenção: {sem_codigo} municípios sem código IBGE e {sem_populacao} sem população:")
        print(tabela[tabela["populacao"].isna()].to_string())
    tabela["eleitores_por_100_hab"] = (100 * tabela["qt_eleitores"] / tabela["populacao"]).round(1)
    return tabela


def abstencao(con) -> pd.DataFrame:
    """Aptos, comparecimento e abstenção por idade, escolaridade e gênero (Brasil e exterior)."""
    somas = ("sum(qt_aptos)::bigint as qt_aptos, sum(qt_comparecimento)::bigint as qt_comparecimento, "
             "sum(qt_abstencao)::bigint as qt_abstencao")
    return con.sql("""
        with a as (select * from abstencao join faixas using (cd_faixa))
        select ano, turno, 'idade' as dimensao, f.ordem_abstencao as ordem, f.faixa_abstencao as categoria,
               bool_or(f.facultativo) as facultativo, {somas}
        from abstencao join faixas f using (cd_faixa)
        where f.ordem_abstencao is not null group by all
        union all
        select ano, turno, 'escolaridade', e.ordem, e.escolaridade, bool_or(e.facultativo), {somas}
        from a join escolaridades e using (cd_escolaridade) group by all
        union all
        select ano, turno, 'escolaridade_18_69', e.ordem, e.escolaridade, bool_or(e.facultativo), {somas}
        from a join escolaridades e using (cd_escolaridade) where a.idade between 18 and 69 group by all
        union all
        select ano, turno, 'genero', g.ordem, g.genero, false, {somas}
        from a join generos g using (cd_genero) group by all
        union all
        select ano, turno, 'total', 0, 'Total', false, {somas}
        from a group by all
        union all
        -- o mesmo total no resultado oficial de Presidente, para conferência
        select ano, turno, 'resultado_oficial', 0, 'Resultado oficial (Presidente)', false,
               sum(qt_aptos)::bigint, sum(qt_comparecimento)::bigint, sum(qt_abstencoes)::bigint
        from banco.comparecimento_presidente
        where ano in (select distinct ano from abstencao) group by all
        order by ano, turno, dimensao, ordem
    """.replace("{somas}", somas)).df()


def evolucao(con) -> pd.DataFrame:
    """Eleitorado do Brasil por gênero e por escolaridade em cada eleição geral."""
    return con.sql("""
        select ano, 'genero' as dimensao, g.ordem, g.genero as categoria, sum(qt_eleitores)::bigint as qt_eleitores
        from perfil join generos g using (cd_genero) group by all
        union all
        select ano, 'escolaridade', e.ordem, e.escolaridade, sum(qt_eleitores)::bigint
        from perfil join escolaridades e using (cd_escolaridade) group by all
        order by dimensao, ano, ordem
    """).df()


def brasil_perfil(con) -> pd.DataFrame:
    """Eleitorado de 2026 do Brasil (com o exterior) por gênero, faixa etária e grau de
    instrução, com os nomes do TSE. Para outras páginas do site."""
    return con.sql("""
        select dimensao, categoria, qt_eleitores from (
            select 'genero' as dimensao, g.ordem, g.genero_tse as categoria, sum(qt_eleitores)::bigint as qt_eleitores
            from perfil_2026 join generos g using (cd_genero) group by all
            union all
            select 'faixa_etaria', p.cd_faixa, f.ds_faixa, sum(qt_eleitores)::bigint
            from perfil_2026 p join (select cd_faixa, any_value(trim(ds_faixa)) as ds_faixa
                                      from read_parquet('""" + (BRUTOS / "perfil_2026").as_posix() + """/*.parquet')
                                      group by 1) f using (cd_faixa)
            group by all
            union all
            select 'grau_instrucao', e.ordem, e.escolaridade_tse, sum(qt_eleitores)::bigint
            from perfil_2026 join escolaridades e using (cd_escolaridade) group by all
        )
        order by case dimensao when 'genero' then 0 when 'faixa_etaria' then 1 else 2 end,
                 case when ordem < 0 then 99999 else ordem end
    """).df()


def censo_idades(con) -> pd.DataFrame:
    """Eleitores x pessoas no Censo 2022 com 16 anos, 17 anos e 100 anos ou mais."""
    con.register("censo", idades_censo_2022())
    return con.sql("""
        select c.categoria, c.populacao_censo_2022,
               sum(p.qt_eleitores) filter (where p.ano = 2022)::bigint as qt_eleitores_2022,
               sum(p.qt_eleitores) filter (where p.ano = 2026)::bigint as qt_eleitores_2026
        from censo c
        join (select 1600 as cd_faixa, '16 anos' as categoria union all select 1700, '17 anos'
              union all select 9999, '100 anos ou mais') f using (categoria)
        join perfil p using (cd_faixa)
        group by all order by min(f.cd_faixa)
    """).df()


def eleitorado_uf(con) -> pd.DataFrame:
    """Eleitorado de 2026 por UF (com o exterior, "ZZ"), gênero, faixa etária e grau de instrução,
    com os nomes do TSE. Alimenta o modelo do Power BI (fica fora do git, em dados/brutos/eleitorado/)."""
    return con.sql("""
        with faixa_tse as (
            select cd_faixa, any_value(trim(ds_faixa)) as ds_faixa
            from read_parquet('""" + (BRUTOS / "perfil_2026").as_posix() + """/*.parquet') group by 1)
        select p.uf, g.genero_tse as ds_genero, f.ds_faixa as ds_faixa_etaria,
               e.escolaridade_tse as ds_grau_instrucao, sum(p.qt_eleitores)::bigint as qt_eleitores
        from perfil_2026 p
        join generos g using (cd_genero) join faixa_tse f using (cd_faixa) join escolaridades e using (cd_escolaridade)
        group by p.uf, g.ordem, g.genero_tse, p.cd_faixa, f.ds_faixa, e.ordem, e.escolaridade_tse
        order by p.uf, g.ordem, case when p.cd_faixa < 0 then 99999 else p.cd_faixa end, e.ordem
    """).df()


def gravar(tabelas: dict[str, pd.DataFrame]) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    for nome, tabela in tabelas.items():
        destino = SAIDA / f"{nome}.parquet"
        tabela.to_parquet(destino, index=False, compression="zstd")
        print(f"  {destino.relative_to(RAIZ)}: {len(tabela):,} linhas, {destino.stat().st_size / 1e3:,.0f} kB")


def resumo(t: dict[str, pd.DataFrame]) -> None:
    """Imprime os principais números e as conferências."""
    loc = t["eleitorado_locais"]
    br = loc[loc["local"] == "BR"].set_index("ano")
    print("\nBrasil (com exterior), por eleição:")
    for ano, r in br.iterrows():
        print(f"  {ano}: {r.qt_eleitores:>12,} eleitores | 16 e 17 anos: {r.qt_16_17:>10,} "
              f"({r.qt_16_17 / r.qt_eleitores:.2%}) | 70+: {r.qt_70_mais:>11,} ({r.qt_70_mais / r.qt_eleitores:.2%}) "
              f"| mulheres {r.qt_mulheres / r.qt_eleitores:.2%} | arquivo de {r.dt_geracao}")
    conf = t["eleitorado_conferencia"]
    print("\nConferência com os aptos do 1º turno (Brasil):")
    for _, r in conf[conf["local"] == "BR"].iterrows():
        print(f"  {r.ano}: perfil {r.qt_perfil:,} | aptos {r.qt_aptos_1t:,} | diferença {r.qt_perfil - r.qt_aptos_1t:+,}")
    c26 = conf[(conf["ano"] == 2026) & (conf["local"] != "BR")].copy()
    c26["dif"] = c26["qt_perfil"] - c26["qt_aptos_1t"]
    c26["dif_ajustada"] = c26["qt_perfil"] + c26["tte_entrada"] - c26["tte_saida"] - c26["qt_aptos_1t"]
    print(f"  2026 por UF: maior diferença bruta {c26['dif'].abs().max():,} ({c26.loc[c26['dif'].abs().idxmax(), 'local']}); "
          f"depois da transferência temporária entre UFs, {int((c26['dif_ajustada'] == 0).sum())} de {len(c26)} "
          f"batem exatamente; maior diferença {c26['dif_ajustada'].abs().max():,}")
    mun = t["eleitorado_municipios"]
    acima = mais_eleitores_que_habitantes(mun)
    acima_censo = mais_eleitores_que_habitantes(mun, "populacao_censo_2022")
    print(f"\nMunicípios com mais eleitores do que habitantes: {len(acima)} (estimativa "
          f"{mun['ano_populacao'].max():.0f}); {len(acima_censo)} pelo Censo 2022; "
          f"{len(set(acima.cd_municipio_tse) & set(acima_censo.cd_municipio_tse))} nas duas")
    print(acima.head(10)[["uf", "nm_municipio", "qt_eleitores", "populacao", "eleitores_por_100_hab"]].to_string())
    print("\nEleitores x Censo 2022:")
    print(t["eleitorado_censo_idades"].to_string(index=False))
    ab = t["eleitorado_abstencao"]
    tot = ab[ab["dimensao"] == "total"]
    print("\nAbstenção (perfil de comparecimento):")
    oficial = ab[ab["dimensao"] == "resultado_oficial"].set_index(["ano", "turno"])
    for _, r in tot.iterrows():
        o = oficial.loc[(r.ano, r.turno)]
        print(f"  {r.ano} {r.turno}º turno: aptos {r.qt_aptos:,} | abstenção {r.qt_abstencao:,} "
              f"({r.qt_abstencao / r.qt_aptos:.2%}) | resultado oficial: aptos {o.qt_aptos:,}, "
              f"abstenção {o.qt_abstencao:,} (diferença {r.qt_abstencao - o.qt_abstencao:+,})")


def calcular() -> dict[str, pd.DataFrame]:
    con = conectar()
    tabelas = {
        "eleitorado_piramide": piramide(con),
        "eleitorado_locais": locais(con),
        "eleitorado_conferencia": conferencia(con),
        "eleitorado_municipios": municipios(con),
        # data da consulta: a página avisa até quando o arquivo de 2026 ainda não tinha saído
        "eleitorado_abstencao": abstencao(con).assign(dt_consulta=pd.Timestamp.today().normalize()),
        "eleitorado_evolucao": evolucao(con),
        "eleitorado_brasil_perfil": brasil_perfil(con),
        "eleitorado_censo_idades": censo_idades(con),
    }
    powerbi = eleitorado_uf(con)
    con.close()
    destino = BRUTOS / "eleitorado_2026_uf.parquet"
    powerbi.to_parquet(destino, index=False)
    print(f"  {destino.relative_to(RAIZ)}: {len(powerbi):,} linhas (Power BI; fora do git)")
    return tabelas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--forcar", action="store_true", help="baixa e agrega de novo mesmo se já existir")
    args = parser.parse_args()
    baixar_tudo(args.forcar)
    print("Calculando as tabelas do site", flush=True)
    tabelas = calcular()
    gravar(tabelas)
    resumo(tabelas)


if __name__ == "__main__":
    main()
