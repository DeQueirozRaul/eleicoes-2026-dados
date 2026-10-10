"""Funções puras usadas na página "Eleitorado" (faixas etárias, voto facultativo,
municípios com mais eleitores do que habitantes).

O TSE publica a idade em faixas com um código numérico: 1600 = "16 anos",
2124 = "21 a 24 anos", 2529 = "25 a 29 anos", 9599 = "95 a 99 anos",
9999 = "100 anos ou mais" e códigos negativos (ou "Inválido") para idade sem
informação. Os dois primeiros dígitos são a idade inicial da faixa, exceto em
"100 anos ou mais".
"""

from __future__ import annotations

import pandas as pd

# Idades em que o voto é facultativo (Constituição, art. 14): 16 e 17 anos e 70 anos ou mais.
# Analfabetos também têm voto facultativo, em qualquer idade.
IDADE_OBRIGATORIA = (18, 69)

# Grau de instrução declarado no alistamento: (nome curto para gráficos, nome do TSE).
ESCOLARIDADE = {
    1: ("Analfabeto", "Analfabeto"),
    2: ("Lê e escreve", "Lê e escreve"),
    3: ("Fundamental incompleto", "Ensino fundamental incompleto"),
    4: ("Fundamental completo", "Ensino fundamental completo"),
    5: ("Médio incompleto", "Ensino médio incompleto"),
    6: ("Médio completo", "Ensino médio completo"),
    7: ("Superior incompleto", "Superior incompleto"),
    8: ("Superior completo", "Superior completo"),
    0: ("Não informado", "Não informado"),
}  # na ordem de leitura dos gráficos: do menor ao maior grau, "Não informado" no fim

# Gênero: (nome nos gráficos, nome do TSE).
GENERO = {4: ("Mulheres", "Feminino"), 2: ("Homens", "Masculino"), 0: ("Não informado", "Não informado")}


def idade_inicial(cd_faixa) -> int | None:
    """Idade inicial da faixa do TSE: 1600 -> 16, 2124 -> 21, 9999 -> 100.

    Devolve None para faixa sem informação (código negativo, zero ou fora do padrão)."""
    try:
        cd = int(cd_faixa)
    except (TypeError, ValueError):
        return None
    if cd == 9999 or cd >= 10000:
        return 100
    if cd < 1600 or cd > 9999:
        return None
    return cd // 100


def faixa_piramide(idade: int | None) -> tuple[int, str] | None:
    """Faixas de 5 anos para a pirâmide: (ordem, rótulo).

    A primeira faixa tem só 4 idades (16 a 19), porque o voto começa aos 16;
    a última junta 90 anos ou mais."""
    if idade is None or idade < 16:
        return None
    if idade < 20:
        return 0, "16 a 19"
    if idade >= 90:
        return 15, "90 ou mais"
    inicio = 5 * (idade // 5)
    return (inicio - 15) // 5, f"{inicio} a {inicio + 4}"


def faixa_abstencao(idade: int | None) -> tuple[int, str] | None:
    """Faixas para a abstenção por idade: 16, 17, 18 a 20, 21 a 24, 25 a 29, ...,
    85 a 89 e 90 ou mais. As idades de voto facultativo ficam separadas."""
    if idade is None or idade < 16:
        return None
    if idade in (16, 17):
        return idade - 16, f"{idade} anos"
    if idade < 21:
        return 2, "18 a 20"
    if idade < 25:
        return 3, "21 a 24"
    if idade >= 90:
        return 17, "90 ou mais"
    inicio = 5 * (idade // 5)
    return (inicio - 25) // 5 + 4, f"{inicio} a {inicio + 4}"


def voto_facultativo(idade: int | None) -> bool | None:
    """True para 16 e 17 anos e para 70 anos ou mais; None sem idade."""
    if idade is None:
        return None
    return idade < IDADE_OBRIGATORIA[0] or idade > IDADE_OBRIGATORIA[1]


def grupo_facultativo(idade: int | None) -> str | None:
    """'16 e 17 anos', '70 anos ou mais' ou None (voto obrigatório ou sem idade)."""
    if idade is None:
        return None
    if idade < IDADE_OBRIGATORIA[0]:
        return "16 e 17 anos"
    if idade > IDADE_OBRIGATORIA[1]:
        return "70 anos ou mais"
    return None


def tabela_faixas(codigos) -> pd.DataFrame:
    """Uma linha por código de faixa etária do TSE, com a idade inicial e os
    agrupamentos usados no site (pirâmide, abstenção e voto facultativo)."""
    linhas = []
    for cd in sorted({int(c) for c in codigos}):
        idade = idade_inicial(cd)
        piramide = faixa_piramide(idade) or (None, None)
        abstencao = faixa_abstencao(idade) or (None, None)
        linhas.append({
            "cd_faixa": cd, "idade": idade,
            "ordem_piramide": piramide[0], "faixa_piramide": piramide[1],
            "ordem_abstencao": abstencao[0], "faixa_abstencao": abstencao[1],
            "facultativo": voto_facultativo(idade), "grupo_facultativo": grupo_facultativo(idade),
        })
    tabela = pd.DataFrame(linhas)
    for coluna in ["idade", "ordem_piramide", "ordem_abstencao"]:
        tabela[coluna] = tabela[coluna].astype("Int64")
    tabela["facultativo"] = tabela["facultativo"].astype("boolean")
    return tabela


def tabela_escolaridade() -> pd.DataFrame:
    """Código do TSE -> ordem, nome curto, nome do TSE e se o voto é facultativo
    (analfabetos têm voto facultativo em qualquer idade)."""
    return pd.DataFrame([
        {"cd_escolaridade": cd, "ordem": ordem, "escolaridade": curto, "escolaridade_tse": tse,
         "facultativo": cd == 1}
        for ordem, (cd, (curto, tse)) in enumerate(ESCOLARIDADE.items())
    ])


def tabela_genero() -> pd.DataFrame:
    return pd.DataFrame([{"cd_genero": cd, "ordem": ordem, "genero": nome, "genero_tse": tse}
                         for ordem, (cd, (nome, tse)) in enumerate(GENERO.items())])


def codigo_municipio_tse(codigo) -> str:
    """O TSE grava o código do município ora com zero à esquerda ('03000'), ora sem
    ('3000'). Padroniza com 5 dígitos, como na tabela `municipios` do banco."""
    return str(int(str(codigo).strip())).zfill(5)


def mais_eleitores_que_habitantes(municipios: pd.DataFrame, coluna_populacao: str = "populacao") -> pd.DataFrame:
    """Municípios com mais eleitores do que habitantes.

    Entrada: uma linha por município com `qt_eleitores` e a coluna de população.
    Saída: só os municípios em que eleitores > habitantes, com
    `eleitores_por_100_hab` (100 = um eleitor por habitante), do maior para o menor.
    Municípios sem população (ex.: exterior) ficam de fora."""
    base = municipios.dropna(subset=[coluna_populacao])
    base = base[base[coluna_populacao] > 0]
    acima = base[base["qt_eleitores"] > base[coluna_populacao]].copy()
    acima["eleitores_por_100_hab"] = 100 * acima["qt_eleitores"] / acima[coluna_populacao]
    return acima.sort_values("eleitores_por_100_hab", ascending=False).reset_index(drop=True)


def taxa(parte: float, total: float) -> float | None:
    """parte / total, ou None quando o total é zero."""
    return parte / total if total else None
