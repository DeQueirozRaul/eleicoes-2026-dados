"""Testes das funções puras de scripts/site_resultados.py (página "Resultados e mapa")."""

import pandas as pd
import pytest

from scripts.site_resultados import (
    area_com_sinal,
    cortes_deputados,
    douglas_peucker,
    lado_governador,
    mais_votados,
    nome_proprio,
    orientar,
    partidos_do_agrupamento,
    sigla,
    simplificar_malha,
    transicao,
)


# --- geometria ----------------------------------------------------------------
def test_douglas_peucker_tira_pontos_quase_alinhados_e_mantem_pontas():
    linha = [(0, 0), (1, 0.1), (2, -0.1), (3, 5), (4, 0), (5, 0)]
    assert douglas_peucker(linha, tolerancia=0.5) == [(0, 0), (2, -0.1), (3, 5), (4, 0), (5, 0)]
    assert douglas_peucker(linha, tolerancia=10) == [(0, 0), (5, 0)]
    assert douglas_peucker([(0, 0), (1, 1)], tolerancia=10) == [(0, 0), (1, 1)]


def quadrado_com_divisa_ondulada():
    """Dois municípios lado a lado; a divisa entre eles (x = 10) tem pontos que
    quase não fazem curva e devem sumir dos DOIS lados, sem abrir fresta."""
    divisa = [(10, 0), (10, 2), (11, 4), (10, 6), (10, 8), (10, 10)]  # (11, 4) se afasta 1
    esquerda = [(0, 0)] + divisa + [(0, 10), (0, 0)]
    direita = [(20, 0), (20, 10)] + divisa[::-1] + [(20, 0)]
    return {"E": [[esquerda]], "D": [[direita]]}


def pontos_da_divisa(anel):
    return {p for p in anel if p[0] in (10, 11)}


def test_simplificar_malha_simplifica_a_divisa_igual_para_os_dois_vizinhos():
    # com tolerância 0,5: (10, 2) fica a 0,49 do trecho (10, 0)-(11, 4) e sai; (10, 6) fica a 0,66 e fica
    for tolerancia, esperado in ((0.5, {(10, 0), (11, 4), (10, 6), (10, 10)}),
                                 (2, {(10, 0), (10, 10)})):
        saida, degenerados = simplificar_malha(quadrado_com_divisa_ondulada(), tolerancia)
        e, d = saida["E"][0][0], saida["D"][0][0]
        assert pontos_da_divisa(e) == pontos_da_divisa(d) == esperado
        assert e[0] == e[-1] and d[0] == d[-1]  # anéis continuam fechados
        assert degenerados == 0


def test_simplificar_malha_mantem_enclave_encaixado_no_buraco():
    enclave = [(4, 4), (5, 4.2), (6, 4), (6, 6), (4, 6), (4, 4)]
    externo = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    poligonos = {"fora": [[externo, enclave[::-1]]], "dentro": [[enclave]]}
    saida, _ = simplificar_malha(poligonos, tolerancia=0.5)
    buraco, ilha = saida["fora"][0][1], saida["dentro"][0][0]
    assert set(buraco) == set(ilha)
    assert (5, 4.2) not in ilha


def test_orientar_poe_externo_no_sentido_horario_e_buraco_no_anti_horario():
    anti_horario = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    assert area_com_sinal(anti_horario) == 100
    externo, buraco = orientar([anti_horario, anti_horario[::-1]])
    assert area_com_sinal(externo) < 0
    assert area_com_sinal(buraco) > 0


# --- textos ---------------------------------------------------------------------
@pytest.mark.parametrize("entrada, saida", [
    ("SÃO JOÃO DO RIO VERMELHO", "São João do Rio Vermelho"),
    ("PINGO D'ÁGUA", "Pingo d'Água"),
    ("EMBU-GUAÇU", "Embu-Guaçu"),
    ("BOA ESPERANÇA DO NORTE", "Boa Esperança do Norte"),
])
def test_nome_proprio(entrada, saida):
    assert nome_proprio(entrada) == saida


def test_sigla_normaliza_acentos_e_espacos():
    assert sigla("PC do B") == "PCDOB"
    assert sigla("UNIÃO") == "UNIAO"
    assert sigla("MISSÃO") == "MISSAO"


# --- resultados ---------------------------------------------------------------------
def test_mais_votados_calcula_porcentagens_e_marca_empate():
    votos = pd.DataFrame({
        "municipio": ["1", "1", "1", "2", "2"],
        "nm_urna": ["B", "A", "C", "B", "A"],
        "sg_partido": ["PB", "PA", "PC", "PB", "PA"],
        "qt_votos": [60, 30, 10, 50, 50],
    })
    r = mais_votados(votos, ["municipio"]).set_index("municipio")
    assert r.loc["1", "mais_votado"] == "B"
    assert r.loc["1", "pct_mais_votado"] == pytest.approx(0.6)
    assert r.loc["1", "vantagem"] == pytest.approx(0.3)
    assert r.loc["1", "qt_validos"] == 100
    assert not r.loc["1", "empate"]
    assert r.loc["2", "empate"]
    assert r.loc["2", "mais_votado"] == "empate"
    assert r.loc["2", "empatados"] == "A e B"  # ordem alfabética


def test_transicao_descreve_os_dois_sentidos_igual():
    assert transicao("PL", "PL") == "PL nas duas"
    assert transicao("PT", "PL") == "PT em 2022 → PL em 2026"
    assert transicao("PL", "PT") == "PL em 2022 → PT em 2026"
    assert transicao(None, "PL") == "sem resultado em 2022"


def test_lado_governador_usa_a_coligacao_do_mais_votado():
    todos = {"PL", "NOVO", "PT", "PV", "MDB"}
    assert lado_governador("PL", {"PL", "NOVO"}, todos) == "mesma coligação"
    assert lado_governador("PT", {"PL", "NOVO"}, todos) == "coligações diferentes"
    assert lado_governador("MISSÃO", {"PL", "NOVO"}, todos | {"MISSAO"}) == "coligações diferentes"
    assert lado_governador("UP", {"PL", "NOVO"}, todos) == "partido sem candidato a Governador"


def test_partidos_do_agrupamento_le_federacoes_e_coligacoes():
    agrupamento = {"com": "PDT / PSB / PCDOB / PT / PV / PSOL / REDE", "par": [{"sg": "PSB"}]}
    assert partidos_do_agrupamento(agrupamento) == {"PDT", "PSB", "PCDOB", "PT", "PV", "PSOL", "REDE"}
    isolado = {"com": "", "par": [{"sg": "UNIÃO"}]}
    assert partidos_do_agrupamento(isolado) == {"UNIAO"}


def test_cortes_deputados_compara_eleito_menos_votado_com_nao_eleitos():
    c = pd.DataFrame({
        "uf": ["XX"] * 5,
        "nm_urna": ["E1", "E2", "N1", "N2", "SJ"],
        "sg_partido": ["P1", "P2", "P3", "P1", "P2"],
        "qt_votos": [100, 40, 70, 30, 500],
        "eleito": [True, True, False, False, False],
        "voto_valido": [True, True, True, True, False],  # SJ: votos anulados sub judice, fica de fora
    })
    r = cortes_deputados(c).iloc[0]
    assert (r["menor_eleito"], r["votos_menor_eleito"]) == ("E2", 40)
    assert (r["maior_nao_eleito"], r["votos_maior_nao_eleito"]) == ("N1", 70)
    assert r["fora_com_mais_votos"] == 1
    assert r["eleitos_com_menos_votos"] == 1
