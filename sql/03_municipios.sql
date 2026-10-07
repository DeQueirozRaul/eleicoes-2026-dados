-- Cadastro de municípios (códigos TSE e IBGE), a partir da configuração da
-- eleição de 2026 publicada pelo TSE, com a região de cada UF.
create or replace table municipios as
select
    upper(uf)                   as uf,
    case
        when upper(uf) in ('AC', 'AM', 'AP', 'PA', 'RO', 'RR', 'TO') then 'Norte'
        when upper(uf) in ('AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE') then 'Nordeste'
        when upper(uf) in ('DF', 'GO', 'MS', 'MT') then 'Centro-Oeste'
        when upper(uf) in ('ES', 'MG', 'RJ', 'SP') then 'Sudeste'
        when upper(uf) in ('PR', 'RS', 'SC') then 'Sul'
        else 'Exterior'
    end                         as regiao,
    cd_municipio_tse,
    cd_municipio_ibge,
    nm_municipio,
    capital
from read_parquet('dados/base/municipios_2026.parquet');
