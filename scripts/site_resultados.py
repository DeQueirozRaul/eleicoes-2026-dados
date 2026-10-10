"""Prepara os dados da página "Resultados e mapa" do site (app/paginas/resultados.py).

O que faz, em ordem:
1. Baixa o que ainda não foi baixado (fica guardado em dados/brutos/resultados/;
   rodar de novo não baixa outra vez):
   - malha dos municípios do IBGE (contorno de cada município, 1 arquivo);
   - total nacional de Presidente do 1º turno de 2026 (para conferir as somas);
   - resultado de Deputado Federal de cada UF (27 arquivos), com a situação de
     cada candidato (eleito por QP, eleito por média, suplente, não eleito);
   - resultado de Governador em cada município (~5.600 arquivos pequenos).
2. Lê do banco dados/eleicoes.duckdb os votos e o comparecimento para Presidente
   (2002 a 2026, por município).
3. Calcula e grava os arquivos pequenos que o site lê, em app/dados/:
   resultados_placar, resultados_municipios, resultados_comparecimento_serie,
   resultados_comparecimento_uf, resultados_deputados, resultados_deputados_uf
   (.parquet) e resultados_malha.json (geometria simplificada).
4. Confere os números: soma dos municípios = total nacional, todo município do
   mapa tem resultado e vice-versa, nº de eleitos = nº de vagas (513).

Fontes:
- IBGE, API de malhas (v4, que já traz Boa Esperança do Norte-MT, instalado em
  2025; a v3 ainda tem 5.570 municípios):
  https://servicodados.ibge.gov.br/api/v4/malhas/paises/BR?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=municipio
- TSE, arquivos de resultado (os mesmos do app Resultados; ver eleicoes/tse_ao_vivo.py):
  https://resultados.tse.jus.br/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json
  https://resultados.tse.jus.br/oficial/ele2026/6259/dados/{uf}/{uf}-c0006-e006259-u.json
  https://resultados.tse.jus.br/oficial/ele2026/6259/dados/{uf}/{uf}{municipio}-c0003-e006259-u.json
- Banco dados/eleicoes.duckdb (scripts/montar_base.py): Portal de Dados Abertos
  do TSE para 2002 a 2022 e coletor ao vivo para 2026.

Antes: scripts/montar_base.py.

    python scripts/site_resultados.py
    python scripts/site_resultados.py --sem-governador   # pula os ~5.600 downloads de Governador
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.tse_ao_vivo import UFS, ClienteTSE, caminho_resultado  # noqa: E402

BRUTOS = RAIZ / "dados" / "brutos" / "resultados"
SAIDA = RAIZ / "app" / "dados"
BANCO = RAIZ / "dados" / "eleicoes.duckdb"

URL_MALHA = ("https://servicodados.ibge.gov.br/api/v4/malhas/paises/BR"
             "?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=municipio")
PRESIDENTE_1T, GERAIS_1T = 6257, 6259
PRESIDENTE, GOVERNADOR, DEP_FEDERAL = 1, 3, 6
PARALELOS = 4  # o servidor do TSE devolve 403 com muitas conexões ao mesmo tempo

# Códigos IBGE das UFs (os 2 primeiros dígitos do código do município).
UF_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA",
    "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS",
    "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}


# ---------------------------------------------------------------------------
# 1. downloads
# ---------------------------------------------------------------------------

def baixar_arquivo(url: str, destino: Path, tentativas: int = 5) -> Path:
    """Baixa `url` para `destino` (se ainda não existe), com novas tentativas."""
    if destino.exists():
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    for tentativa in range(tentativas):
        try:
            resposta = requests.get(url, timeout=120)
            resposta.raise_for_status()
            temporario = destino.with_suffix(".parcial")
            temporario.write_bytes(resposta.content)
            temporario.replace(destino)
            return destino
        except requests.RequestException:
            if tentativa == tentativas - 1:
                raise
            time.sleep(5 * (tentativa + 1))
    return destino


def baixar_jsons_tse(alvos: dict[str, Path], paralelos: int = PARALELOS) -> list[str]:
    """Baixa vários JSONs de resultado do TSE ({caminho: destino}), só os que faltam.

    Usa no máximo `paralelos` conexões; o que falhar é tentado de novo, um de
    cada vez e com mais espera. Devolve os caminhos que não deu para baixar
    (o arquivo não existe no servidor ou falhou em todas as tentativas)."""
    faltam = {c: d for c, d in alvos.items() if not d.exists()}
    if not faltam:
        return []
    print(f"   baixando {len(faltam)} de {len(alvos)} arquivos...", flush=True)
    cliente = ClienteTSE(tentativas=3)

    def um(caminho: str) -> str | None:
        destino = faltam[caminho]
        try:
            dados = cliente.baixar(caminho)
        except Exception:  # noqa: BLE001  (fica para a segunda rodada)
            return caminho
        if dados is None:
            return caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(".parcial")
        temporario.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporario.replace(destino)
        return None

    falhas = []
    with ThreadPoolExecutor(max_workers=paralelos) as executor:
        for i, falha in enumerate(executor.map(um, list(faltam)), 1):
            if falha:
                falhas.append(falha)
            if i % 500 == 0:
                print(f"   {i}/{len(faltam)}", flush=True)
    # segunda rodada: um de cada vez, com pausa
    restantes = []
    for caminho in falhas:
        time.sleep(3)
        if um(caminho):
            restantes.append(caminho)
    return restantes


def baixar_tudo(municipios: pd.DataFrame, governador: bool) -> None:
    print("1. downloads (só o que falta)", flush=True)
    baixar_arquivo(URL_MALHA, BRUTOS / "malha_municipios_ibge.json")

    alvos = {caminho_resultado("ele2026", PRESIDENTE_1T, PRESIDENTE, "br"): BRUTOS / "presidente_br.json"}
    for uf in UFS:
        if uf != "zz":
            alvos[caminho_resultado("ele2026", GERAIS_1T, DEP_FEDERAL, uf)] = (
                BRUTOS / "deputado_federal" / f"{uf}.json")
    # arquivo guardado antes de a totalização terminar (ex.: UF aguardando reprocessamento): baixa de novo
    for destino in alvos.values():
        if destino.exists() and json.loads(destino.read_text(encoding="utf-8")).get("tf") != "s":
            destino.unlink()
    falhas = baixar_jsons_tse(alvos)
    if falhas:
        raise SystemExit(f"Não deu para baixar: {falhas}. Rode de novo em alguns minutos.")

    if governador:
        alvos = {
            caminho_resultado("ele2026", GERAIS_1T, GOVERNADOR, m.uf.lower(), m.cd_municipio_tse):
                BRUTOS / "governador" / m.uf.lower() / f"{m.cd_municipio_tse}.json"
            for m in municipios.itertuples()
        }
        falhas = baixar_jsons_tse(alvos)
        if falhas:
            print(f"   !! {len(falhas)} arquivos de Governador não foram baixados (ex.: {falhas[:3]}); "
                  "rode de novo para completar.", flush=True)


# ---------------------------------------------------------------------------
# geometria: malha do IBGE simplificada sem abrir frestas entre vizinhos
# ---------------------------------------------------------------------------

def _distancia(p: tuple, a: tuple, b: tuple) -> float:
    """Distância do ponto p ao segmento a-b (ou ao ponto a, se a == b)."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    comprimento2 = dx * dx + dy * dy
    if comprimento2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / comprimento2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def douglas_peucker(pontos: list, tolerancia: float) -> list:
    """Simplifica uma linha: tira os pontos que se afastam menos que `tolerancia`
    do traçado simplificado. As duas pontas sempre ficam."""
    n = len(pontos)
    if n < 3:
        return list(pontos)
    manter = [False] * n
    manter[0] = manter[-1] = True
    pilha = [(0, n - 1)]
    while pilha:
        i, j = pilha.pop()
        maior, k = -1.0, -1
        for m in range(i + 1, j):
            d = _distancia(pontos[m], pontos[i], pontos[j])
            if d > maior:
                maior, k = d, m
        if k >= 0 and maior > tolerancia:
            manter[k] = True
            pilha += [(i, k), (k, j)]
    return [p for p, fica in zip(pontos, manter) if fica]


