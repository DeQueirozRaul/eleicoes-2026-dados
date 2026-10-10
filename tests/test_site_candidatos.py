"""Testes das funções puras das páginas "Perfil dos candidatos" e "Patrimônio
declarado" (scripts/site_candidatos.py), sem rede."""

import pandas as pd
import pytest

from scripts.site_candidatos import (
    AGUARDANDO,
    APLICACOES,
    CRIPTO,
    ELEITO,
    EMPRESAS,
    IMOVEIS,
    NAO_ELEITO,
    OUTROS,
    SEGUNDO_TURNO,
    SEM_TITULO,
    VEICULOS,
    agremiacao,
    categoria_bem,
    chave_pessoa,
    faixa_etaria,
    fatores_ipca,
    idade_na_data,
    indice_ipca,
    ler_sidra,
    mediana_ou_nada,
    situacao_final,
    situacao_json,
    situacao_texto,
    texto_tse,
    titulo_nome_urna,
    valor_reais,
)


@pytest.mark.parametrize("nome, tipo", [
    ("PASTOR JOÃO", "Religioso"),
    ("PR. MARCOS", "Religioso"),
    ("Irmã Lúcia", "Religioso"),
    ("SGT. SILVA", "Policial ou militar"),
    ("SUB TENENTE GOMES", "Policial ou militar"),
    ("TEN CEL ALVES", "Policial ou militar"),
    ("DELEGADA ANA", "Policial ou militar"),
    ("PROFª MARIA", "Professor(a)"),
    ("PROF. JOSÉ", "Professor(a)"),
    ("DRA. CLARA", "Doutor(a)"),
    ("ENFERMEIRA RITA", "Enfermeiro(a) ou médico(a)"),
])
def test_titulo_reconhece_a_primeira_palavra(nome, tipo):
    assert titulo_nome_urna(nome) == tipo


@pytest.mark.parametrize("nome", [
    "JOÃO BISPO",          # sobrenome no fim do nome não conta
    "PRADO",               # começa com "PR", mas é outra palavra
    "DRUMMOND",
    "SUB PREFEITO ZÉ",     # "SUB" só conta antes de TENENTE/OFICIAL
    "",
    None,
])
def test_titulo_ignora_falsos_positivos(nome):
    assert titulo_nome_urna(nome) == SEM_TITULO


def test_situacao_final_de_2018_e_2022():
    assert situacao_final("ELEITO POR QP", None) == ELEITO
    assert situacao_final("ELEITO POR MÉDIA", None) == ELEITO
    assert situacao_final("SUPLENTE", None) == NAO_ELEITO
    assert situacao_final("NÃO ELEITO", None) == NAO_ELEITO
    # quem foi ao 2º turno conta pelo resultado do 2º turno
    assert situacao_final("2º TURNO", "ELEITO") == ELEITO
    assert situacao_final("2º TURNO", "NÃO ELEITO") == NAO_ELEITO
    assert situacao_final("2º TURNO", None) == SEGUNDO_TURNO
    # candidatura fora da urna não tem totalização
    assert situacao_final(None, None) is None
    assert situacao_final(float("nan"), None) is None


def test_situacao_dos_arquivos_de_resultado_de_2026():
    assert situacao_json("Eleito por QP") == ELEITO
    assert situacao_json("Eleito por média") == ELEITO
    assert situacao_json("2º turno") == SEGUNDO_TURNO
    assert situacao_json("Suplente") == NAO_ELEITO
    assert situacao_json("Não eleito") == NAO_ELEITO
    assert situacao_json("") == AGUARDANDO       # totalização ainda não final


def test_situacao_texto_para_o_power_bi():
    assert situacao_texto(2022, "ELEITO POR QP", None, None) == "Eleito por QP"
    assert situacao_texto(2022, "2º TURNO", "NÃO ELEITO", None) == "Não eleito (2º turno)"
    assert situacao_texto(2018, "SUPLENTE", None, None) == "Suplente"
    assert situacao_texto(2026, "#NULO", None, "2º turno") == "2º turno"
    assert situacao_texto(2026, None, None, "") == AGUARDANDO


def test_texto_tse_padroniza_e_marca_sem_informacao():
    assert texto_tse("ENSINO MÉDIO COMPLETO") == "Ensino médio completo"
    assert texto_tse("LÊ E ESCREVE") == "Lê e escreve"
    assert texto_tse("NÃO DIVULGÁVEL") == "Não informado"
    assert texto_tse(None) == "Não informado"


def test_idade_em_anos_completos_no_dia_da_eleicao():
    nascimento = pd.Series(["04/10/1980", "05/10/1980", "03/10/1980", "29/02/1960", "data ruim"])
    idade = idade_na_data(nascimento, "2026-10-04")
    assert idade.tolist()[:4] == [46, 45, 46, 66]
    assert pd.isna(idade.iloc[4])


