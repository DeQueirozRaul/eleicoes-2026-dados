-- Todo município brasileiro de 2026 deve existir no cadastro (com código IBGE).
select t.uf, t.cd_municipio_tse
from transicao_turnos t
left join municipios m using (uf, cd_municipio_tse)
where t.ano = 2026 and t.uf <> 'ZZ' and m.cd_municipio_ibge is null;
