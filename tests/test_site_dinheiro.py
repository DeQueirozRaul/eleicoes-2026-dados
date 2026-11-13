"""Dinheiro de campanha: nada contado duas vezes e as partes do fundo por grupo."""

import importlib.util
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("site_dinheiro", RAIZ / "scripts" / "site_dinheiro.py")
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)


def test_para_utf8_tira_bytes_nulos_e_converte(tmp_path):
    csv = tmp_path / "x.csv"
    csv.write_bytes('"A";"B"\n"Eleição";"1"\x00\n'.encode("latin-1"))
    D.para_utf8(csv)
    assert csv.read_text(encoding="utf-8") == '"A";"B"\n"Eleição";"1"\n'


def test_fundo_por_grupo_divide_o_fundo_recebido_do_partido():
    con = duckdb.connect()
    con.register("r", pd.DataFrame({
        "sq_candidato": ["1", "2", "3", "3"],
        "categoria": ["Fundo eleitoral"] * 4,
        "origem": ["Recursos de partido político"] * 3 + ["Recursos de outros candidatos"],
        "valor": [300.0, 700.0, 0.0, 999.0],
    }))
    con.execute("create table receitas as select * from r")
    cand = pd.DataFrame({"sq_candidato": ["1", "2", "3", "4"], "sg_partido": ["X"] * 4,
                         "ds_genero": ["Feminino", "Masculino", "Feminino", "Masculino"],
                         "ds_cor_raca": ["Parda", "Branca", "Preta", "Branca"],
                         "cargo": ["Deputado Federal"] * 4, "uf": ["SP"] * 4, "eleito": [False] * 4})
    f = D.fundo_por_grupo(con, cand).set_index("sg_partido")
    x = f.loc["X"]
    assert x["fundo"] == 1000                       # o repasse de outro candidato não conta
    assert x["parte_candidatas_mulheres"] == 0.5
    assert x["parte_fundo_mulheres"] == 0.3
    assert x["parte_fundo_negros"] == 0.3


def test_custo_por_voto_e_faixas():
    con = duckdb.connect()
    n = 20
    con.register("d", pd.DataFrame({"sq_candidato": [str(i) for i in range(n)], "valor": [1000.0 * i for i in range(n)]}))
    con.execute("create table despesas as select * from d")
    cand = pd.DataFrame({"sq_candidato": [str(i) for i in range(n)], "cargo": ["Deputado Federal"] * n,
                         "eleito": [i >= 18 for i in range(n)], "sg_partido": ["X"] * n,
                         "ds_genero": ["Feminino"] * n, "ds_cor_raca": ["Parda"] * n, "uf": ["SP"] * n})
    votos = pd.DataFrame({"sq_candidato": [str(i) for i in range(n)], "votos": [100] * n})
    grupos, faixas = D.custo_por_voto(con, cand, votos)
    eleitos = grupos.set_index("grupo").loc["Eleitos"]
    assert eleitos["mediana_custo_voto"] == (18000 + 19000) / 2 / 100
    assert len(faixas) == 10 and faixas.iloc[-1]["parte_eleitos"] == 1.0 and faixas.iloc[0]["parte_eleitos"] == 0.0
