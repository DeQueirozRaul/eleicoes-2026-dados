"""Modelo de previsão do 2º turno presidencial a partir do 1º turno, por município.

Notação (para cada município i de uma eleição):
    z_i = logit(% de A entre os dois finalistas no 1º turno)
    e_i = % dos votos válidos do 1º turno que foram para candidatos eliminados
    y_i = logit(% de A no 2º turno)               (o que queremos prever)
e, no total nacional, Z, E e Y. A = 1º colocado nacional no 1º turno.

Duas etapas:

1. Nacional: quanto o placar entre os finalistas muda do 1º para o 2º turno.
       delta = Y - Z = k * E + eta,   eta ~ Normal(0, tau²)
   Ou seja, a mudança tende a ser proporcional ao tamanho do voto nos
   eliminados, mais um choque que não depende dele (como em 2006). k e tau são
   estimados com as eleições anteriores.

2. Municipal: como essa mudança nacional se distribui pelos municípios.
       y_i = z_i + delta
             + lambda * delta * (e_i / E - 1)        muda mais onde há mais eliminados
             + gamma  * e_i * (z_i - Z)              eliminados se dividem de forma mais
                                                     equilibrada que o município (gamma < 0)
             + u_UF + eps_i
   com u_UF ~ Normal(0, sigma_uf²) e var(eps_i) = sigma_mun² + c / votos_validos_i.
   Também existe o termo `beta * (z_i - Z)` (regressão à média), testado na
   validação mas fora do modelo padrão porque piorou a previsão.

A incerteza vem de simular milhares de cenários (delta, u_UF e eps_i).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

TERMOS_MUNICIPAIS = ("lambda", "gamma")


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def logistica(x):
    return 1 / (1 + np.exp(-x))


def preparar(base: pd.DataFrame) -> pd.DataFrame:
    """Calcula z, e, y e os totais nacionais (Z, E, Y) a partir de `transicao_turnos`."""
    df = base[(base["qt_a_1t"] + base["qt_b_1t"]) > 0].copy()
    df["peso"] = df["qt_validos_1t"].astype(float)
    df["z"] = logit(df["qt_a_1t"] / (df["qt_a_1t"] + df["qt_b_1t"]))
    df["e"] = df["qt_eliminados_1t"] / df["qt_validos_1t"]
    tem_2t = df["qt_a_2t"].notna() & ((df["qt_a_2t"] + df["qt_b_2t"]) > 0)
    df["y"] = np.where(tem_2t, logit(df["qt_a_2t"] / (df["qt_a_2t"] + df["qt_b_2t"])), np.nan)

    nacional = df.groupby("ano").agg(
        a1=("qt_a_1t", "sum"), b1=("qt_b_1t", "sum"), el=("qt_eliminados_1t", "sum"),
        v1=("qt_validos_1t", "sum"), a2=("qt_a_2t", "sum"), b2=("qt_b_2t", "sum"),
    )
    nacional["Z"] = logit(nacional["a1"] / (nacional["a1"] + nacional["b1"]))
    nacional["E"] = nacional["el"] / nacional["v1"]
    soma_2t = nacional["a2"] + nacional["b2"]
    nacional["Y"] = np.where(soma_2t > 0, logit(nacional["a2"] / soma_2t.where(soma_2t > 0)), np.nan)
    return df.join(nacional[["Z", "E", "Y"]], on="ano")


def _regressores(df: pd.DataFrame, delta, termos) -> np.ndarray:
    colunas = {
        "beta": df["z"] - df["Z"],
        "lambda": delta * (df["e"] / df["E"] - 1),
        "gamma": df["e"] * (df["z"] - df["Z"]),
    }
    if not termos:
        return np.zeros((len(df), 0))
    return np.column_stack([np.asarray(colunas[t], dtype=float) for t in termos])


@dataclass
class Modelo:
    """Parâmetros aprendidos com as eleições de treino."""

    anos_treino: list[int]
    k: float
    tau: float
    soma_e2: float
    coeficientes: dict[str, float]
    sigma_uf: float
    sigma_mun: float
    c_tamanho: float

    def resumo(self) -> dict:
        return asdict(self)


def ajustar(dados: pd.DataFrame, termos=TERMOS_MUNICIPAIS) -> Modelo:
    """Ajusta o modelo nas eleições de `dados` que já tiveram 2º turno."""
    treino = dados[dados["y"].notna()]
    anos = sorted(treino["ano"].unique())

    # Etapa 1 (nacional): delta = k * E + eta, regressão sem intercepto.
    nac = treino.groupby("ano")[["Z", "E", "Y"]].first()
    delta = nac["Y"] - nac["Z"]
    soma_e2 = float((nac["E"] ** 2).sum())
    k = float((delta * nac["E"]).sum() / soma_e2)
    residuos = delta - k * nac["E"]
    tau = float(np.sqrt((residuos ** 2).sum() / max(len(nac) - 1, 1)))

    # Etapa 2 (municipal): mínimos quadrados ponderados pelos votos válidos.
    delta_ano = treino["ano"].map(delta)
    alvo = treino["y"] - treino["z"] - delta_ano
    X = _regressores(treino, delta_ano, termos)
    w = treino["peso"].to_numpy()
    if X.shape[1]:
        sw = np.sqrt(w)
        coef, *_ = np.linalg.lstsq(X * sw[:, None], alvo.to_numpy() * sw, rcond=None)
    else:
        coef = np.zeros(0)
    resid = alvo.to_numpy() - X @ coef

    # Componentes de variância: efeito da UF (por ano) e ruído municipal.
    r = treino[["ano", "uf", "peso"]].assign(r=resid)
    r["rw"] = r["r"] * r["peso"]
    grupos = r.groupby(["ano", "uf"])
    r["ruf"] = grupos["rw"].transform("sum") / grupos["peso"].transform("sum")
    efeitos_uf = r.groupby(["ano", "uf"])["ruf"].first()
    sigma_uf = float(efeitos_uf.std())
    eps2 = (r["r"] - r["ruf"]) ** 2
    A = np.column_stack([np.ones(len(r)), 1 / r["peso"].to_numpy()])
    (s2, c), *_ = np.linalg.lstsq(A, eps2.to_numpy(), rcond=None)

    return Modelo(
        anos_treino=[int(a) for a in anos], k=k, tau=tau, soma_e2=soma_e2,
        coeficientes={t: float(v) for t, v in zip(termos, coef)},
        sigma_uf=sigma_uf, sigma_mun=float(np.sqrt(max(s2, 0))), c_tamanho=float(max(c, 0)),
    )


def prever_municipios(modelo: Modelo, df: pd.DataFrame, delta) -> np.ndarray:
    """Valor esperado de y_i para um delta nacional (sem os ruídos)."""
    termos = list(modelo.coeficientes)
    coef = np.array([modelo.coeficientes[t] for t in termos])
    X = _regressores(df, delta, termos)
    return df["z"].to_numpy() + delta + (X @ coef if len(coef) else 0)


@dataclass
class Simulacao:
    nacional: np.ndarray        # % de A no país em cada cenário
    por_uf: pd.DataFrame        # média e intervalo por UF
    por_municipio: pd.DataFrame  # média e intervalo por município
    delta: np.ndarray

    def resumo(self, nivel: float = 0.9) -> dict:
        q = (1 - nivel) / 2
        return {
            "pct_a_mediana": float(np.median(self.nacional)),
            "pct_a_inferior": float(np.quantile(self.nacional, q)),
            "pct_a_superior": float(np.quantile(self.nacional, 1 - q)),
            "prob_a_vence": float((self.nacional > 0.5).mean()),
            "nivel_intervalo": nivel,
            "cenarios": int(len(self.nacional)),
        }


def simular(modelo: Modelo, df: pd.DataFrame, cenarios: int = 10_000,
            semente: int = 2026, lote: int = 500) -> Simulacao:
    """Simula o 2º turno de uma eleição (df com um só ano) a partir do 1º turno."""
    rng = np.random.default_rng(semente)
    E = float(df["E"].iloc[0])
    n_treino = len(modelo.anos_treino)

    # Incerteza do delta nacional: choque (tau) + incerteza na estimativa de k,
    # com cauda de t de Student porque há poucas eleições de treino.
    escala = modelo.tau * np.sqrt(1 + E ** 2 / modelo.soma_e2)
    delta = modelo.k * E + escala * rng.standard_t(df=max(n_treino - 1, 1), size=cenarios)

    ufs, uf_idx = np.unique(df["uf"].to_numpy(), return_inverse=True)
    peso = df["peso"].to_numpy()
    sd_mun = np.sqrt(modelo.sigma_mun ** 2 + modelo.c_tamanho / peso)
    nacional = np.empty(cenarios)
    soma_s = np.zeros(len(df))
    amostras_mun = []
    soma_uf = np.zeros((cenarios, len(ufs)))
    peso_uf = np.bincount(uf_idx, weights=peso, minlength=len(ufs))

    for inicio in range(0, cenarios, lote):
        d = delta[inicio:inicio + lote]
        base = np.stack([prever_municipios(modelo, df, di) for di in d])
        u = rng.normal(0, modelo.sigma_uf, size=(len(d), len(ufs)))[:, uf_idx]
        eps = rng.normal(0, 1, size=base.shape) * sd_mun
        s = logistica(base + u + eps)
        nacional[inicio:inicio + lote] = s @ peso / peso.sum()
        votos_a = s * peso
        for j in range(len(ufs)):
            soma_uf[inicio:inicio + lote, j] = votos_a[:, uf_idx == j].sum(axis=1)
        soma_s += s.sum(axis=0)
        if len(amostras_mun) * lote < 2000:
            amostras_mun.append(s)

    amostra = np.vstack(amostras_mun)
    por_municipio = df[["ano", "uf", "cd_municipio_tse"]].copy()
    por_municipio["pct_a_media"] = soma_s / cenarios
    por_municipio["pct_a_inferior"] = np.quantile(amostra, 0.05, axis=0)
    por_municipio["pct_a_superior"] = np.quantile(amostra, 0.95, axis=0)

    pct_uf = soma_uf / peso_uf
    por_uf = pd.DataFrame({
        "uf": ufs,
        "pct_a_mediana": np.median(pct_uf, axis=0),
        "pct_a_inferior": np.quantile(pct_uf, 0.05, axis=0),
        "pct_a_superior": np.quantile(pct_uf, 0.95, axis=0),
        "prob_a_vence": (pct_uf > 0.5).mean(axis=0),
    })
    return Simulacao(nacional=nacional, por_uf=por_uf, por_municipio=por_municipio, delta=delta)


def erro_municipal(modelo: Modelo, df: pd.DataFrame) -> float:
    """Erro (pontos percentuais, ponderado por votos) dos municípios de uma eleição
    já realizada, usando o delta nacional verdadeiro. Mede só a etapa 2."""
    df = df[df["y"].notna()]
    delta_real = float(df["Y"].iloc[0] - df["Z"].iloc[0])
    previsto = logistica(prever_municipios(modelo, df, delta_real))
    real = logistica(df["y"].to_numpy())
    return float(np.sqrt(np.average((previsto - real) ** 2, weights=df["peso"])) * 100)
