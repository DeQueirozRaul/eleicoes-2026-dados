"""Previsão ao vivo do 2º turno durante a apuração.

Ideia: o placar parcial engana porque as regiões apuram em ritmos diferentes.
A cada atualização, o modelo:

1. compara, em cada município com votos já apurados, o resultado parcial com a
   previsão feita antes da eleição (o "resíduo", na escala logit);
2. estima o quanto a previsão está errando no país e em cada UF (modelo
   normal hierárquico: resíduo = erro nacional + erro da UF + erro do município),
   o que permite corrigir também os municípios que ainda não apuraram nada;
3. projeta os votos que faltam em cada município e soma ao que já foi apurado,
   admitindo que o que falta pode ser sistematicamente diferente do que chegou;
4. repete com milhares de sorteios dos erros para obter intervalo e probabilidade.

Entrada (`estado`), uma linha por município:
    uf, qt_aptos, qt_aptos_apurados, qt_a, qt_b       (o que já foi apurado)
    logit_prior    previsão de antes da eleição para o % de A (logit)
    taxa_validos   votos válidos esperados por eleitor apto
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from eleicoes.modelo_2t import logistica, logit


# Abaixo disso a projeção oscila demais (os primeiros boletins vêm de poucas
# regiões); no teste com o 2º turno de 2022 ela só ficou estável a partir de ~5%.
MINIMO_APURADO = 0.05


@dataclass
class Parametros:
    tau_nacional: float = 0.17    # incerteza do erro nacional antes de apurar (logit)
    sigma_uf: float = 0.125       # variação do erro entre UFs
    sigma_mun: float = 0.138      # variação do erro entre municípios
    c_tamanho: float = 11.3       # ruído extra de municípios pequenos (÷ votos válidos)
    sigma_parcial: float = 0.20   # o que já foi apurado num município difere do que falta
    # O que ainda falta apurar pode diferir de forma sistemática do que já chegou
    # (regiões e seções que apuram mais tarde votam diferente). Esse erro não
    # diminui com mais dados apurados, só com menos votos faltando.
    sigma_restante_nacional: float = 0.04
    sigma_restante_uf: float = 0.05


@dataclass
class Projecao:
    pct_a_apurado: float          # placar oficial parcial
    pct_secoes: float             # fração do eleitorado já apurada
    pct_a_mediana: float
    pct_a_inferior: float
    pct_a_superior: float
    prob_a_vence: float

    @property
    def publicavel(self) -> bool:
        return self.pct_secoes >= MINIMO_APURADO


def _posterior_erros(r, w_var, uf_idx, n_uf, p: Parametros):
    """Média e covariância a posteriori de (erro nacional, erros das UFs)
    no modelo r_i = mu + u_uf + e_i, e_i ~ N(0, w_var_i)."""
    k = 1 + n_uf
    precisao = np.zeros((k, k))
    precisao[0, 0] = 1 / p.tau_nacional ** 2
    precisao[np.arange(1, k), np.arange(1, k)] = 1 / p.sigma_uf ** 2
    vetor = np.zeros(k)
    if len(r):
        inv = 1 / w_var
        precisao[0, 0] += inv.sum()
        por_uf = np.bincount(uf_idx, weights=inv, minlength=n_uf)
        precisao[0, 1:] += por_uf
        precisao[1:, 0] += por_uf
        precisao[np.arange(1, k), np.arange(1, k)] += por_uf
        vetor[0] = (inv * r).sum()
        vetor[1:] = np.bincount(uf_idx, weights=inv * r, minlength=n_uf)
    cov = np.linalg.inv(precisao)
    return cov @ vetor, cov


def projetar(estado: pd.DataFrame, p: Parametros = Parametros(), cenarios: int = 2000,
             semente: int = 0, nivel: float = 0.9) -> Projecao:
    rng = np.random.default_rng(semente)
    ufs, uf_idx = np.unique(estado["uf"].to_numpy(), return_inverse=True)
    n_uf = len(ufs)

    aptos = estado["qt_aptos"].to_numpy(float)
    aptos_ap = np.minimum(estado["qt_aptos_apurados"].to_numpy(float), aptos)
    a = estado["qt_a"].to_numpy(float)
    b = estado["qt_b"].to_numpy(float)
    validos = a + b
    prior = estado["logit_prior"].to_numpy(float)
    fracao = np.divide(aptos_ap, aptos, out=np.ones_like(aptos), where=aptos > 0)

    # 1. resíduos dos municípios com votos apurados
    tem = validos > 0
    r = logit((a[tem] + 0.5) / (validos[tem] + 1)) - prior[tem]
    var_mun = p.sigma_mun ** 2 + p.c_tamanho / np.maximum(validos[tem], 1)
    var_obs = var_mun + p.sigma_parcial ** 2 * (1 - fracao[tem])

    # 2. erro nacional e por UF
    media, cov = _posterior_erros(r, var_obs, uf_idx[tem], n_uf, p)

    # 3. votos que faltam em cada município
    taxa_obs = np.divide(validos, aptos_ap, out=np.zeros_like(validos), where=aptos_ap > 0)
    taxa = np.where(fracao >= 0.2, taxa_obs, estado["taxa_validos"].to_numpy(float))
    restante = (aptos - aptos_ap) * taxa

    # 4. sorteios
    erros = rng.multivariate_normal(media, cov, size=cenarios)          # cenários x (1 + UFs)
    base = prior[None, :] + erros[:, [0]] + erros[:, 1:][:, uf_idx]
    # erro próprio do município: o que já apurou informa sobre o que falta
    var_e = p.sigma_mun ** 2 + p.c_tamanho / np.maximum(aptos * taxa, 1)
    rho = np.zeros(len(estado))
    desvio_obs = np.zeros((cenarios, len(estado)))
    rho[tem] = var_e[tem] / (var_e[tem] + p.sigma_parcial ** 2 + p.c_tamanho / np.maximum(validos[tem], 1))
    desvio_obs[:, tem] = logit((a[tem] + 0.5) / (validos[tem] + 1))[None, :] - base[:, tem]
    e = rho * desvio_obs + rng.normal(size=base.shape) * np.sqrt((1 - rho) * var_e)
    atraso = (rng.normal(0, p.sigma_restante_nacional, size=(cenarios, 1))
              + rng.normal(0, p.sigma_restante_uf, size=(cenarios, n_uf))[:, uf_idx])
    pct_restante = logistica(base + e + atraso)

    total_a = a.sum() + (pct_restante * restante).sum(axis=1)
    total = validos.sum() + restante.sum()
    pct = total_a / total
    q = (1 - nivel) / 2
    return Projecao(
        pct_a_apurado=float(a.sum() / validos.sum()) if validos.sum() else float("nan"),
        pct_secoes=float(aptos_ap.sum() / aptos.sum()),
        pct_a_mediana=float(np.median(pct)),
        pct_a_inferior=float(np.quantile(pct, q)),
        pct_a_superior=float(np.quantile(pct, 1 - q)),
        prob_a_vence=float((pct > 0.5).mean()),
    )


def estado_do_coletor(pasta: str, nr_a: int, nr_b: int, prior: pd.DataFrame) -> pd.DataFrame:
    """Monta o `estado` a partir dos retratos salvos por scripts/coletar_ao_vivo.py.

    `pasta` é a pasta da eleição e cargo (ex.: dados/ao_vivo/e6258_c1); usa o
    retrato mais recente de cada município. `prior` traz uf, cd_municipio_tse,
    logit_prior e taxa_validos.
    """
    import duckdb

    con = duckdb.connect()
    andamento = con.sql(f"""
        select upper(uf) as uf, cd_abrangencia as cd_municipio_tse,
               qt_eleitores as qt_aptos, qt_eleitores_secoes_totalizadas as qt_aptos_apurados
        from read_parquet('{pasta}/*/andamento.parquet')
        where tp_abrangencia = 'mun'
        qualify row_number() over (partition by uf, cd_abrangencia order by dt_coleta desc) = 1
    """).df()
    votos = con.sql(f"""
        with ultimo as (
            select * from read_parquet('{pasta}/*/candidatos.parquet')
            where cd_municipio_tse <> ''
            qualify dense_rank() over (partition by uf, cd_municipio_tse order by dt_coleta desc) = 1
        )
        select upper(uf) as uf, cd_municipio_tse,
               coalesce(sum(qt_votos) filter (where nr_candidato::int = {nr_a}), 0) as qt_a,
               coalesce(sum(qt_votos) filter (where nr_candidato::int = {nr_b}), 0) as qt_b
        from ultimo group by all
    """).df()
    con.close()
    estado = andamento.merge(votos, on=["uf", "cd_municipio_tse"], how="left").fillna({"qt_a": 0, "qt_b": 0})
    estado = estado.merge(prior, on=["uf", "cd_municipio_tse"], how="left")
    estado["logit_prior"] = estado["logit_prior"].fillna(0.0)
    estado["taxa_validos"] = estado["taxa_validos"].fillna(estado["taxa_validos"].median())
    return estado
