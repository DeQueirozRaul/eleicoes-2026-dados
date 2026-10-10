-- Votos para Presidente por eleição, turno, município e candidato (2002 a 2026).
--   2002–2022: "Votação nominal por município e zona" do TSE, somando as zonas.
--   2026: coletor dos resultados ao vivo (o retrato mais recente de cada município).
-- A UF "ZZ" é o exterior; em 2010 o voto em trânsito aparece como UF "VT".
create or replace table votos_presidente as
with historico as (
    select
        ANO_ELEICAO::int                as ano,
        NR_TURNO::int                   as turno,
        SG_UF                           as uf,
        lpad(CD_MUNICIPIO, 5, '0')      as cd_municipio_tse,
        NR_CANDIDATO::int               as nr_candidato,
        NM_URNA_CANDIDATO               as nm_urna,
        SG_PARTIDO                      as sg_partido,
        sum(coalesce(QT_VOTOS_NOMINAIS_VALIDOS, QT_VOTOS_NOMINAIS)::bigint) as qt_votos
    from read_csv('dados/brutos/votacao_candidato_munzona_*_BR.csv',
                  delim = ';', encoding = 'latin-1', all_varchar = true, union_by_name = true)
    where CD_CARGO = '1'
    group by all
),
ao_vivo as (
    select
        2026                            as ano,
        if(filename like '%e6258_c1%', 2, 1) as turno,
        upper(uf)                       as uf,
        cd_municipio_tse,
        nr_candidato::int               as nr_candidato,
        nm_urna,
        sg_partido,
        qt_votos
    from read_parquet('dados/ao_vivo/e625*_c1/*/candidatos.parquet', filename = true)
    where cd_municipio_tse <> ''
    qualify row_number() over (
        partition by turno, uf, cd_municipio_tse, nr_candidato order by dt_coleta desc
    ) = 1
)
select * from historico
union all by name
select * from ao_vivo;
