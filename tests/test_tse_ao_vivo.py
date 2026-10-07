"""Testes do leitor dos JSONs ao vivo, usando arquivos reais do 1º turno de 2026."""

import json
from pathlib import Path

import pandas as pd
import pytest

from eleicoes.tse_ao_vivo import (
    ClienteTSE,
    caminho_andamento,
    caminho_resultado,
    ler_andamento,
    ler_eleicoes,
    ler_municipios,
    ler_resultado,
)

FIXTURES = Path(__file__).parent / "fixtures"


def carregar(nome: str) -> dict:
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


def test_caminhos_seguem_o_padrao_do_tse():
    assert caminho_resultado("ele2026", 6257, 1, "br") == "ele2026/6257/dados/br/br-c0001-e006257-u.json"
    assert (caminho_resultado("ele2026", 6257, 1, "df", "97012")
            == "ele2026/6257/dados/df/df97012-c0001-e006257-u.json")
    assert caminho_andamento("ele2026", 6257, "sp") == "ele2026/6257/dados/sp/sp-e006257-ab.json"


def test_ler_eleicoes_traz_o_codigo_do_segundo_turno():
    eleicoes = ler_eleicoes(carregar("ele-c.json"))
    presidente = eleicoes[eleicoes["ds_cargo"] == "Presidente"].iloc[0]
    assert presidente["cd_eleicao"] == 6257
    assert presidente["cd_eleicao_2t"] == 6258
    assert presidente["turno"] == 1
    governador = eleicoes[eleicoes["ds_cargo"] == "Governador"].iloc[0]
    assert governador["cd_eleicao"] == 6259


def test_ler_municipios_tem_codigo_tse_e_ibge():
    municipios = ler_municipios(carregar("mun-e006257-cm.json"))
    brasilia = municipios[municipios["uf"] == "df"].iloc[0]
    assert brasilia["cd_municipio_tse"] == "97012"
    assert brasilia["cd_municipio_ibge"] == "5300108"
    assert brasilia["capital"]
    assert brasilia["qt_zonas"] == 19
    assert (municipios["uf"] == "ac").sum() == 22


def test_ler_andamento_converte_numeros_e_horario():
    andamento = ler_andamento(carregar("df-e006257-ab.json"), "df")
    linha = andamento[andamento["tp_abrangencia"] == "mun"].iloc[0]
    assert linha["qt_secoes"] == linha["qt_secoes_totalizadas"] == 6969
    assert linha["qt_comparecimento"] + linha["qt_abstencao"] == linha["qt_eleitores"]
    assert linha["dt_totalizacao"] == pd.Timestamp("2026-10-04 20:11:33", tz="America/Sao_Paulo")


def test_ler_resultado_soma_dos_candidatos_bate_com_os_validos():
    resultado = ler_resultado(carregar("df97012-c0001-e006257-u.json"))
    resumo, candidatos = resultado.resumo, resultado.candidatos

    assert resumo["tp_abrangencia"] == "mu"
    assert resumo["totalizacao_final"]
    assert candidatos["qt_votos"].sum() == resumo["qt_votos_validos"] == 1_772_808
    assert (resumo["qt_votos_validos"] + resumo["qt_votos_brancos"] + resumo["qt_votos_nulos"]
            == resumo["qt_votos_total"])
    assert candidatos["pc_votos_validos"].sum() == pytest.approx(1)
    assert set(candidatos["situacao"]) >= {"2º turno", "Não eleito"}
    assert len(candidatos) == 12


class SessaoFalsa:
    """Responde aos GETs com os arquivos de fixtures, sem usar a rede."""

    def __init__(self, arquivos: dict[str, str]):
        self.arquivos = arquivos
        self.headers = {}
        self.pedidos = []

    def get(self, url, timeout):
        self.pedidos.append(url)
        nome = self.arquivos.get(url.rsplit("/", 1)[-1])
        return RespostaFalsa(carregar(nome) if nome else None)


class RespostaFalsa:
    def __init__(self, conteudo):
        self.conteudo = conteudo
        self.status_code = 200 if conteudo is not None else 404

    def raise_for_status(self):
        pass

    def json(self):
        return self.conteudo


def test_cliente_devolve_none_quando_arquivo_nao_existe():
    cliente = ClienteTSE(sessao=SessaoFalsa({}))
    assert cliente.resultado(6258, 1) is None


def test_cliente_resultados_identifica_cada_municipio():
    sessao = SessaoFalsa({"df97012-c0001-e006257-u.json": "df97012-c0001-e006257-u.json"})
    cliente = ClienteTSE(sessao=sessao)
    resumos, candidatos = cliente.resultados(6257, 1, [("df", "97012"), ("df", "00000")])
    assert list(resumos["cd_municipio_tse"]) == ["97012"]
    assert set(candidatos["uf"]) == {"df"}
    assert len(sessao.pedidos) == 2
