"""De onde vieram os eleitores de cada candidato, e para onde devem ir no 2º turno.

Inferência ecológica (regressão de Goodman com restrições): só existem os
totais por município, nunca o voto de cada pessoa. Mas, com 5.500 municípios,
dá para estimar a "matriz de transição" entre duas votações:

    fração do eleitorado do município i que escolheu a opção k agora
        ≈ Σ_r  fração que escolheu r no 2º turno anterior  ×  P[r, k]

P[r, k] é a parte dos eleitores da opção r (ex.: quem votou no finalista do
PT no 2º turno anterior) que escolheu a opção k agora. Cada linha de P soma 1 e
todos os valores ficam entre 0 e 1. A matriz é estimada separadamente por
região, porque o comportamento muda pelo país.

Com P, a regra de Bayes diz de onde vieram os eleitores de cada candidato
eliminado (o "lado" deles no 2º turno anterior), em cada município.
É a "tendência" usada nos cenários de transferência.

Limitação conhecida: a inferência ecológica supõe que eleitores de um mesmo
grupo se comportam de modo parecido dentro da região. Os resultados são
estimativas, e a validação nas eleições passadas mostra o quanto erram.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

LADOS = ["lado_A", "lado_B", "sem_lado"]
NAO_VALIDOS = ["BRANCO_NULO", "ABSTENCAO"]
CORTE_CANDIDATO = 0.01   # eliminados com menos de 1% no país entram juntos em "OUTROS"


def estimar_transicoes(X: np.ndarray, Y: np.ndarray, pesos: np.ndarray,
                       penalidade: float = 1e3) -> np.ndarray:
    """Matriz P (R x K) que minimiza Σ_i peso_i ||Y_i - X_i P||², com 0 <= P <= 1
    e cada linha somando 1 (imposto com uma penalidade alta)."""
    n, R = X.shape
    K = Y.shape[1]
    sw = np.sqrt(pesos / pesos.mean())
    A = np.zeros((n * K + R, R * K))
    b = np.zeros(n * K + R)
    for k in range(K):
        A[k * n:(k + 1) * n, k::K] = X * sw[:, None]
        b[k * n:(k + 1) * n] = Y[:, k] * sw
    for r in range(R):
        A[n * K + r, r * K:(r + 1) * K] = penalidade
        b[n * K + r] = penalidade
    return lsq_linear(A, b, bounds=(0, 1), lsmr_tol="auto").x.reshape(R, K)


def lados_dos_finalistas(finalistas: pd.DataFrame, ano: int, ano_anterior: int) -> dict[int, str]:
    """Liga os finalistas do 2º turno anterior aos lados A e B do atual.

    Mesmo partido -> mesmo lado; se nenhum partido coincidir para um deles, o
    que sobrar vai para o lado que sobrou."""
    atual = finalistas[finalistas["ano"] == ano].set_index("finalista")
    anterior = finalistas[finalistas["ano"] == ano_anterior]
    lados = {}
    for _, f in anterior.iterrows():
        for lado in ("A", "B"):
            if f["sg_partido"] == atual.loc[lado, "sg_partido"]:
                lados[int(f["nr_candidato"])] = f"lado_{lado}"
    restantes_ant = [int(n) for n in anterior["nr_candidato"] if int(n) not in lados]
    restantes_lado = [f"lado_{l}" for l in ("A", "B") if f"lado_{l}" not in lados.values()]
    if len(restantes_ant) == 1 and len(restantes_lado) == 1:
        lados[restantes_ant[0]] = restantes_lado[0]
    if len(lados) != 2:
        raise ValueError(f"não deu para ligar os finalistas de {ano_anterior} aos de {ano}")
    return lados


def montar_matrizes(composicao: pd.DataFrame, finalistas: pd.DataFrame, regioes: pd.DataFrame,
                    ano: int, ano_anterior: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Matrizes de contagens por município: X (2º turno anterior, por lado) e
    Y (1º turno atual, por candidato). Só municípios brasileiros presentes nos dois anos."""
    lados = lados_dos_finalistas(finalistas, ano, ano_anterior)

    ant = composicao[(composicao["ano"] == ano_anterior) & (composicao["turno"] == 2)].copy()
    ant["categoria"] = ant["opcao"].map(lambda o: lados.get(int(o), "sem_lado") if o.isdigit() else "sem_lado")
    X = ant.pivot_table(index=["uf", "cd_municipio_tse"], columns="categoria", values="qt",
                        aggfunc="sum", fill_value=0).reindex(columns=LADOS, fill_value=0)

    atual = composicao[(composicao["ano"] == ano) & (composicao["turno"] == 1)].copy()
    fin = finalistas[finalistas["ano"] == ano].set_index("nr_candidato")["finalista"]
    total_cand = atual[atual["opcao"].str.isdigit()].groupby("opcao")["qt"].sum()
    validos = total_cand.sum()

    def categoria(opcao: str) -> str:
        if not opcao.isdigit():
            return opcao
        if int(opcao) in fin.index:
            return fin[int(opcao)]
        return opcao if total_cand[opcao] / validos >= CORTE_CANDIDATO else "OUTROS"

    atual["categoria"] = atual["opcao"].map(categoria)
    Y = atual.pivot_table(index=["uf", "cd_municipio_tse"], columns="categoria", values="qt",
                          aggfunc="sum", fill_value=0)
    eliminados = sorted([c for c in Y.columns if c not in ("A", "B", "OUTROS", *NAO_VALIDOS)],
                        key=lambda c: -Y[c].sum())
    Y = Y[["A", "B", *eliminados, *(["OUTROS"] if "OUTROS" in Y.columns else []), *NAO_VALIDOS]]

    comuns = X.index.intersection(Y.index)
    comuns = comuns[~comuns.get_level_values("uf").isin(["ZZ", "VT"])]
    X, Y = X.loc[comuns], Y.loc[comuns]
    regiao = regioes.set_index(["uf", "cd_municipio_tse"])["regiao"]
    X["regiao"] = Y["regiao"] = regiao.reindex(comuns).to_numpy()
    return X, Y


