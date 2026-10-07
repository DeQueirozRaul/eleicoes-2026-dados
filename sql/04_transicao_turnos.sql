-- Base do modelo de 2º turno: uma linha por eleição e município, com o voto
-- no 1º turno (nos dois finalistas e nos eliminados) e, quando já houve, no 2º.
--
-- Finalista A = 1º colocado no total nacional do 1º turno; B = 2º colocado.

create or replace table finalistas as
with nacional as (
    select ano, nr_candidato, any_value(nm_urna) as nm_urna,
           any_value(sg_partido) as sg_partido, sum(qt_votos) as qt_votos
    from votos_presidente
    where turno = 1
    group by all
)
select ano, nr_candidato, nm_urna, sg_partido, qt_votos,
       row_number() over (partition by ano order by qt_votos desc) as posicao_1t,
       if(posicao_1t = 1, 'A', 'B') as finalista
from nacional
qualify posicao_1t <= 2;

create or replace table transicao_turnos as
with votos as (
    select v.ano, v.turno, v.uf, v.cd_municipio_tse,
           sum(v.qt_votos) filter (where f.finalista = 'A') as qt_a,
           sum(v.qt_votos) filter (where f.finalista = 'B') as qt_b,
           sum(v.qt_votos) filter (where f.finalista is null) as qt_eliminados,
           sum(v.qt_votos) as qt_validos
    from votos_presidente v
    left join finalistas f using (ano, nr_candidato)
    group by all
),
t1 as (select * from votos where turno = 1),
t2 as (select * from votos where turno = 2),
c1 as (select * from comparecimento_presidente where turno = 1),
c2 as (select * from comparecimento_presidente where turno = 2)
select
    t1.ano, t1.uf, t1.cd_municipio_tse,
    coalesce(m.regiao, if(t1.uf = 'ZZ', 'Exterior', null)) as regiao,
    c1.qt_aptos,
    c1.qt_comparecimento                     as qt_comparecimento_1t,
    t1.qt_a                                  as qt_a_1t,
    t1.qt_b                                  as qt_b_1t,
    coalesce(t1.qt_eliminados, 0)            as qt_eliminados_1t,
    t1.qt_validos                            as qt_validos_1t,
    c1.qt_brancos + c1.qt_nulos              as qt_brancos_nulos_1t,
    c2.qt_comparecimento                     as qt_comparecimento_2t,
    t2.qt_a                                  as qt_a_2t,
    t2.qt_b                                  as qt_b_2t,
    t2.qt_validos                            as qt_validos_2t
from t1
left join t2 using (ano, uf, cd_municipio_tse)
left join c1 using (ano, uf, cd_municipio_tse)
left join c2 using (ano, uf, cd_municipio_tse)
left join municipios m using (uf, cd_municipio_tse);
