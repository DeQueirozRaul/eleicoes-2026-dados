"""Votos para Governador anulados por quem digitou o número de um candidato a
Presidente, nas disputas mais apertadas de 2022 e 2026.

Passos:
1. Para cada disputa de Governador (2022 1º e 2º turnos, 2026 1º turno), calcula
   quantos votos bastariam para mudar o resultado: virar o 2º turno, vencer no
   1º turno, forçar um 2º turno ou trocar quem vai ao 2º turno.
2. Seleciona as disputas em que isso é menos de --limite dos votos válidos.
3. Lê o RDV de todas as urnas desses estados (só os bytes dos arquivos .rdv) e
   conta os votos nulos para Governador por número digitado. Confere os votos
   nominais com o resultado oficial.
4. Compara os nulos com número de presidenciável com a margem decisiva, e
   refaz o resultado sob a "hipótese da coligação": quem digitou o número de um
   presidenciável queria votar no candidato a Governador cuja coligação inclui
   o partido desse presidenciável. É uma hipótese: o RDV não diz a intenção.

Antes: scripts/montar_base.py e scripts/baixar_governador.py.
Saídas em dados/nulos/. Leva ~1 hora na primeira vez (as contagens ficam
guardadas e não são baixadas de novo).
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.rdv import VALIDOS_OU_BRANCOS, ZipRemotoRDV  # noqa: E402
from eleicoes.tse_ao_vivo import ClienteTSE, caminho_resultado  # noqa: E402
from eleicoes.tse_arquivos import extrair_do_zip, ler_csv_tse  # noqa: E402

SAIDA = RAIZ / "dados" / "nulos"
GOVERNADOR = 3
URL_RDV = ("https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes{ano}/arqurnatot/"
           "bu_imgbu_logjez_rdv_vscmr_{ano}_{turno}t_{uf}.zip")
URL_CANDIDATOS_2022 = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2022.zip"


def sigla(texto: str) -> str:
    """Normaliza a sigla de um partido: 'PC do B' -> 'PCDOB', 'UNIÃO' -> 'UNIAO'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", sem_acento.upper())


# ---------------------------------------------------------------------------
# 1 e 2: disputas apertadas
# ---------------------------------------------------------------------------

def resultado(votos: dict[int, float], turno: int) -> str:
    ordem = sorted(votos, key=votos.get, reverse=True)
    total = sum(votos.values())
    if turno == 2 or votos[ordem[0]] * 2 > total:
        return f"eleito: {ordem[0]}"
    return f"2º turno: {ordem[0]} × {ordem[1]}"


