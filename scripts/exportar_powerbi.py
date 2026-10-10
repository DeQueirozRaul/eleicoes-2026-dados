"""Exporta um modelo estrela pronto para montar o painel no Power BI.

Grava em dados/exportar/powerbi/ (CSV com ";" e UTF-8, só números inteiros e
texto, para o Power BI não confundir vírgula e ponto decimal; as porcentagens
são calculadas no Power BI, com medidas DAX). O passo a passo do painel está em
docs/powerbi.md.

    python scripts/exportar_powerbi.py

Tabelas:
    dim_eleicao        uma linha por eleição e turno (2002 a 2026)
    dim_uf             estados e região
    dim_municipio      municípios, com códigos TSE e IBGE
    dim_candidato      candidatos a Presidente de cada eleição
    fato_votos         votos para Presidente por eleição, turno, município e candidato
    fato_comparecimento  aptos, comparecimento, abstenção, brancos, nulos e válidos
    fato_candidaturas  candidaturas de 2018, 2022 e 2026 (todos os cargos), com perfil,
                       resultado e patrimônio declarado (se scripts/site_candidatos.py já rodou)
    fato_eleitorado    eleitorado de 2026 por UF, gênero, faixa etária e escolaridade
                       (se scripts/site_eleitorado.py já rodou)
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "dados" / "exportar" / "powerbi"

DATAS = {
    2002: ("2002-10-06", "2002-10-27"), 2006: ("2006-10-01", "2006-10-29"),
    2010: ("2010-10-03", "2010-10-31"), 2014: ("2014-10-05", "2014-10-26"),
    2018: ("2018-10-07", "2018-10-28"), 2022: ("2022-10-02", "2022-10-30"),
    2026: ("2026-10-04", "2026-10-25"),
}
UFS = {
    "AC": ("Acre", "Norte"), "AL": ("Alagoas", "Nordeste"), "AM": ("Amazonas", "Norte"),
    "AP": ("Amapá", "Norte"), "BA": ("Bahia", "Nordeste"), "CE": ("Ceará", "Nordeste"),
    "DF": ("Distrito Federal", "Centro-Oeste"), "ES": ("Espírito Santo", "Sudeste"),
    "GO": ("Goiás", "Centro-Oeste"), "MA": ("Maranhão", "Nordeste"), "MG": ("Minas Gerais", "Sudeste"),
    "MS": ("Mato Grosso do Sul", "Centro-Oeste"), "MT": ("Mato Grosso", "Centro-Oeste"),
    "PA": ("Pará", "Norte"), "PB": ("Paraíba", "Nordeste"), "PE": ("Pernambuco", "Nordeste"),
    "PI": ("Piauí", "Nordeste"), "PR": ("Paraná", "Sul"), "RJ": ("Rio de Janeiro", "Sudeste"),
    "RN": ("Rio Grande do Norte", "Nordeste"), "RO": ("Rondônia", "Norte"), "RR": ("Roraima", "Norte"),
    "RS": ("Rio Grande do Sul", "Sul"), "SC": ("Santa Catarina", "Sul"), "SE": ("Sergipe", "Nordeste"),
    "SP": ("São Paulo", "Sudeste"), "TO": ("Tocantins", "Norte"), "ZZ": ("Exterior", "Exterior"),
    # em 2010 o TSE registrou o voto em trânsito (nas capitais) como se fosse uma UF à parte
    "VT": ("Voto em trânsito (2010)", "Voto em trânsito"),
    "BR": ("Brasil (candidatura a Presidente)", "Nacional"),
}


def salvar(tabela: pd.DataFrame, nome: str) -> None:
    caminho = DESTINO / f"{nome}.csv"
    tabela.to_csv(caminho, sep=";", index=False, encoding="utf-8-sig")
    linhas = f"{len(tabela):,}".replace(",", ".")
    tamanho = f"{caminho.stat().st_size / 2**20:.1f}".replace(".", ",")
    print(f"  {nome}.csv: {linhas} linhas, {tamanho} MB")


def dimensoes(con: duckdb.DuckDBPyConnection) -> None:
    salvar(pd.DataFrame([
        {"id_eleicao": ano * 10 + turno, "ano": ano, "turno": turno, "data": DATAS[ano][turno - 1],
         "eleicao": f"{ano} - {turno}º turno"}
        for ano in DATAS for turno in (1, 2)
    ]), "dim_eleicao")
    salvar(pd.DataFrame([{"uf": uf, "nome_uf": nome, "regiao": regiao} for uf, (nome, regiao) in UFS.items()]),
           "dim_uf")
    # o cadastro de 2026 não tem municípios que só existiram em eleições antigas
    # (sobretudo cidades do exterior); os nomes deles vêm dos próprios arquivos do TSE
    regioes = pd.DataFrame([{"uf": uf, "regiao_uf": regiao} for uf, (_, regiao) in UFS.items()])
    con.register("regioes", regioes)
    salvar(con.sql(f"""
        with antigos as (
            select SG_UF as uf, cast(CD_MUNICIPIO as integer) as cd_municipio_tse,
                   arg_max(NM_MUNICIPIO, cast(ANO_ELEICAO as integer)) as nm_municipio
            from read_csv(['{(RAIZ / "dados" / "brutos").as_posix()}/votacao_candidato_munzona_*_BR.csv',
                           '{(RAIZ / "dados" / "brutos").as_posix()}/detalhe_votacao_munzona_*_BR.csv'],
                          encoding = 'latin-1', delim = ';', union_by_name = true, all_varchar = true)
            group by all
        ),
        todos as (
            select cast(cd_municipio_tse as integer) as cd_municipio_tse,
                   try_cast(cd_municipio_ibge as integer) as cd_municipio_ibge, nm_municipio, uf, regiao, capital
            from municipios
            union all
            select a.cd_municipio_tse, null, a.nm_municipio, a.uf, r.regiao_uf, false
            from antigos a join regioes r using (uf)
            where a.cd_municipio_tse not in (select cast(cd_municipio_tse as integer) from municipios)
        )
        select *, nm_municipio || ', ' || uf || ', Brasil' as local_para_mapa   -- ajuda o mapa do Power BI
        from todos order by uf, nm_municipio
    """).df(), "dim_municipio")
    salvar(con.sql("""
        with primeiro_turno as (
            select ano, nr_candidato, nm_urna, sg_partido, sum(qt_votos) as qt_votos
            from votos_presidente where turno = 1 group by ano, nr_candidato, nm_urna, sg_partido
        )
        select p.ano * 100 + p.nr_candidato as id_candidato, p.ano, p.nr_candidato, p.nm_urna, p.sg_partido,
               f.finalista is not null as foi_ao_2o_turno,
               rank() over (partition by p.ano order by p.qt_votos desc) as posicao_1o_turno
        from primeiro_turno p
        left join finalistas f using (ano, nr_candidato)
        order by p.ano, posicao_1o_turno
    """).df(), "dim_candidato")


def fatos(con: duckdb.DuckDBPyConnection) -> None:
    salvar(con.sql("""
        select ano * 10 + turno as id_eleicao, ano * 100 + nr_candidato as id_candidato,
               cast(cd_municipio_tse as integer) as cd_municipio_tse, qt_votos::bigint as qt_votos
        from votos_presidente order by ano, turno, cd_municipio_tse
    """).df(), "fato_votos")
    salvar(con.sql("""
        select ano * 10 + turno as id_eleicao, cast(cd_municipio_tse as integer) as cd_municipio_tse,
               qt_aptos::bigint as qt_aptos, qt_comparecimento::bigint as qt_comparecimento,
               qt_abstencoes::bigint as qt_abstencoes, qt_brancos::bigint as qt_brancos,
               qt_nulos::bigint as qt_nulos, qt_validos::bigint as qt_validos
        from comparecimento_presidente order by ano, turno, cd_municipio_tse
    """).df(), "fato_comparecimento")


def candidaturas() -> None:
    origem = RAIZ / "dados" / "brutos" / "candidatos" / "candidaturas.parquet"
    if not origem.exists():
        print("  fato_candidaturas: pulado (rode antes scripts/site_candidatos.py)")
        return
    tabela = pd.read_parquet(origem)
    # as candidaturas pertencem à eleição do ano; ligamos ao 1º turno em dim_eleicao
    tabela.insert(0, "id_eleicao", tabela["ano"] * 10 + 1)
    salvar(tabela, "fato_candidaturas")


def eleitorado() -> None:
    origem = RAIZ / "dados" / "brutos" / "eleitorado" / "eleitorado_2026_uf.parquet"
    if not origem.exists():
        print("  fato_eleitorado: pulado (rode antes scripts/site_eleitorado.py)")
        return
    salvar(pd.read_parquet(origem), "fato_eleitorado")


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(RAIZ / "dados" / "eleicoes.duckdb"), read_only=True)
    print(f"Modelo para o Power BI em {DESTINO.relative_to(RAIZ)}:")
    dimensoes(con)
    fatos(con)
    con.close()
    candidaturas()
    eleitorado()


if __name__ == "__main__":
    main()
