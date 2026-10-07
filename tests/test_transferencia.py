"""Testes da inferência ecológica e dos cenários de transferência."""

import numpy as np
import pandas as pd
import pytest

from eleicoes.transferencia import cenario, estimar_transicoes, lados_dos_finalistas


def test_estimar_transicoes_recupera_matriz_conhecida():
    rng = np.random.default_rng(3)
    P = np.array([[0.80, 0.05, 0.10, 0.05],
                  [0.02, 0.85, 0.08, 0.05],
                  [0.10, 0.10, 0.10, 0.70]])
    X = rng.dirichlet([5, 5, 3], size=600)
    Y = X @ P
    estimada = estimar_transicoes(X, Y, pesos=rng.uniform(1, 10, 600))
    assert estimada == pytest.approx(P, abs=0.01)
    assert estimada.sum(axis=1) == pytest.approx(np.ones(3), abs=1e-3)


def test_lados_ligam_finalistas_pelo_partido_e_pelo_que_sobra():
    finalistas = pd.DataFrame({
        "ano": [2018, 2018, 2022, 2022],
        "finalista": ["A", "B", "A", "B"],
        "nr_candidato": [17, 13, 13, 22],
        "sg_partido": ["PSL", "PT", "PT", "PL"],
    })
    # 2022: A = PT (mesmo partido do 13 de 2018); B = PL fica com o que sobrou (17, PSL)
    assert lados_dos_finalistas(finalistas, 2022, 2018) == {13: "lado_A", 17: "lado_B"}


def municipios(e_a, e_b):
    return pd.DataFrame({
        "A1": [600.0, 400.0], "B1": [400.0, 600.0],
        "E_A": e_a, "E_B": e_b, "E_S": [20.0, 20.0],
        "N_A": [0.0, 0.0], "N_B": [0.0, 0.0],
    })


def test_cenario_com_eliminados_equilibrados_mantem_o_placar_do_1o_turno():
    f = municipios([50.0, 50.0], [50.0, 50.0])
    for fidelidade in (0.5, 0.9):
        assert cenario(f, fidelidade, 0.05) == pytest.approx(0.5)


def test_cenario_com_eliminados_de_um_lado_favorece_esse_lado():
    f = municipios([90.0, 90.0], [10.0, 10.0])
    assert cenario(f, 0.9, 0.05) > cenario(f, 0.5, 0.05) > 0.5