def disputas(governador: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for (ano, turno, uf), d in governador.groupby(["ano", "turno", "uf"]):
        d = d.sort_values("qt_votos", ascending=False)
        v = d["qt_votos"].tolist() + [0, 0]
        total = sum(d["qt_votos"])
        if turno == 2:
            opcoes = {"virar o 2º turno": v[0] - v[1]}
        elif v[0] * 2 > total:
            opcoes = {"forçar um 2º turno": 2 * v[0] - total}
        else:
            opcoes = {"vencer no 1º turno": total - 2 * v[0], "trocar quem vai ao 2º turno": v[1] - v[2]}
        mudanca, necessarios = min(opcoes.items(), key=lambda kv: kv[1])
        linhas.append({"ano": ano, "turno": turno, "uf": uf, "votos_validos": total,
                       "mais_votado": d.iloc[0]["nm_urna"], "pct_mais_votado": v[0] / total,
                       "mudanca_mais_facil": mudanca, "votos_para_mudar": int(necessarios),
                       "pct_para_mudar": necessarios / total})
    return pd.DataFrame(linhas).sort_values("pct_para_mudar")


# ---------------------------------------------------------------------------
# coligações dos candidatos a Governador
# ---------------------------------------------------------------------------

def coligacoes_2026(uf: str) -> dict[int, set[str]]:
    u = ClienteTSE().baixar(caminho_resultado("ele2026", 6259, GOVERNADOR, uf.lower()))
    saida = {}
    for agr in u["carg"][0]["agr"]:
        partidos = {sigla(p) for p in agr["com"].split("/")}
        for p in agr["par"]:
            for c in p["cand"]:
                saida[int(c["n"])] = partidos | {sigla(p["sg"])}
    return saida


def coligacoes_2022(uf: str) -> dict[int, set[str]]:
    with tempfile.TemporaryDirectory() as tmp:
        csv = extrair_do_zip(URL_CANDIDATOS_2022, f"consulta_cand_2022_{uf}.csv", Path(tmp) / "c.csv")
        df = ler_csv_tse(csv, ["CD_CARGO", "NR_CANDIDATO", "SG_PARTIDO", "DS_COMPOSICAO_COLIGACAO",
                               "DS_COMPOSICAO_FEDERACAO"])
    saida = {}
    for _, c in df[df["CD_CARGO"] == "3"].drop_duplicates("NR_CANDIDATO").iterrows():
        texto = " / ".join(str(c[k]) for k in ("SG_PARTIDO", "DS_COMPOSICAO_COLIGACAO", "DS_COMPOSICAO_FEDERACAO")
                           if pd.notna(c[k]))
        saida[int(c["NR_CANDIDATO"])] = {sigla(t) for t in re.split(r"[/()]", texto) if t.strip()}
    return saida


# ---------------------------------------------------------------------------
# 3: contagem dos RDVs
# ---------------------------------------------------------------------------

def contagem_rdv(ano: int, turno: int, uf: str, paralelos: int) -> pd.DataFrame:
    """Votos por cargo, tipo e número digitado em todas as urnas da UF (com cache)."""
    destino = SAIDA / "rdv" / f"{ano}_{turno}t_{uf}.parquet"
    if destino.exists():
        return pd.read_parquet(destino)
    leitor = ZipRemotoRDV(URL_RDV.format(ano=ano, turno=turno, uf=uf))
    contagem = leitor.contar(paralelos=paralelos)
    if leitor.falhas:
        print(f"   {len(leitor.falhas)} de {len(leitor.membros)} RDVs não puderam ser lidos: {leitor.falhas[:3]}")
    df = pd.DataFrame([(e, c, t, d, q) for (e, c, t, d), q in contagem.items()],
                      columns=["cd_eleicao", "cargo", "tipo", "digitos", "qt"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(destino, index=False)
    return df


# ---------------------------------------------------------------------------
# 4: análise de cada disputa
# ---------------------------------------------------------------------------

def analisar(d: pd.Series, oficial: pd.DataFrame, rdv: pd.DataFrame,
             presidenciaveis: dict[int, str], coligacoes: dict[int, set[str]]) -> dict:
    gov = rdv[rdv["cargo"] == GOVERNADOR]
    nominais = gov[gov["tipo"] == 2].groupby("digitos")["qt"].sum()
    votos = dict(zip(oficial["nr_candidato"], oficial["qt_votos"]))
    confere = all(int(nominais.get(f"{nr:02d}", 0)) == int(q) for nr, q in votos.items())

    nulos = gov[~gov["tipo"].isin(VALIDOS_OU_BRANCOS)]
    com_presid = nulos[nulos["digitos"].isin([f"{n:02d}" for n in presidenciaveis])]
    por_numero = com_presid.groupby("digitos")["qt"].sum().sort_values(ascending=False)
    em_jogo = int(por_numero.sum())

    # hipótese da coligação
    hipotese = {nr: float(q) for nr, q in votos.items()}
    destino_votos = {}
    for digitos, q in por_numero.items():
        partido = sigla(presidenciaveis[int(digitos)])
        candidatos = [nr for nr, partidos in coligacoes.items() if partido in partidos and nr in hipotese]
        if len(candidatos) == 1:
            hipotese[candidatos[0]] += q
            destino_votos[digitos] = candidatos[0]
    nomes = dict(zip(oficial["nr_candidato"], oficial["nm_urna"]))
    nomear = lambda texto: re.sub(r"\d+", lambda m: nomes.get(int(m.group()), m.group()), texto)  # noqa: E731
    res_oficial = nomear(resultado(votos, int(d["turno"])))
    res_hipotese = nomear(resultado(hipotese, int(d["turno"])))

    return {
        "ano": int(d["ano"]), "turno": int(d["turno"]), "uf": d["uf"],
        "resultado_oficial": res_oficial,
        "mudanca_mais_facil": d["mudanca_mais_facil"],
        "votos_para_mudar": int(d["votos_para_mudar"]),
        "nulos_governador": int(nulos["qt"].sum()),
        "nulos_com_numero_de_presidenciavel": em_jogo,
        "detalhe": ", ".join(f"{dg}: {int(q):,}".replace(",", ".") for dg, q in por_numero.head(4).items()),
        "em_jogo_maior_que_margem": em_jogo > d["votos_para_mudar"],
        "para_quem_na_hipotese": ", ".join(f"{dg}→{nomes.get(nr, nr)}" for dg, nr in destino_votos.items()),
        "resultado_na_hipotese": res_hipotese,
        "hipotese_muda_resultado": res_hipotese != res_oficial,
        "rdv_confere_com_oficial": confere,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limite", type=float, default=0.015,
                        help="disputas em que mudar o resultado exigia menos que esta fração dos válidos")
    parser.add_argument("--paralelos", type=int, default=4)
    args = parser.parse_args()

    governador = pd.read_parquet(RAIZ / "dados" / "base" / "governador_uf.parquet")
    con = duckdb.connect(str(RAIZ / "dados" / "eleicoes.duckdb"), read_only=True)
    presid = con.sql("select distinct ano, nr_candidato, sg_partido from votos_presidente where turno = 1").df()
    con.close()

    todas = disputas(governador)
    SAIDA.mkdir(parents=True, exist_ok=True)
    todas.to_csv(SAIDA / "disputas_governador.csv", index=False)
    apertadas = todas[todas["pct_para_mudar"] < args.limite]
    print(f"{len(apertadas)} disputas com menos de {args.limite:.1%} dos válidos para mudar o resultado")

    linhas = []
    for _, d in apertadas.iterrows():
        ano, turno, uf = int(d["ano"]), int(d["turno"]), d["uf"]
        print(f"{ano} {turno}º turno {uf}: lendo RDVs...", flush=True)
        rdv = contagem_rdv(ano, turno, uf, args.paralelos)
        p = presid[presid["ano"] == ano]
        presidenciaveis = dict(zip(p["nr_candidato"].astype(int), p["sg_partido"]))
        coligacoes = coligacoes_2026(uf) if ano == 2026 else coligacoes_2022(uf)
        oficial = governador[(governador["ano"] == ano) & (governador["turno"] == turno) & (governador["uf"] == uf)]
        linhas.append(analisar(d, oficial, rdv, presidenciaveis, coligacoes))
        print(f"   {linhas[-1]}", flush=True)

    tabela = pd.DataFrame(linhas)
    tabela.to_csv(SAIDA / "nulos_disputas_apertadas.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 60)
    print(tabela.to_string(index=False))


if __name__ == "__main__":
    main()
