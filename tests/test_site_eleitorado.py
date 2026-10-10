"""Testes das contas da página "Eleitorado" (faixas etárias, voto facultativo,
escolha dos CSVs do zip, agregação dos CSVs do TSE e municípios com mais
eleitores do que habitantes). Sem rede: os CSVs são pequenos e escritos aqui."""

import importlib.util
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from eleicoes.eleitorado import (
    codigo_municipio_tse,
    faixa_abstencao,
    faixa_piramide,
    grupo_facultativo,
    idade_inicial,
    mais_eleitores_que_habitantes,
    tabela_escolaridade,
    tabela_faixas,
    voto_facultativo,
)

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("site_eleitorado", RAIZ / "scripts" / "site_eleitorado.py")
site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(site)

# Todos os códigos de faixa etária que aparecem nos arquivos do TSE de 2010 a 2026.
CODIGOS_TSE = [-3, 1600, 1700, 1800, 1900, 2000, 2124, 2529, 3034, 3539, 4044, 4549, 5054, 5559, 6064,
               6569, 7074, 7579, 8084, 8589, 9094, 9599, 9999]


def test_idade_inicial_le_os_codigos_do_tse():
    assert idade_inicial(1600) == 16
    assert idade_inicial("2124") == 21
    assert idade_inicial(9599) == 95
    assert idade_inicial(9999) == 100  # "100 anos ou mais"
    assert idade_inicial(-3) is None   # "Inválida"
    assert idade_inicial(-1) is None
    assert idade_inicial("#NULO#") is None


def test_piramide_tem_faixas_de_5_anos_sem_buraco_nem_sobreposicao():
    faixas = tabela_faixas(CODIGOS_TSE).dropna(subset=["idade"])
    # cada idade inicial cai numa só faixa, e as faixas seguem a ordem das idades
    ordem = faixas.groupby("faixa_piramide")["ordem_piramide"].nunique()
    assert (ordem == 1).all()
    assert faixas["ordem_piramide"].is_monotonic_increasing
    rotulos = faixas.drop_duplicates("ordem_piramide").sort_values("ordem_piramide")["faixa_piramide"].tolist()
    assert rotulos[0] == "16 a 19" and rotulos[1] == "20 a 24" and rotulos[-1] == "90 ou mais"
    assert len(rotulos) == 16
    # "20 anos" e "21 a 24 anos" do TSE formam juntos a faixa de 20 a 24
    assert faixa_piramide(20) == faixa_piramide(21) == (1, "20 a 24")
    assert faixa_piramide(85) == (14, "85 a 89")
    assert faixa_piramide(None) is None


def test_abstencao_separa_as_idades_de_voto_facultativo():
    assert faixa_abstencao(16) == (0, "16 anos")
    assert faixa_abstencao(17) == (1, "17 anos")
    assert faixa_abstencao(18) == faixa_abstencao(20) == (2, "18 a 20")
    assert faixa_abstencao(21) == (3, "21 a 24")
    assert faixa_abstencao(65) == (12, "65 a 69")
    assert faixa_abstencao(70) == (13, "70 a 74")
    assert faixa_abstencao(95) == faixa_abstencao(100) == (17, "90 ou mais")
    # nenhuma faixa mistura voto obrigatório e facultativo
    faixas = tabela_faixas(CODIGOS_TSE).dropna(subset=["idade"])
    assert (faixas.groupby("faixa_abstencao")["facultativo"].nunique() == 1).all()


@pytest.mark.parametrize("idade, facultativo, grupo", [
    (16, True, "16 e 17 anos"), (17, True, "16 e 17 anos"), (18, False, None),
    (65, False, None), (70, True, "70 anos ou mais"), (100, True, "70 anos ou mais"), (None, None, None),
])
def test_voto_facultativo(idade, facultativo, grupo):
    assert voto_facultativo(idade) is facultativo
    assert grupo_facultativo(idade) == grupo


def test_analfabeto_tem_voto_facultativo_e_nao_informado_fica_no_fim():
    tabela = tabela_escolaridade().set_index("cd_escolaridade")
    assert tabela.loc[1, "facultativo"] and not tabela.loc[[2, 3, 8], "facultativo"].any()
    assert tabela["ordem"].idxmax() == 0
    assert tabela.loc[8, "escolaridade_tse"] == "Superior completo"


