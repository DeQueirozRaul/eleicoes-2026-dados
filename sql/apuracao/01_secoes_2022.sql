-- Uma linha por seção eleitoral e turno de 2022 (Presidente), com os votos
-- dos dois finalistas (A = LULA, B = JAIR BOLSONARO, os mesmos nos dois turnos)
-- e o momento em que o boletim de urna entrou na totalização.
--
-- A totalização só começa às 17h (horário de Brasília), quando fecham as urnas
-- em todo o país; boletins que chegaram antes (exterior) entram às 17h.
create or replace table secoes_2022 as
with bu as (
    select *,
           if(filename like '%bweb_2022_1t%', 1, 2) as turno,
           greatest(strptime(DT_BU_RECEBIDO, '%d/%m/%Y %H:%M:%S'),
                    if(turno = 1, timestamp '2022-10-02 17:00:00', timestamp '2022-10-30 17:00:00'))
               as dt_totalizacao
    from read_parquet('dados/brutos/bweb_2022_*t/*.parquet', filename = true)
),
fin as (select nr_candidato::varchar as nr, finalista from finalistas where ano = 2022)
select
    turno,
    SG_UF                                   as uf,
    lpad(CD_MUNICIPIO, 5, '0')              as cd_municipio_tse,
    NR_ZONA::int                            as zona,
    NR_SECAO::int                           as secao,
    any_value(QT_APTOS::int)                as qt_aptos,
    any_value(QT_COMPARECIMENTO::int)       as qt_comparecimento,
    coalesce(sum(QT_VOTOS::int) filter (where fin.finalista = 'A'), 0) as qt_a,
    coalesce(sum(QT_VOTOS::int) filter (where fin.finalista = 'B'), 0) as qt_b,
    coalesce(sum(QT_VOTOS::int) filter (where NR_VOTAVEL not in ('95', '96')), 0) as qt_validos,
    max(dt_totalizacao)                     as dt_totalizacao
from bu
left join fin on fin.nr = bu.NR_VOTAVEL
group by all;
