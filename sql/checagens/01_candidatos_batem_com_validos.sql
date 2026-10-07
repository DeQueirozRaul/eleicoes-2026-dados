-- A soma dos votos dos candidatos deve ser igual aos votos válidos do município.
select v.ano, v.turno, v.uf, v.cd_municipio_tse, sum(v.qt_votos) as soma_candidatos, c.qt_validos
from votos_presidente v
join comparecimento_presidente c using (ano, turno, uf, cd_municipio_tse)
group by all
having sum(v.qt_votos) <> c.qt_validos;