def simplificar_malha(poligonos: dict[str, list], tolerancia: float) -> tuple[dict[str, list], int]:
    """Simplifica os contornos de todos os municípios juntos.

    `poligonos` = {código: [polígono, ...]}, polígono = [anel externo, buracos...],
    anel = lista fechada de pontos (x, y) inteiros (coordenadas já arredondadas).

    Simplificar cada município sozinho abriria frestas entre vizinhos. Aqui cada
    trecho de divisa (entre dois "nós", os pontos onde muda quem está do outro
    lado) é simplificado uma vez só e o mesmo resultado vale para os dois lados.
    Devolve (polígonos simplificados, nº de anéis que ficariam degenerados e
    foram mantidos sem simplificar ou, se eram buracos, retirados).
    """
    def aresta(a, b):
        return (a, b) if a < b else (b, a)

    aneis = []
    for codigo, lista in poligonos.items():
        for ip, poligono in enumerate(lista):
            for ia, anel in enumerate(poligono):
                pontos = [p for i, p in enumerate(anel) if i == 0 or p != anel[i - 1]]
                if len(pontos) > 1 and pontos[0] == pontos[-1]:
                    pontos = pontos[:-1]
                aneis.append((codigo, ip, ia, pontos))

    uso: dict[tuple, set] = {}
    vizinhos: dict[tuple, set] = {}
    for k, (_, _, _, pontos) in enumerate(aneis):
        n = len(pontos)
        for i in range(n):
            a, b = pontos[i], pontos[(i + 1) % n]
            uso.setdefault(aresta(a, b), set()).add(k)
            vizinhos.setdefault(a, set()).add(b)
            vizinhos.setdefault(b, set()).add(a)

    cache: dict[tuple, list] = {}

    def arco_simplificado(arco: list) -> list:
        chave, inverso = tuple(arco), tuple(reversed(arco))
        invertido = inverso < chave  # mesma divisa percorrida ao contrário pelo vizinho
        if invertido:
            chave = inverso
        if chave not in cache:
            cache[chave] = douglas_peucker(list(chave), tolerancia)
        return cache[chave][::-1] if invertido else cache[chave]

    saida: dict[str, list] = {}
    degenerados = 0
    for codigo, ip, ia, pontos in aneis:
        n = len(pontos)
        if n < 3:
            continue
        assinatura = [frozenset(uso[aresta(pontos[i], pontos[(i + 1) % n])]) for i in range(n)]
        nos = [i for i in range(n) if len(vizinhos[pontos[i]]) > 2 or assinatura[i - 1] != assinatura[i]]
        if not nos:  # ilha ou enclave: começa no menor ponto, o mesmo para os dois lados
            nos = [min(range(n), key=lambda i: pontos[i])]
        novo = []
        for j, inicio in enumerate(nos):
            fim = nos[(j + 1) % len(nos)]
            arco = pontos[inicio:fim + 1] if fim > inicio else pontos[inicio:] + pontos[:fim + 1]
            novo.extend(arco_simplificado(arco)[:-1])
        if len(set(novo)) < 3:
            degenerados += 1
            if ia > 0:
                continue  # buraco minúsculo: some
            novo = pontos
        novo.append(novo[0])
        lista = saida.setdefault(codigo, [])
        while len(lista) <= ip:
            lista.append([])
        lista[ip].append(novo)
    return {c: [p for p in lista if p] for c, lista in saida.items()}, degenerados


