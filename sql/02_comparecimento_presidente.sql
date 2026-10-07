-- Eleitorado, comparecimento e votos brancos/nulos/válidos para Presidente,
-- por eleição, turno e município. `qt_anulados_separado` são votos anulados
-- depois de apurados em separado (ocorreu em 2002, 2010 e 2018).
create or replace table comparecimento_presidente as
with historico as (
    select
        ANO_ELEICAO::int                as ano,
        NR_TURNO::int                   as turno,
        SG_UF                           as uf,
        lpad(CD_MUNICIPIO, 5, '0')      as cd_municipio_tse,
        sum(QT_APTOS::bigint)           as qt_aptos,
        sum(QT_COMPARECIMENTO::bigint)  as qt_comparecimento,
        sum(QT_ABSTENCOES::bigint)      as qt_abstencoes,
        sum(QT_VOTOS_BRANCOS::bigint)   as qt_brancos,
        sum(QT_TOTAL_VOTOS_NULOS::bigint) as qt_nulos,
        sum(QT_TOTAL_VOTOS_VALIDOS::bigint) as qt_validos,
        sum(QT_VOTOS_ANULADOS_APU_SEP::bigint) as qt_anulados_separado
    from read_csv('dados/brutos/detalhe_votacao_munzona_*_BR.csv',
                  delim = ';', encoding = 'latin-1', all_varchar = true, union_by_name = true)
    where CD_CARGO = '1'
    group by all
),
ao_vivo as (
    select
        2026                            as ano,
        if(filename like '%/e6258_c1/%', 2, 1) as turno,
        upper(uf)                       as uf,
        cd_municipio_tse,
        qt_eleitores                    as qt_aptos,
        qt_comparecimento,
        qt_abstencao                    as qt_abstencoes,
        qt_votos_brancos                as qt_brancos,
        qt_votos_nulos                  as qt_nulos,
        qt_votos_validos                as qt_validos,
        qt_votos_anulados               as qt_anulados_separado
    from read_parquet('dados/ao_vivo/e625*_c1/*/resumo.parquet', filename = true)
    where cd_municipio_tse <> ''
    qualify row_number() over (
        partition by turno, uf, cd_municipio_tse order by dt_coleta desc
    ) = 1
)
select * from historico
union all by name
select * from ao_vivo;
