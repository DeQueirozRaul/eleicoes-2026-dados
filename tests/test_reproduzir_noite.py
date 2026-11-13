"""A noite refeita com os dados oficiais: o retrato de cada momento tem de somar só o que já tinha sido divulgado."""

import importlib.util
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("reproduzir_noite_2026", RAIZ / "scripts" / "reproduzir_noite_2026.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

T = pd.Timestamp


def conexao():
    con = duckdb.connect()
    # um município com duas zonas; a zona 2 só é totalizada às 19h10
    con.register("zonas_df", pd.DataFrame({"uf": ["SP", "SP"], "cd_municipio_tse": ["00001", "00001"], "zona": [1, 2],
                                           "qt_secoes": [2, 1], "qt_aptos": [200, 100]}))
    con.register("eventos_df", pd.DataFrame({
        "uf": ["SP"] * 3, "cd_municipio_tse": ["00001"] * 3, "zona": [1, 1, 2],
        "momento": [T("2026-10-25 19:01"), T("2026-10-25 19:05"), T("2026-10-25 19:10")],
        "secoes": [1, 2, 1], "aptos": [100, 200, 100], "qt_a": [30, 70, 50], "qt_b": [50, 90, 30]}))
    # três seções; na ordem do 1º turno a última do 2º turno chega primeiro
    con.register("secoes_df", pd.DataFrame({
        "uf": ["SP"] * 3, "cd_municipio_tse": ["00001"] * 3, "zona": [1, 1, 2], "secao": [1, 2, 3],
        "qt_aptos": [100, 100, 100], "qt_a": [30, 40, 50], "qt_b": [50, 40, 30],
        "totalizado_1t": [T("2026-10-04 17:30"), T("2026-10-04 17:20"), T("2026-10-04 17:10")],
        "totalizado_2t": [T("2026-10-25 19:01"), T("2026-10-25 19:05"), T("2026-10-25 19:10")]}))
    con.execute("create table zonas as select * from zonas_df")
    con.execute("create table eventos as select * from eventos_df")
    con.execute("create table secoes as select * from secoes_df")
    return con


def test_retrato_do_historico_soma_o_ultimo_acumulado_de_cada_zona():
    r = R.retratos_historico(conexao(), [T("2026-10-25 19:00"), T("2026-10-25 19:06"), T("2026-10-25 19:30")])
    r = r.set_index("momento")
    assert r.loc[T("2026-10-25 19:00"), "qt_aptos_apurados"] == 0
    assert r.loc[T("2026-10-25 19:06"), ["qt_secoes_apuradas", "qt_a", "qt_b"]].tolist() == [2, 70, 90]
    assert r.loc[T("2026-10-25 19:30"), ["qt_secoes", "qt_secoes_apuradas", "qt_aptos_apurados"]].tolist() == [3, 3, 300]


def test_retrato_por_secao_segue_a_ordem_pedida():
    con = conexao()
    momentos = [T("2026-10-25 19:02"), T("2026-10-25 19:12")]
    real = R.retratos_secoes(con, "totalizado_2t", momentos).set_index("momento")
    assert real.loc[T("2026-10-25 19:02"), "qt_a"] == 30                 # só a seção 1
    ordem_1t = R.retratos_secoes(
        con, "timestamp '2026-10-25 19:00' + (totalizado_1t - timestamp '2026-10-04 17:00')", momentos
    ).set_index("momento")
    assert ordem_1t.loc[T("2026-10-25 19:12"), "qt_a"] == 50             # na ordem do 1º turno, a seção 3 vem antes
    assert real.loc[T("2026-10-25 19:12"), "qt_a"] == ordem_1t.loc[T("2026-10-25 19:12"), "qt_a"] + 70


def test_primeira_secao_compara_com_o_proprio_municipio():
    con = conexao()
    # primeira_secao só olha municípios com 5 seções ou mais: repete as três seções em outras zonas
    con.execute("""insert into secoes select uf, cd_municipio_tse, zona + 10, secao + 10, qt_aptos, qt_a, qt_b,
                   totalizado_1t + interval 1 hour, totalizado_2t + interval 1 hour from secoes""")
    r = R.primeira_secao(con).set_index("ordem")["dif_pp"]
    municipio = (30 + 40 + 50) * 2 / (240 * 2)
    assert round(r["ordem do 2º turno (real)"], 6) == round((30 / 80 - municipio) * 100, 6)
    assert round(r["ordem do 1º turno"], 6) == round((50 / 80 - municipio) * 100, 6)
