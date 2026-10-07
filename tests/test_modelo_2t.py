"""Testes do modelo de 2º turno com dados sintéticos de parâmetros conhecidos."""

import numpy as np
import pandas as pd
import pytest

from eleicoes.modelo_2t import ajustar, logistica, logit, preparar, simular

K, LAMBDA, GAMMA = -0.7, 0.3, -0.6


def eleicao_sintetica(ano, rng, n=400, choque=0.0, ruido=0.01, com_2t=True):
    """Gera municípios cujo 2º turno segue exatamente o modelo (mais ruído pequeno)."""
    validos = rng.integers(2_000, 200_000, n)
    h = rng.uniform(0.25, 0.75, n)
    e = rng.uniform(0.03, 0.30, n)
    a1 = np.round(validos * (1 - e) * h)
    b1 = np.round(validos * (1 - e) * (1 - h))
    elim = validos - a1 - b1
    df = pd.DataFrame({
        "ano": ano, "uf": rng.choice(["AA", "BB", "CC", "DD"], n), "cd_municipio_tse": [f"{i:05d}" for i in range(n)],
        "qt_a_1t": a1, "qt_b_1t": b1, "qt_eliminados_1t": elim, "qt_validos_1t": validos,
        "qt_a_2t": np.nan, "qt_b_2t": np.nan,
    })
    if com_2t:
        p = preparar(df)
        delta = K * p["E"].iloc[0] + choque
        y = (p["z"] + delta + LAMBDA * delta * (p["e"] / p["E"] - 1)
             + GAMMA * p["e"] * (p["z"] - p["Z"]) + rng.normal(0, ruido, n))
        s = logistica(y)
        df["qt_a_2t"] = np.round(validos * s)
        df["qt_b_2t"] = validos - df["qt_a_2t"]
    return df


@pytest.fixture
def historico():
    rng = np.random.default_rng(1)
    choques = [0.02, -0.01, 0.0, 0.015, -0.02]
    return pd.concat([eleicao_sintetica(2000 + 4 * i, rng, choque=c) for i, c in enumerate(choques)])


def test_preparar_calcula_os_totais_nacionais():
    df = pd.DataFrame({
        "ano": [2022, 2022], "uf": ["AA", "BB"], "cd_municipio_tse": ["1", "2"],
        "qt_a_1t": [60, 20], "qt_b_1t": [20, 60], "qt_eliminados_1t": [20, 20], "qt_validos_1t": [100, 100],
        "qt_a_2t": [70, 30], "qt_b_2t": [30, 70],
    })
    p = preparar(df)
    assert p["z"].iloc[0] == pytest.approx(logit(0.75))
    assert p["e"].tolist() == pytest.approx([0.2, 0.2])
    assert p["Z"].iloc[0] == pytest.approx(0)       # 80 x 80 no país
    assert p["E"].iloc[0] == pytest.approx(0.2)
    assert p["Y"].iloc[0] == pytest.approx(0)       # 100 x 100 no país


def test_ajustar_recupera_os_parametros(historico):
    modelo = ajustar(preparar(historico))
    assert modelo.coeficientes["lambda"] == pytest.approx(LAMBDA, abs=0.05)
    assert modelo.coeficientes["gamma"] == pytest.approx(GAMMA, abs=0.1)
    assert modelo.k == pytest.approx(K, abs=0.15)
    assert modelo.tau < 0.05
    assert modelo.sigma_mun < 0.05


def test_simular_previsao_contem_o_resultado(historico):
    rng = np.random.default_rng(7)
    nova = preparar(eleicao_sintetica(2030, rng))
    modelo = ajustar(preparar(historico))
    sim = simular(modelo, nova.assign(y=np.nan, Y=np.nan), cenarios=2000)
    r = sim.resumo()
    real = logistica(nova["Y"].iloc[0])
    assert 0 <= r["prob_a_vence"] <= 1
    assert r["pct_a_inferior"] <= r["pct_a_mediana"] <= r["pct_a_superior"]
    assert r["pct_a_inferior"] <= real <= r["pct_a_superior"]
    assert len(sim.por_municipio) == len(nova)
    assert set(sim.por_uf["uf"]) == {"AA", "BB", "CC", "DD"}