def area_com_sinal(anel: list) -> float:
    """Área do anel pela fórmula do cadarço: positiva se o anel gira no sentido anti-horário."""
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(anel, anel[1:])) / 2


def orientar(poligono: list) -> list:
    """Põe o anel externo no sentido horário e os buracos no anti-horário.

    É o sentido que o mapa do Plotly (d3-geo) espera; no sentido contrário,
    o polígono é lido como "o globo inteiro menos o município"."""
    saida = []
    for i, anel in enumerate(poligono):
        horario = area_com_sinal(anel) < 0
        if horario != (i == 0):
            anel = anel[::-1]
        saida.append(anel)
    return saida


def preparar_malha(origem: Path, destino: Path, casas: int = 3, tolerancia: float = 3) -> int:
    """Lê a malha do IBGE, arredonda as coordenadas para `casas` decimais
    (3 casas = ~100 m), simplifica (tolerância em unidades da última casa) e grava
    um GeoJSON compacto com o código IBGE de 7 dígitos em `id`. Devolve o nº de municípios."""
    escala = 10 ** casas
    bruto = json.loads(origem.read_text(encoding="utf-8"))
    poligonos = {}
    for feicao in bruto["features"]:
        g = feicao["geometry"]
        lista = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        poligonos[feicao["properties"]["codarea"]] = [
            [[(round(x * escala), round(y * escala)) for x, y in anel] for anel in poligono]
            for poligono in lista
        ]
    simplificados, degenerados = simplificar_malha(poligonos, tolerancia)
    feicoes = []
    for codigo, lista in sorted(simplificados.items()):
        coordenadas = [[[[x / escala, y / escala] for x, y in anel] for anel in orientar(poligono)]
                       for poligono in lista]
        geometria = ({"type": "Polygon", "coordinates": coordenadas[0]} if len(coordenadas) == 1
                     else {"type": "MultiPolygon", "coordinates": coordenadas})
        feicoes.append({"type": "Feature", "id": codigo, "properties": {}, "geometry": geometria})
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"type": "FeatureCollection", "features": feicoes}, separators=(",", ":")),
                       encoding="utf-8")
    antes = sum(len(a) for lista in poligonos.values() for p in lista for a in p)
    depois = sum(len(a) for lista in simplificados.values() for p in lista for a in p)
    print(f"   malha: {len(feicoes)} municípios, {antes} -> {depois} pontos, "
          f"{degenerados} anéis pequenos demais mantidos sem simplificar, "
          f"{destino.stat().st_size / 1e6:.2f} MB", flush=True)
    return len(feicoes)


