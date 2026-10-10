import pandas as pd

from eleicoes.acompanhamento import Acompanhamento
from eleicoes.tse_ao_vivo import Resultado


class ClienteFalso:
    """Simula o TSE: dois municípios de SP; o 2º só começa a apurar na 2ª rodada.
    `falhar` faz o download dos votos de um município falhar uma vez."""

    def __init__(self):
        self.rodada = 0
        self.falhar: set[str] = set()
        self.baixados: list[str] = []

    def andamento(self, eleicao, uf):
        if uf != "sp":
            return None
        apurado_2 = 0 if self.rodada == 0 else 500
        return pd.DataFrame([
            {"uf": "sp", "tp_abrangencia": "uf", "cd_abrangencia": "sp", "dt_totalizacao": None,
             "qt_secoes": 4, "qt_secoes_totalizadas": 1 + (self.rodada > 0), "qt_eleitores": 2000,
             "qt_eleitores_secoes_totalizadas": 1000 + apurado_2},
            {"uf": "sp", "tp_abrangencia": "mun", "cd_abrangencia": "001", "dt_totalizacao": "t1",
             "qt_secoes": 2, "qt_secoes_totalizadas": 1, "qt_eleitores": 1000,
             "qt_eleitores_secoes_totalizadas": 1000},
            {"uf": "sp", "tp_abrangencia": "mun", "cd_abrangencia": "002", "dt_totalizacao": f"t{self.rodada}",
             "qt_secoes": 2, "qt_secoes_totalizadas": int(self.rodada > 0), "qt_eleitores": 1000,
             "qt_eleitores_secoes_totalizadas": apurado_2},
        ])

    def resultado(self, eleicao, cargo, uf="br", municipio=""):
        if municipio in self.falhar:
            self.falhar.discard(municipio)
            return None
        self.baixados.append(municipio)
        votos = {"001": (600, 300), "002": (100, 300), "": (700, 600)}[municipio]
        candidatos = pd.DataFrame({"nr_candidato": ["22", "13"], "qt_votos": list(votos)})
        return Resultado(resumo={"qt_secoes": 4, "qt_secoes_totalizadas": 2}, candidatos=candidatos)


def acompanhamento(cliente):
    prior = pd.DataFrame({"uf": ["SP", "SP"], "cd_municipio_tse": ["001", "002"],
                          "logit_prior": [0.0, 0.0], "taxa_validos": [0.9, 0.9]})
    return Acompanhamento(eleicao=1, cargo=1, nr_a=22, nr_b=13, prior=prior, cliente=cliente,
                          paralelos=1, cenarios=200)


def test_so_baixa_o_que_mudou_e_soma_os_votos():
    cliente = ClienteFalso()
    acomp = acompanhamento(cliente)
    r1 = acomp.rodar_uma_vez()
    assert (r1.qt_a, r1.qt_b) == (600, 300)
    assert r1.pct_secoes == 0.5
    assert cliente.baixados == ["001", ""]          # o município 002 ainda não apurou

    cliente.rodada, cliente.baixados = 1, []
    r2 = acomp.rodar_uma_vez()
    assert cliente.baixados == ["002", ""]           # 001 não mudou: não baixa de novo
    assert (r2.qt_a, r2.qt_b) == (700, 600)
    assert r2.pct_secoes == 0.75
    assert r2.pct_a_oficial == 700 / 1300
    assert len(acomp.tabela_historico()) == 2


def test_falha_no_download_nao_avanca_o_apurado():
    cliente = ClienteFalso()
    acomp = acompanhamento(cliente)
    acomp.rodar_uma_vez()
    cliente.rodada = 1
    cliente.falhar = {"002"}
    r = acomp.rodar_uma_vez()
    assert r.pct_secoes == 0.5                       # o eleitorado de 002 só conta junto com os votos
    r = acomp.rodar_uma_vez()                        # na rodada seguinte o download funciona
    assert r.pct_secoes == 0.75 and r.qt_b == 600


def test_antes_de_publicar_nao_ha_rodada():
    cliente = ClienteFalso()
    cliente.andamento = lambda eleicao, uf: None
    acomp = acompanhamento(cliente)
    assert acomp.rodar_uma_vez() is None
    assert not acomp.publicado
