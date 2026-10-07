-- Como o eleitorado de cada município se dividiu em cada turno: uma linha por
-- opção (cada candidato, brancos e nulos juntos, e abstenção), em número de
-- eleitores. É a base da estimativa de "para onde foi o eleitor" entre eleições.
create or replace table composicao_eleitorado as
select ano, turno, uf, cd_municipio_tse, nr_candidato::varchar as opcao, qt_votos as qt
from votos_presidente
union all
select ano, turno, uf, cd_municipio_tse, 'BRANCO_NULO', qt_brancos + qt_nulos
from comparecimento_presidente
union all
select ano, turno, uf, cd_municipio_tse, 'ABSTENCAO', qt_abstencoes
from comparecimento_presidente;