# ---------------------------------------------------------------------------
# funções de cálculo (puras, testadas em tests/test_site_resultados.py)
# ---------------------------------------------------------------------------

MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "d'"}


def nome_proprio(texto: str) -> str:
    """'SÃO JOÃO DO RIO VERMELHO' -> 'São João do Rio Vermelho'; "PINGO D'ÁGUA" -> "Pingo d'Água"."""
    palavras = []
    for i, palavra in enumerate(texto.lower().split()):
        if i > 0 and palavra in MINUSCULAS:
            palavras.append(palavra)
        elif palavra.startswith("d'") and len(palavra) > 2:
            palavras.append("d'" + palavra[2:].capitalize() if i > 0 else "D'" + palavra[2:].capitalize())
        else:
            palavras.append("-".join(p.capitalize() for p in palavra.split("-")))
    return " ".join(palavras)


def sigla(texto: str) -> str:
    """Normaliza a sigla de um partido: 'PC do B' -> 'PCDOB', 'UNIÃO' -> 'UNIAO'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", sem_acento.upper())


def mais_votados(votos: pd.DataFrame, chave: list[str]) -> pd.DataFrame:
    """Para cada grupo de `chave` (ex.: município): o mais votado e o segundo,
    com a % de cada um nos votos válidos e a diferença entre os dois.

    `votos` tem uma linha por candidato, com `nm_urna`, `sg_partido` e `qt_votos`.
    Em caso de empate no 1º lugar, `empate` é verdadeiro, o mais votado e o
    partido viram "empate" e `empatados` traz os dois nomes em ordem alfabética."""
    v = votos.sort_values(chave + ["qt_votos", "nm_urna"], ascending=[True] * len(chave) + [False, True])
    v = v.assign(validos=v.groupby(chave)["qt_votos"].transform("sum"))
    v = v.assign(pct=v["qt_votos"] / v["validos"].where(v["validos"] > 0))
    g = v.groupby(chave, sort=False)
    primeiro = g.nth(0).set_index(chave)
    segundo = g.nth(1).set_index(chave)
    saida = pd.DataFrame({
        "qt_validos": primeiro["validos"],
        "mais_votado": primeiro["nm_urna"],
        "partido_mais_votado": primeiro["sg_partido"],
        "pct_mais_votado": primeiro["pct"],
        "segundo": segundo["nm_urna"],
        "pct_segundo": segundo["pct"],
    })
    saida["vantagem"] = saida["pct_mais_votado"] - saida["pct_segundo"].fillna(0)
    saida["empate"] = primeiro["qt_votos"] == segundo["qt_votos"].reindex(primeiro.index)
    saida["empatados"] = [" e ".join(sorted([a, b])) if e else None
                          for a, b, e in zip(saida["mais_votado"], saida["segundo"], saida["empate"])]
    saida.loc[saida["empate"], ["mais_votado", "partido_mais_votado"]] = "empate"
    return saida.reset_index()


def transicao(partido_antes, partido_depois, ano_antes: int = 2022, ano_depois: int = 2026) -> str:
    """Rótulo da mudança do partido do mais votado entre duas eleições."""
    if pd.isna(partido_antes) or pd.isna(partido_depois):
        return f"sem resultado em {ano_antes if pd.isna(partido_antes) else ano_depois}"
    if partido_antes == partido_depois:
        return f"{partido_depois} nas duas"
    return f"{partido_antes} em {ano_antes} → {partido_depois} em {ano_depois}"


def lado_governador(partido_presidente: str, partidos_coligacao: set[str], partidos_com_candidato: set[str]) -> str:
    """Compara o Governador mais votado no município com o Presidente mais votado ali.

    Regra (a mesma para todos): o partido do candidato a Presidente mais votado
    está na coligação (ou federação) do candidato a Governador mais votado?
    `partidos_com_candidato` = partidos de todas as coligações que lançaram
    candidato a Governador na UF."""
    p = sigla(partido_presidente)
    if p in partidos_coligacao:
        return "mesma coligação"
    if p in partidos_com_candidato:
        return "coligações diferentes"
    return "partido sem candidato a Governador"


def partidos_do_agrupamento(agrupamento: dict) -> set[str]:
    """Siglas normalizadas de uma coligação/federação/partido isolado de um JSON do TSE.
    O campo `com` lista os partidos separados por '/' (ex.: 'PL / NOVO')."""
    partidos = {sigla(p) for p in re.split(r"[/()]", agrupamento.get("com") or "") if p.strip()}
    return partidos | {sigla(p["sg"]) for p in agrupamento["par"]}


def cortes_deputados(candidatos: pd.DataFrame) -> pd.DataFrame:
    """Para cada UF: o eleito com menos votos, o não eleito com mais votos e
    quantos ficaram de fora com mais votos que o eleito menos votado.

    Só entram candidatos com votos válidos (votos anulados sub judice não contam
    para ninguém) e UFs com a totalização concluída."""
    linhas = []
    for uf, c in candidatos[candidatos["voto_valido"]].groupby("uf"):
        eleitos = c[c["eleito"]].sort_values("qt_votos")
        fora = c[~c["eleito"]].sort_values("qt_votos", ascending=False)
        if eleitos.empty:
            continue
        menor = eleitos.iloc[0]
        maior = fora.iloc[0] if not fora.empty else None
        linhas.append({
            "uf": uf,
            "menor_eleito": menor["nm_urna"], "partido_menor_eleito": menor["sg_partido"],
            "votos_menor_eleito": int(menor["qt_votos"]),
            "maior_nao_eleito": None if maior is None else maior["nm_urna"],
            "partido_maior_nao_eleito": None if maior is None else maior["sg_partido"],
            "votos_maior_nao_eleito": 0 if maior is None else int(maior["qt_votos"]),
            "fora_com_mais_votos": int((fora["qt_votos"] > menor["qt_votos"]).sum()),
            "eleitos_com_menos_votos": int((eleitos["qt_votos"] < (0 if maior is None else maior["qt_votos"])).sum()),
        })
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# 2 e 3. cálculos com os dados reais
# ---------------------------------------------------------------------------

def ler_banco() -> dict[str, pd.DataFrame]:
    con = duckdb.connect(str(BANCO), read_only=True)
    tabelas = {
        "municipios": con.sql("select * from municipios").df(),
        "votos": con.sql("""
            select ano, uf, cd_municipio_tse, nr_candidato, nm_urna, sg_partido, qt_votos::bigint as qt_votos
            from votos_presidente where turno = 1 and ano in (2022, 2026)""").df(),
        "comparecimento": con.sql("""
            select ano, turno, uf, cd_municipio_tse,
                   qt_aptos::bigint as qt_aptos, qt_comparecimento::bigint as qt_comparecimento,
                   qt_abstencoes::bigint as qt_abstencoes, qt_brancos::bigint as qt_brancos,
                   qt_nulos::bigint as qt_nulos, qt_validos::bigint as qt_validos
            from comparecimento_presidente""").df(),
    }
    con.close()
    return tabelas


def calcular_placar(votos26: pd.DataFrame) -> pd.DataFrame:
    """Votos de cada candidato a Presidente no 1º turno de 2026 (Brasil + exterior),
    conferidos com o total nacional publicado pelo TSE."""
    placar = (votos26.groupby(["nr_candidato", "nm_urna", "sg_partido"], as_index=False)["qt_votos"].sum()
              .sort_values("qt_votos", ascending=False, ignore_index=True))
    placar["pct_validos"] = placar["qt_votos"] / placar["qt_votos"].sum()
    placar["posicao"] = range(1, len(placar) + 1)

    oficial = json.loads((BRUTOS / "presidente_br.json").read_text(encoding="utf-8"))
    votos_oficiais = {int(c["n"]): int(c["vap"]) for a in oficial["carg"][0]["agr"] for p in a["par"] for c in p["cand"]}
    diferencas = {nr: q - votos_oficiais.get(nr, 0) for nr, q in zip(placar["nr_candidato"], placar["qt_votos"])}
    assert all(d == 0 for d in diferencas.values()), f"soma dos municípios difere do total nacional: {diferencas}"
    assert placar["qt_votos"].sum() == int(oficial["v"]["vv"]), "soma dos candidatos difere dos votos válidos"
    print(f"   ok: soma dos {votos26['cd_municipio_tse'].nunique()} municípios (com o exterior) "
          f"= total nacional do TSE para os {len(placar)} candidatos ({placar['qt_votos'].sum():,} votos válidos)")
    return placar


def calcular_municipios(t: dict[str, pd.DataFrame], placar: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por município do Brasil (sem o exterior): resultado de 2026,
    comparação com 2022 e comparecimento."""
    mun = t["municipios"][t["municipios"]["uf"] != "ZZ"].copy()
    votos = t["votos"][t["votos"]["uf"] != "ZZ"]
    chave = ["uf", "cd_municipio_tse"]

    v26 = votos[votos["ano"] == 2026]
    r26 = mais_votados(v26, chave)
    finalistas = placar.nsmallest(2, "posicao")["nr_candidato"].tolist()
    # votos e % dos dois mais votados do país (colunas votos_<número> e pct_<número>)
    votos_fin = v26[v26["nr_candidato"].isin(finalistas)].pivot_table(
        index=chave, columns="nr_candidato", values="qt_votos", aggfunc="sum", fill_value=0)
    validos = v26.groupby(chave)["qt_votos"].sum().reindex(votos_fin.index)
    pcts = votos_fin.div(validos.where(validos > 0), axis=0)
    pcts.columns = [f"pct_{nr}" for nr in pcts.columns]
    votos_fin.columns = [f"votos_{nr}" for nr in votos_fin.columns]
    pcts = pcts.join(votos_fin)

    r22 = mais_votados(votos[votos["ano"] == 2022], chave)[chave + ["mais_votado", "partido_mais_votado", "empate"]]
    r22.columns = chave + ["mais_votado_2022", "partido_2022", "empate_2022"]

    c26 = t["comparecimento"].query("ano == 2026 and turno == 1")[
        chave + ["qt_aptos", "qt_comparecimento", "qt_abstencoes", "qt_brancos", "qt_nulos"]]

    saida = (mun.merge(r26, on=chave, how="left")
             .merge(pcts.reset_index(), on=chave, how="left")
             .merge(r22, on=chave, how="left")
             .merge(c26, on=chave, how="left"))
    saida["nm_municipio"] = saida["nm_municipio"].map(nome_proprio)
    saida["transicao"] = [transicao(a, b) for a, b in zip(saida["partido_2022"], saida["partido_mais_votado"])]
    saida["pct_abstencao"] = saida["qt_abstencoes"] / saida["qt_aptos"]
    saida["pct_brancos"] = saida["qt_brancos"] / saida["qt_comparecimento"]
    saida["pct_nulos"] = saida["qt_nulos"] / saida["qt_comparecimento"]

    # conferências
    assert len(saida) == saida["cd_municipio_ibge"].nunique(), "código IBGE repetido"
    assert saida["mais_votado"].notna().all(), "município sem resultado de 2026"
    soma = v26.groupby("nr_candidato")["qt_votos"].sum()
    exterior = t["votos"].query("ano == 2026 and uf == 'ZZ'").groupby("nr_candidato")["qt_votos"].sum()
    total = soma.add(exterior, fill_value=0).sort_index()
    assert total.equals(placar.set_index("nr_candidato")["qt_votos"].sort_index().astype(total.dtype))
    return saida