def transicoes_por_regiao(X: pd.DataFrame, Y: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Estima P separadamente para cada região."""
    resultado = {}
    cols_x = [c for c in X.columns if c != "regiao"]
    cols_y = [c for c in Y.columns if c != "regiao"]
    for regiao in sorted(X["regiao"].dropna().unique()):
        m = (X["regiao"] == regiao).to_numpy()
        xa = X.loc[m, cols_x].to_numpy(float)
        ya = Y.loc[m, cols_y].to_numpy(float)
        tot_x = xa.sum(axis=1, keepdims=True)
        tot_y = ya.sum(axis=1, keepdims=True)
        ok = (tot_x[:, 0] > 0) & (tot_y[:, 0] > 0)
        P = estimar_transicoes(xa[ok] / tot_x[ok], ya[ok] / tot_y[ok], tot_y[ok, 0])
        resultado[regiao] = pd.DataFrame(P, index=cols_x, columns=cols_y)
    return resultado


def origem_dos_eleitores(X: pd.DataFrame, Y: pd.DataFrame,
                         transicoes: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Para cada município e cada opção do 1º turno atual, quantos eleitores
    vieram de cada lado do 2º turno anterior (regra de Bayes, ajustada para
    somar exatamente os votos observados).

    Devolve uma tabela longa: uf, cd_municipio_tse, regiao, categoria, origem, qt.
    """
    partes = []
    cols_x = [c for c in X.columns if c != "regiao"]
    cols_y = [c for c in Y.columns if c != "regiao"]
    for regiao, P in transicoes.items():
        m = (X["regiao"] == regiao).to_numpy()
        xa = X.loc[m, cols_x].to_numpy(float)
        xa = xa / np.maximum(xa.sum(axis=1, keepdims=True), 1)
        ya = Y.loc[m, cols_y].to_numpy(float)
        Pm = P.loc[cols_x, cols_y].to_numpy()
        conjunta = xa[:, :, None] * Pm[None, :, :]               # município x origem x opção
        prob = conjunta / np.maximum(conjunta.sum(axis=1, keepdims=True), 1e-12)
        contagem = prob * ya[:, None, :]
        idx = Y.index[m]
        for j, origem in enumerate(cols_x):
            df = pd.DataFrame(contagem[:, j, :], index=idx, columns=cols_y).stack().rename("qt").reset_index()
            df.columns = ["uf", "cd_municipio_tse", "categoria", "qt"]
            partes.append(df.assign(origem=origem, regiao=regiao))
    return pd.concat(partes, ignore_index=True)


# ---------------------------------------------------------------------------
# Transferência para o 2º turno
# ---------------------------------------------------------------------------

def fontes_por_municipio(origem: pd.DataFrame) -> pd.DataFrame:
    """Resume, por município, os votos dos finalistas no 1º turno e, para os
    eleitores dos eliminados (E) e dos que não votaram válido (N), de que lado
    do 2º turno anterior eles vieram (sufixos _A, _B e _S = sem lado)."""
    o = origem.copy()
    o["grupo"] = np.where(o["categoria"].isin(["A", "B"]), o["categoria"],
                          np.where(o["categoria"].isin(NAO_VALIDOS), "N", "E"))
    sufixo = {"lado_A": "A", "lado_B": "B", "sem_lado": "S"}
    o["coluna"] = np.where(o["grupo"].isin(["A", "B"]), o["grupo"] + "1",
                           o["grupo"] + "_" + o["origem"].map(sufixo))
    return o.pivot_table(index=["uf", "cd_municipio_tse", "regiao"], columns="coluna",
                         values="qt", aggfunc="sum", fill_value=0).reset_index()


PARAMETROS = ["fidelidade", "troca", "sem_lado", "volta_nv", "desistencia"]
LIMITES = ([0, 0, 0, 0, 0], [1, 1, 0.5, 1, 0.3])


def _desenho(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Ganho de A e de B entre os turnos como combinação dos parâmetros:

        ganho_A = fidelidade·E_A + troca·E_B + sem_lado·E_S + volta_nv·N_A - desistencia·A1
        ganho_B = fidelidade·E_B + troca·E_A + sem_lado·E_S + volta_nv·N_B - desistencia·B1

    E_A = eleitores dos eliminados que vieram do lado de A no 2º turno anterior
    (E_B e E_S idem para o lado B e para quem não tinha lado); N_A e N_B = quem
    não votou válido no 1º turno, por lado de origem; desistencia = parte dos
    eleitores dos finalistas que não volta para votar no 2º turno.
    """
    ga = np.column_stack([f["E_A"], f["E_B"], f["E_S"], f["N_A"], -f["A1"]])
    gb = np.column_stack([f["E_B"], f["E_A"], f["E_S"], f["N_B"], -f["B1"]])
    return ga, gb


def ajustar_transferencia(f: pd.DataFrame) -> dict[str, float]:
    """Estima os parâmetros de transferência de uma eleição já realizada, por
    mínimos quadrados nas contagens de votos de cada município (dividindo pela
    raiz do eleitorado, para que municípios grandes não dominem sozinhos)."""
    ga, gb = _desenho(f)
    tot = f[[c for c in f.columns if c[:2] in ("A1", "B1", "E_", "N_")]].sum(axis=1).to_numpy(float)
    sw = 1 / np.sqrt(tot)
    A = np.vstack([ga * sw[:, None], gb * sw[:, None]])
    b = np.concatenate([(f["A2"] - f["A1"]).to_numpy() * sw, (f["B2"] - f["B1"]).to_numpy() * sw])
    x = lsq_linear(A, b, bounds=LIMITES).x
    return dict(zip(PARAMETROS, map(float, x)))


def prever_transferencia(f: pd.DataFrame, parametros: dict[str, float]) -> pd.DataFrame:
    """Votos previstos de A e B no 2º turno em cada município."""
    ga, gb = _desenho(f)
    p = np.array([parametros[k] for k in PARAMETROS])
    return f.assign(A2_prev=f["A1"] + ga @ p, B2_prev=f["B1"] + gb @ p)


def cenario(f: pd.DataFrame, fidelidade: float, troca: float, sem_lado: float = 0.35) -> float:
    """% de A no 2º turno se os eleitores dos eliminados se comportarem assim:
    `fidelidade` vai para o finalista do lado em que votaram no 2º turno anterior,
    `troca` vai para o outro, e o resto não vota válido; quem não tinha lado
    vai `sem_lado` para cada finalista. Eleitores dos finalistas repetem o voto."""
    p = prever_transferencia(f, {"fidelidade": fidelidade, "troca": troca, "sem_lado": sem_lado,
                                 "volta_nv": 0.0, "desistencia": 0.0})
    return float(p["A2_prev"].sum() / (p["A2_prev"].sum() + p["B2_prev"].sum()))