def test_codigo_municipio_tse_padroniza_com_5_digitos():
    assert codigo_municipio_tse("3000") == "03000"   # 2022 grava sem o zero
    assert codigo_municipio_tse("03018") == "03018"  # 2026 grava com o zero
    assert codigo_municipio_tse(97012) == "97012"


def test_mais_eleitores_que_habitantes():
    municipios = pd.DataFrame({
        "nm_municipio": ["A", "B", "C", "D", "Exterior"],
        "qt_eleitores": [150, 80, 100, 300, 500],
        "populacao": [100, 100, 100, 200, None],
    })
    acima = mais_eleitores_que_habitantes(municipios)
    # C tem eleitores = habitantes: não entra; sem população (exterior): não entra
    assert acima["nm_municipio"].tolist() == ["A", "D"]
    assert acima["eleitores_por_100_hab"].tolist() == [150.0, 150.0]


def test_escolhe_os_csvs_de_cada_uf_ou_o_nacional():
    por_uf = [f"perfil_eleitorado_2026_{uf}.csv" for uf in site.UFS]
    assert site.escolher_membros(por_uf + ["perfil_eleitorado_2026_BRASIL.csv", "leiame.pdf"]) == por_uf
    # comparecimento de 2022: faltam DF e exterior entre os arquivos por UF -> usa o nacional
    incompleto = [n for n in por_uf if not n.endswith(("_DF.csv", "_ZZ.csv"))]
    assert site.escolher_membros(incompleto + ["x_2022_BRASIL.csv"]) == ["x_2022_BRASIL.csv"]
    # anos antigos: um só CSV com o país inteiro
    assert site.escolher_membros(["LEIAME.pdf", "perfil_eleitorado_2018.csv"]) == ["perfil_eleitorado_2018.csv"]
    with pytest.raises(RuntimeError):
        site.escolher_membros(["leiame.pdf"])


def escrever_csv(caminho: Path, cabecalho: list[str], linhas: list[list]) -> Path:
    texto = "\n".join(";".join(f'"{v}"' for v in linha) for linha in [cabecalho, *linhas])
    caminho.write_bytes(texto.encode("latin-1"))
    return caminho


def test_agrega_o_perfil_nos_dois_formatos_de_coluna_do_tse(tmp_path):
    comum = ["DT_GERACAO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "CD_GENERO",
             "CD_FAIXA_ETARIA", "DS_FAIXA_ETARIA", "CD_GRAU_ESCOLARIDADE"]
    # 2022 e 2026: AA_ELEICAO e QT_ELEITORES
    novo = escrever_csv(tmp_path / "novo.csv", ["AA_ELEICAO", *comum, "QT_ELEITORES"], [
        [2026, "14/07/2026", "RR", "03018", "BOA VISTA", 1, 4, 1600, "16 anos", 5, 10],
        [2026, "14/07/2026", "RR", "03018", "BOA VISTA", 2, 4, 1600, "16 anos", 5, 7],  # outra zona: soma
        [2026, "14/07/2026", "RR", "03018", "BOA VISTA", 1, 2, 9999, "100 anos ou mais", 1, 3],
    ])
    # 2010 a 2018: ANO_ELEICAO e QT_ELEITORES_PERFIL, faixa com espaços no fim
    antigo = escrever_csv(tmp_path / "antigo.csv", ["ANO_ELEICAO", *comum, "QT_ELEITORES_PERFIL"], [
        [2018, "12/04/2021", "SP", "71072", "SÃO PAULO", 1, 4, 2124, "21 a 24 anos     ", 8, 5],
    ])
    r = duckdb.sql(site.sql_agregar_perfil(novo)).df().sort_values("cd_faixa").reset_index(drop=True)
    assert r["qt_eleitores"].tolist() == [17, 3]
    assert r.loc[0, "ano"] == 2026 and r.loc[0, "uf"] == "RR"
    a = duckdb.sql(site.sql_agregar_perfil(antigo)).df()
    assert a.loc[0, "ano"] == 2018 and a.loc[0, "qt_eleitores"] == 5
    assert a.loc[0, "ds_faixa"] == "21 a 24 anos" and a.loc[0, "nm_municipio"] == "SÃO PAULO"
