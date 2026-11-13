"""Gravação e análise da noite: recomeçar de onde parou e comparar com o resultado final."""

import importlib.util
from pathlib import Path

import pandas as pd

from test_acompanhamento import ClienteFalso, acompanhamento

RAIZ = Path(__file__).resolve().parents[1]


def _carregar(nome: str):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


gravar = _carregar("gravar_noite")
analisar = _carregar("analisar_noite")


def test_restaurar_so_baixa_o_que_mudou(tmp_path):
    cliente = ClienteFalso()
    primeiro = acompanhamento(cliente)
    primeiro.rodar_uma_vez()                         # 001 apurado; 002 ainda não
    salvo = tmp_path / "municipios.parquet"
    primeiro.estado().to_parquet(salvo, index=False)

    cliente.rodada, cliente.baixados = 1, []         # 002 começa a apurar
    segundo = acompanhamento(cliente)
    assert gravar.restaurar(segundo, salvo) == 1     # 001 continua igual: não precisa baixar de novo
    r = segundo.rodar_uma_vez()
    assert cliente.baixados == ["002", ""]
    assert (r.qt_a, r.qt_b) == (700, 600) and r.pct_secoes == 0.75


def test_restaurar_baixa_de_novo_municipio_sem_votos(tmp_path):
    cliente = ClienteFalso()
    primeiro = acompanhamento(cliente)
    primeiro.rodar_uma_vez()
    primeiro.municipios[("sp", "001")].update(qt_a=0, qt_b=0)   # salvo zerado (arquivo atrasado no cache)
    salvo = tmp_path / "municipios.parquet"
    primeiro.estado().to_parquet(salvo, index=False)

    cliente.baixados = []
    segundo = acompanhamento(cliente)
    assert gravar.restaurar(segundo, salvo) == 0
    r = segundo.rodar_uma_vez()
    assert cliente.baixados == ["001", ""] and r.qt_a == 600


def test_noite_compara_com_o_resultado_final():
    gravacao = pd.DataFrame({
        "momento": ["2026-10-25T18:30:00-03:00", "2026-10-25T19:10:00-03:00",
                    "2026-10-25T19:11:00-03:00", "2026-10-25T19:12:00-03:00"],
        "pct_secoes": [0.0, 0.02, 0.06, 0.08],
        "pct_secoes_oficial": [0.0025, 0.03, None, 0.09],
        "pct_a_oficial": [0.42, 0.47, None, 0.49],
        "pct_a_mediana": [0.47, 0.46, 0.475, 0.485],
        "pct_a_inferior": [0.44, 0.44, 0.47, 0.475],
        "pct_a_superior": [0.50, 0.48, 0.479, 0.495],
        "prob_a_vence": [0.2, 0.0, 0.0, 0.01],
        "falhas": [0, 0, 30, 0],
    })
    r = analisar.noite(gravacao, {"qt_a": 48, "qt_b": 52, "pct_secoes": 1.0})
    assert list(r["momento"].dt.strftime("%H:%M")) == ["19:10", "19:11", "19:12"]   # antes das 19h: divulgação parada
    assert r["pct_a_apurado"].tolist() == [0.47, 0.47, 0.49]     # o arquivo que não veio repete o último placar
    assert not r["placar_recebido"].iloc[1]
    assert pd.isna(r["pct_a_mediana"].iloc[0])                    # menos de 5% lido: projeção não publicada
    assert round(r["erro_projecao_pp"].iloc[1], 6) == -0.5
    assert r["final_no_intervalo"].tolist()[1:] == [False, True]
