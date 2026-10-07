-- Comparecimento deve ser igual a válidos + brancos + nulos + anulados em separado.
--
-- Diferença conhecida nos arquivos do TSE: em 2006 faltam 18.876 votos no país
-- (0,02%), nos dois turnos, sem coluna que explique. Por isso a checagem só acusa
-- diferenças acima de 1% do comparecimento do município (e de pelo menos 10 votos).
--
-- Aptos ≠ comparecimento + abstenções é esperado onde houve seção não instalada
-- (principalmente no exterior), por isso não entra aqui.
select *
from comparecimento_presidente
where abs(qt_comparecimento - (qt_validos + qt_brancos + qt_nulos + qt_anulados_separado))
      > greatest(10, 0.01 * qt_comparecimento);
