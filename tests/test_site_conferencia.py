"""Testes das funções puras da página "Conferência dos dados" (sem rede)."""

import math

import numpy as np
import pandas as pd
import pytest

from scripts.site_conferencia import benford, desvio_medio, digito, distribuicao, tipo_de_local


def test_benford_primeiro_digito_tem_os_valores_conhecidos():
    esperado = benford(1)
    assert list(esperado.index) == list(range(1, 10))
    assert esperado.sum() == pytest.approx(1)
    assert esperado[1] == pytest.approx(0.30103, abs=1e-5)    # log10(2)
    assert esperado[9] == pytest.approx(0.04576, abs=1e-5)    # log10(10/9)
    assert esperado.is_monotonic_decreasing


def test_benford_segundo_digito_vai_de_0_a_9_e_e_quase_plano():
    esperado = benford(2)
    assert list(esperado.index) == list(range(0, 10))
    assert esperado.sum() == pytest.approx(1)
    assert esperado[0] == pytest.approx(0.11968, abs=1e-5)
    assert esperado[9] == pytest.approx(0.08500, abs=1e-5)
    assert esperado.is_monotonic_decreasing


def test_benford_so_aceita_primeiro_e_segundo_digito():
    with pytest.raises(ValueError):
        benford(3)


def test_digito_pega_o_primeiro_e_o_segundo_e_ignora_quem_nao_tem():
    valores = [0, 7, 10, 19, 105, 230, 999, 1000, 6552820]
    assert digito(valores, 1).tolist() == [7, 1, 1, 1, 2, 9, 1, 6]          # o zero não tem 1º dígito
    assert digito(valores, 2).tolist() == [0, 9, 0, 3, 9, 0, 5]             # 0 e 7 não têm 2º dígito


def test_digito_aceita_serie_com_indice_qualquer():
    serie = pd.Series([300, 40, 5], index=[10, 20, 30])
    assert digito(serie).tolist() == [3, 4, 5]


def test_distribuicao_inclui_digitos_sem_ocorrencia_e_soma_um():
    tabela = distribuicao(pd.Series([1, 1, 2, 9]), posicao=1)
    assert tabela["digito"].tolist() == list(range(1, 10))
    assert tabela["quantidade"].tolist() == [2, 1, 0, 0, 0, 0, 0, 0, 1]
    assert tabela["proporcao"].sum() == pytest.approx(1)
    assert tabela.loc[tabela["digito"] == 1, "proporcao"].item() == pytest.approx(0.5)
    assert tabela["benford"].tolist() == pytest.approx(benford(1).tolist())


def test_numeros_que_variam_em_varias_ordens_de_grandeza_seguem_benford():
    # crescimento geométrico (como populações): segue a curva
    geometrica = np.round(1.01 ** np.arange(2000) * 10).astype(int)
    tabela = distribuicao(digito(geometrica), 1)
    assert desvio_medio(tabela["proporcao"], tabela["benford"]) < 0.01


def test_numeros_de_uma_ordem_de_grandeza_so_nao_seguem_benford():
    # "seções" com 150 a 330 votos: o 1º dígito só pode ser 1, 2 ou 3
    secoes = np.arange(150, 331)
    tabela = distribuicao(digito(secoes), 1)
    assert set(tabela.loc[tabela["quantidade"] > 0, "digito"]) == {1, 2, 3}
    assert desvio_medio(tabela["proporcao"], tabela["benford"]) > 0.05


def test_desvio_medio():
    assert desvio_medio([0.5, 0.5], [0.5, 0.5]) == 0
    assert desvio_medio([0.6, 0.4], [0.5, 0.5]) == pytest.approx(0.1)
    assert math.isclose(desvio_medio(np.array([1.0, 0.0]), [0.0, 1.0]), 1.0)


@pytest.mark.parametrize("nome, uf, tipo", [
    ("EMBAIXADA DO BRASIL EM TÚNIS", "ZZ", "exterior"),
    ("PENITENCIÁRIA ESTADUAL DE SAPUCAIA DO SUL", "RS", "presídio ou unidade para adolescentes"),
    ("PRESÍDIO REGIONAL DE CHAPECÓ", "SC", "presídio ou unidade para adolescentes"),
    ("FUNDAÇÃO CASA GUARULHOS", "SP", "presídio ou unidade para adolescentes"),
    ("CENTRO DE DETENÇÃO PROVISÓRIA DE MAUÁ", "SP", "presídio ou unidade para adolescentes"),
    ("UPR DE DAVINÓPOLIS", "MA", "presídio ou unidade para adolescentes"),
    ("ALDEIA PARANATINGA - ESCOLA YOPAKA", "PA", "aldeia ou escola indígena"),
    ("E. M. INDÍGENA DOM PEDRO II", "AM", "aldeia ou escola indígena"),
    ("COMUNIDADE TEKOA NHE ENGATU", "RS", "aldeia ou escola indígena"),
    ("ESCOLA MUNICIPAL GASTAO PENALVA", "RJ", "outro"),          # "PENAL" só como palavra inteira
    ("CENTRO DE INOVAÇÃO CADEIA CRIATIVA DE SOBRAL", "CE", "outro"),
    ("CADEIA PÚBLICA DE JUARA", "MT", "presídio ou unidade para adolescentes"),
    ("EMEF SÃO JOSÉ", "PA", "outro"),
    (None, "SP", "outro"),
])
def test_tipo_de_local(nome, uf, tipo):
    assert tipo_de_local(nome, uf) == tipo