def test_faixa_etaria_nos_limites():
    faixas = faixa_etaria(pd.Series([18, 29, 30, 69, 70, 95, float("nan"), 17]))
    assert faixas.tolist() == ["18 a 29 anos", "18 a 29 anos", "30 a 39 anos", "60 a 69 anos",
                               "70 anos ou mais", "70 anos ou mais", "Não informado", "Não informado"]


def test_agremiacao_junta_partidos_da_federacao():
    assert agremiacao("PT", "13-PT/65-PC do B/43-PV") == "PT/PC do B/PV (federação)"
    assert agremiacao("PSDB", "PSDB/CIDADANIA") == "PSDB/CIDADANIA (federação)"
    assert agremiacao("NOVO", None) == "NOVO"
    assert agremiacao("NOVO", float("nan")) == "NOVO"


def test_categoria_bem():
    assert categoria_bem(11, "APARTAMENTO NO CENTRO") == IMOVEIS
    assert categoria_bem(21, "MOTO YAMAHA CRYPTON") == VEICULOS      # veículo nunca vira cripto
    assert categoria_bem(32, "QUOTAS DA EMPRESA BTC LTDA") == EMPRESAS
    assert categoria_bem(45, "CDB BANCO X") == APLICACOES
    assert categoria_bem(97, "VGBL") == APLICACOES
    assert categoria_bem(49, "Investimento em criptomoedas") == CRIPTO
    assert categoria_bem(99, "0,5 BTC NA CORRETORA") == CRIPTO
    assert categoria_bem(99, "USDT ADQUIRIDOS") == CRIPTO
    assert categoria_bem(99, "DIREITO DE USO DE LINHA") == OUTROS
    assert categoria_bem(51, "EMPRÉSTIMO A TERCEIRO") == OUTROS
    assert categoria_bem(25, None) == OUTROS


def test_valor_reais_com_virgula_decimal():
    valores = valor_reais(pd.Series(["29000,00", "1.234.567,89", "", None]))
    assert valores.tolist() == [29000.0, 1234567.89, 0.0, 0.0]


def test_ipca_acumula_e_leva_agosto_para_a_referencia():
    serie = [{"data": "01/08/2018", "valor": "0.00"}, {"data": "01/09/2018", "valor": "10.00"},
             {"data": "01/08/2022", "valor": "10.00"}, {"data": "01/08/2026", "valor": "0.00"}]
    indice = indice_ipca(serie)
    assert indice.iloc[-1] == pytest.approx(1.21)
    fatores, referencia = fatores_ipca(indice, [2018, 2022, 2026])
    assert referencia == pd.Timestamp(2026, 8, 1)
    assert fatores[2026] == pytest.approx(1.0)
    assert fatores[2022] == pytest.approx(1.0)        # nada de inflação depois de ago/2022
    assert fatores[2018] == pytest.approx(1.21)


def test_ipca_usa_o_ultimo_mes_se_agosto_ainda_nao_saiu():
    serie = [{"data": "01/08/2022", "valor": "0.00"}, {"data": "01/07/2026", "valor": "5.00"}]
    fatores, referencia = fatores_ipca(indice_ipca(serie), [2022, 2026])
    assert referencia == pd.Timestamp(2026, 7, 1)
    assert fatores[2026] == pytest.approx(1.0)
    assert fatores[2022] == pytest.approx(1.05)


def test_chave_pessoa_usa_cpf_e_cai_para_nome_e_nascimento():
    assert chave_pessoa("01234567890", "ANA", "01/01/1980") == "cpf:01234567890"
    assert chave_pessoa("-4", "Ana  Lúcia", "01/01/1980") == "nome:ANA LUCIA|01/01/1980"
    assert chave_pessoa(None, "ANA", None) is None


def test_ler_sidra_acha_a_coluna_da_classificacao():
    resposta = [
        {"V": "Valor", "D4N": "Nível de instrução", "D6N": "Sexo"},
        {"V": "73667167", "D4N": "Total", "D6N": "Homens"},
        {"V": "80642321", "D4N": "Total", "D6N": "Mulheres"},
    ]
    tabela = ler_sidra(resposta, "Sexo")
    assert tabela["categoria_ibge"].tolist() == ["Homens", "Mulheres"]
    assert tabela["pessoas"].sum() == 154309488


def test_mediana_so_para_grupos_grandes():
    assert mediana_ou_nada(pd.Series(range(10)), 10) == 4.5
    assert pd.isna(mediana_ou_nada(pd.Series([1, 2, 3]), 10))
