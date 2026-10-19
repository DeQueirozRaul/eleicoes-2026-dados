"""O coletor de linha de comando não pode parar nem perder municípios quando o TSE
recusa um arquivo no meio da noite."""

import importlib.util
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("coletar_ao_vivo", RAIZ / "scripts" / "coletar_ao_vivo.py")
coletar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coletar)


class ClienteFalso:
    def __init__(self):
        self.recusar_andamento: set[str] = set()
        self.recusar_resultado: set[str] = set()
        self.pedidos: list[str] = []

    def andamento(self, eleicao, uf):
        if uf in self.recusar_andamento:
            raise requests.HTTPError("403 Forbidden")
        return pd.DataFrame([
            {"uf": uf, "tp_abrangencia": "mun", "cd_abrangencia": f"{uf}1", "qt_secoes_totalizadas": 1,
             "dt_totalizacao": "t1"},
        ])

    def resultados(self, eleicao, cargo, alvos, paralelos=1):
        ok = [(uf, mun) for uf, mun in alvos if mun not in self.recusar_resultado]
        self.pedidos += [mun for _, mun in alvos if mun]
        resumos = pd.DataFrame([{"uf": uf, "cd_municipio_tse": mun} for uf, mun in ok])
        return resumos, pd.DataFrame()


def test_municipio_recusado_e_pedido_de_novo():
    cliente = ClienteFalso()
    cliente.recusar_resultado = {"sp1"}
    _, _, _, estado = coletar.varrer(cliente, 1, 1, ["sp", "rj"], {}, 1)
    assert ("sp", "sp1") not in estado and ("rj", "rj1") in estado
    cliente.recusar_resultado, cliente.pedidos = set(), []
    _, _, _, estado = coletar.varrer(cliente, 1, 1, ["sp", "rj"], estado, 1)
    assert cliente.pedidos == ["sp1"]                 # só o que faltou é pedido de novo
    assert ("sp", "sp1") in estado


def test_uf_recusada_nao_derruba_a_varredura():
    cliente = ClienteFalso()
    _, _, _, estado = coletar.varrer(cliente, 1, 1, ["sp", "rj"], {}, 1)
    cliente.recusar_andamento, cliente.pedidos = {"sp"}, []
    andamento, _, _, estado = coletar.varrer(cliente, 1, 1, ["sp", "rj"], estado, 1)
    assert set(andamento["uf"]) == {"rj"}
    assert ("sp", "sp1") in estado                    # SP continua como estava
    assert cliente.pedidos == []                      # nada mudou: nenhum município baixado de novo