def calcular_comparecimento(t: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Brasil (com o exterior) por eleição e turno, 2002 a 2026; e por UF no 1º turno de 2026."""
    colunas = ["qt_aptos", "qt_comparecimento", "qt_abstencoes", "qt_brancos", "qt_nulos", "qt_validos"]

    def taxas(d: pd.DataFrame) -> pd.DataFrame:
        return d.assign(pct_abstencao=d["qt_abstencoes"] / d["qt_aptos"],
                        pct_brancos=d["qt_brancos"] / d["qt_comparecimento"],
                        pct_nulos=d["qt_nulos"] / d["qt_comparecimento"])

    c = t["comparecimento"]
    serie = taxas(c.groupby(["ano", "turno"], as_index=False)[colunas].sum())
    por_uf = taxas(c.query("ano == 2026 and turno == 1").groupby("uf", as_index=False)[colunas].sum())
    return serie, por_uf


def ler_deputados() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Candidatos a Deputado Federal (votos e situação) e o resumo de cada UF."""
    candidatos, ufs = [], []
    for arquivo in sorted((BRUTOS / "deputado_federal").glob("*.json")):
        u = json.loads(arquivo.read_text(encoding="utf-8"))
        uf = arquivo.stem.upper()
        cargo = u["carg"][0]
        for agr in cargo["agr"]:
            for partido in agr["par"]:
                for c in partido["cand"]:
                    candidatos.append({
                        "uf": uf, "nr_candidato": c["n"], "nm_urna": c["nmu"], "sg_partido": partido["sg"],
                        "agrupamento": agr.get("com") or partido["sg"], "qt_votos": int(c.get("vap") or 0),
                        "situacao": c.get("st") or "", "eleito": c.get("e") == "s",
                        "voto_valido": (c.get("dvt") or "").startswith("Válido"),
                    })
        ufs.append({
            "uf": uf, "vagas": int(cargo["nv"]), "quociente_eleitoral": int(cargo["qe"]),
            "qt_validos": int(u["v"]["vv"]), "totalizacao_final": u.get("tf") == "s",
            "mensagem_tse": u.get("mntf") or "",
            "vagas_distribuidas": sum(int(a.get("vag") or 0) for a in cargo["agr"]),
            "dt_geracao": f"{u.get('dg')} {u.get('hg')}",
        })
    candidatos, ufs = pd.DataFrame(candidatos), pd.DataFrame(ufs)
    contagem = candidatos.groupby("uf").agg(
        eleitos=("eleito", "sum"),
        eleitos_qp=("situacao", lambda s: (s == "Eleito por QP").sum()),
        eleitos_media=("situacao", lambda s: (s == "Eleito por média").sum()),
        candidatos=("nm_urna", "size"),
        anulados_sub_judice=("voto_valido", lambda s: (~s).sum()),
    ).reset_index()
    ufs = ufs.merge(contagem, on="uf").merge(cortes_deputados(candidatos), on="uf", how="left")

    # conferências: vagas = 513; em cada UF concluída, eleitos = vagas = vagas distribuídas
    assert ufs["vagas"].sum() == 513, ufs["vagas"].sum()
    concluidas = ufs[ufs["totalizacao_final"]]
    assert (concluidas["eleitos"] == concluidas["vagas"]).all()
    assert (concluidas["vagas_distribuidas"] == concluidas["vagas"]).all()
    assert (concluidas["eleitos_qp"] + concluidas["eleitos_media"] == concluidas["eleitos"]).all()
    # o quociente eleitoral é os votos válidos divididos pelas vagas, arredondado
    assert ((ufs["qt_validos"] / ufs["vagas"]).round() - ufs["quociente_eleitoral"]).abs().max() <= 1
    pendentes = ufs[~ufs["totalizacao_final"]]
    print(f"   ok: {ufs['vagas'].sum()} vagas; {int(ufs['eleitos'].sum())} eleitos definidos"
          + (f"; aguardando: {', '.join(f'{r.uf} ({r.vagas} vagas, {r.mensagem_tse!r})' for r in pendentes.itertuples())}"
             if len(pendentes) else ""))
    return candidatos, ufs


def ler_governador(municipios: pd.DataFrame, presidente: pd.DataFrame) -> pd.DataFrame:
    """Governador mais votado em cada município e o lado em relação ao Presidente
    mais votado ali (ver `lado_governador`)."""
    linhas = []
    for m in municipios.itertuples():
        arquivo = BRUTOS / "governador" / m.uf.lower() / f"{m.cd_municipio_tse}.json"
        if not arquivo.exists():
            continue
        u = json.loads(arquivo.read_text(encoding="utf-8"))
        for agr in u["carg"][0]["agr"]:
            partidos = partidos_do_agrupamento(agr)
            for partido in agr["par"]:
                for c in partido["cand"]:
                    if (c.get("dvt") or "").startswith("Válido"):
                        linhas.append({"uf": m.uf, "cd_municipio_tse": m.cd_municipio_tse, "nm_urna": c["nmu"],
                                       "sg_partido": partido["sg"], "qt_votos": int(c.get("vap") or 0),
                                       "partidos": "/".join(sorted(partidos))})
    if not linhas:
        return pd.DataFrame()
    gov = pd.DataFrame(linhas)
    chave = ["uf", "cd_municipio_tse"]
    mv = mais_votados(gov, chave).rename(columns={
        "mais_votado": "gov_mais_votado", "partido_mais_votado": "gov_partido",
        "pct_mais_votado": "gov_pct", "empate": "gov_empate"})
    coligacao = gov.drop_duplicates(chave + ["nm_urna"]).set_index(chave + ["nm_urna"])["partidos"]
    mv["gov_coligacao"] = [coligacao.get((u, c, n)) for u, c, n in
                           zip(mv["uf"], mv["cd_municipio_tse"], mv["gov_mais_votado"])]
    com_candidato = gov.groupby("uf")["partidos"].agg(lambda s: set("/".join(s).split("/")))
    mv = mv.merge(presidente[chave + ["partido_mais_votado"]], on=chave)
    mv["lado"] = [
        "empate" if p == "empate" or col is None else lado_governador(p, set(col.split("/")), com_candidato[uf])
        for p, col, uf in zip(mv["partido_mais_votado"], mv["gov_coligacao"], mv["uf"])
    ]
    return mv[chave + ["gov_mais_votado", "gov_partido", "gov_pct", "gov_coligacao", "lado"]]


def gravar(tabela: pd.DataFrame, nome: str) -> None:
    destino = SAIDA / f"{nome}.parquet"
    tabela.to_parquet(destino, index=False, compression="zstd")
    print(f"   {destino.relative_to(RAIZ)}: {len(tabela)} linhas, {destino.stat().st_size / 1e3:.0f} kB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sem-governador", action="store_true",
                        help="não baixa nem calcula o voto dividido Presidente x Governador")
    args = parser.parse_args()

    tabelas = ler_banco()
    municipios = tabelas["municipios"].query("uf != 'ZZ'").sort_values(["uf", "cd_municipio_tse"])
    baixar_tudo(municipios, governador=not args.sem_governador)

    print("2. cálculos e conferências", flush=True)
    SAIDA.mkdir(parents=True, exist_ok=True)
    n_mapa = preparar_malha(BRUTOS / "malha_municipios_ibge.json", SAIDA / "resultados_malha.json",
                            casas=3, tolerancia=20)
    placar = calcular_placar(tabelas["votos"].query("ano == 2026"))
    mun = calcular_municipios(tabelas, placar)
    malha = json.loads((SAIDA / "resultados_malha.json").read_text(encoding="utf-8"))
    no_mapa = {f["id"] for f in malha["features"]}
    sem_mapa = set(mun["cd_municipio_ibge"]) - no_mapa
    sem_resultado = no_mapa - set(mun["cd_municipio_ibge"])
    assert not sem_mapa and not sem_resultado, (sem_mapa, sem_resultado)
    print(f"   ok: {n_mapa} municípios no mapa, todos com resultado; {len(mun)} na tabela")

    if not args.sem_governador:
        gov = ler_governador(municipios, mun)
        mun = mun.merge(gov, on=["uf", "cd_municipio_tse"], how="left")
        print(f"   governador: {gov['gov_mais_votado'].notna().sum()} municípios; "
              + ", ".join(f"{k}: {v}" for k, v in gov["lado"].value_counts().items()))

    serie, por_uf = calcular_comparecimento(tabelas)
    candidatos, ufs = ler_deputados()

    print("3. arquivos do site", flush=True)
    gravar(placar, "resultados_placar")
    gravar(mun.drop(columns=["regiao", "capital", "empate"], errors="ignore"), "resultados_municipios")
    gravar(serie, "resultados_comparecimento_serie")
    gravar(por_uf, "resultados_comparecimento_uf")
    gravar(candidatos, "resultados_deputados")
    gravar(ufs, "resultados_deputados_uf")
    total = sum(f.stat().st_size for f in SAIDA.glob("resultados_*"))
    print(f"   total da página em app/dados/: {total / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
