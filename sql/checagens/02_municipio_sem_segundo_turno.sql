-- Em eleição que já teve 2º turno, todo município do 1º turno deve ter 2º turno.
select ano, uf, cd_municipio_tse
from transicao_turnos
where ano in (select ano from votos_presidente where turno = 2)
  and qt_validos_2t is null;
