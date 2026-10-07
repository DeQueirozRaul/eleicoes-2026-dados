"""Testes da previsão ao vivo com apurações sintéticas."""

import numpy as np
import pandas as pd
import pytest

from eleicoes.ao_vivo import Parametros, projetar
from eleicoes.modelo_2t import logistica


def municipios(n=300, semente=0, erro_real=0.10):
    """Municípios em 6 UFs; o resultado real é a previsão de antes + `erro_real`."""
    rng = np.random.default_rng(semente)
    df = pd.DataFrame({
        "uf": rng.choice(list("ABCDEF"), n),
        "qt_aptos": rng.integers(2_000, 80_000, n).astype(float),
        "logit_prior": rng.normal(0, 0.5, n),
        "taxa_validos": 0.75,
    })
    df["pct_real"] = logistica(df["logit_prior"] + erro_real + rng.normal(0, 0.05, n))
    return df


def apurar(df, fracao):
    """Apura a mesma fração do eleitorado em cada município (sem viés de ordem)."""
    out = df.copy()
    out["qt_aptos_apurados"] = out["qt_aptos"] * fracao
    validos = out["qt_aptos_apurados"] * out["taxa_validos"]
    out["qt_a"] = validos * out["pct_real"]
    out["qt_b"] = validos - out["qt_a"]
    return out


def pct_real_nacional(df):
    validos = df["qt_aptos"] * df["taxa_validos"]
    return (validos * df["pct_real"]).sum() / validos.sum()


def test_tudo_apurado_projecao_igual_ao_placar():
    df = apurar(municipios(), 1.0)
    p = projetar(df, cenarios=500)
    assert p.pct_secoes == pytest.approx(1)
    assert p.pct_a_mediana == pytest.approx(p.pct_a_apurado, abs=1e-6)
    assert p.pct_a_superior - p.pct_a_inferior < 1e-6


def test_nada_apurado_usa_a_previsao_de_antes_com_incerteza_grande():
    df = apurar(municipios(erro_real=0.0), 0.0)
    p = projetar(df, Parametros(tau_nacional=0.2), cenarios=2000)
    esperado = (df["qt_aptos"] * logistica(df["logit_prior"])).sum() / df["qt_aptos"].sum()
    assert p.pct_a_mediana == pytest.approx(esperado, abs=0.01)
    assert p.pct_a_superior - p.pct_a_inferior > 0.05


def test_aprende_o_erro_com_parte_dos_municipios_apurados():
    df = municipios(erro_real=0.15)
    real = pct_real_nacional(df)
    apurados = apurar(df, 1.0)
    faltam = df.sample(frac=0.6, random_state=1).index    # 60% dos municípios ainda sem nada
    apurados.loc[faltam, ["qt_aptos_apurados", "qt_a", "qt_b"]] = 0
    p = projetar(apurados, cenarios=2000)
    assert abs(p.pct_a_apurado - real) > abs(p.pct_a_mediana - real)
    assert p.pct_a_inferior <= real <= p.pct_a_superior
    assert p.pct_a_mediana == pytest.approx(real, abs=0.01)
