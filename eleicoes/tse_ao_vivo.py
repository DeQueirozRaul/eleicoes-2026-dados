"""Cliente dos arquivos de resultado "ao vivo" do TSE (resultados.tse.jus.br).

São os mesmos JSONs que alimentam o app Resultados. Não é uma API oficial
documentada: os caminhos abaixo foram mapeados a partir do arquivo de
configuração (`ele-c.json`) e podem mudar entre eleições.

Estrutura dos caminhos (ciclo = "ele2026", eleicao = código da eleição):

    /oficial/comum/config/ele-c.json                         eleições disponíveis
    /oficial/{ciclo}/{eleicao}/config/mun-e{eleicao}-cm.json municípios e zonas
    /oficial/{ciclo}/{eleicao}/dados/{uf}/{uf}-e{eleicao}-ab.json
        andamento da apuração de cada município da UF (seções, comparecimento)
    /oficial/{ciclo}/{eleicao}/dados/{uf}/{uf}{mun}-c{cargo}-e{eleicao}-u.json
        resultado por candidato (use uf="br" e mun="" para o total nacional)

Os números chegam como texto e os percentuais com vírgula ("47,03"); aqui
guardamos sempre as contagens inteiras e recalculamos os percentuais.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

BASE_URL = "https://resultados.tse.jus.br/oficial"
FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")

UFS = [
    "ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms",
    "mt", "pa", "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc",
    "se", "sp", "to", "zz",  # zz = exterior
]


def _int(valor) -> int:
    """Converte os números em texto do TSE ("1234", "" ou None) para int."""
    return int(valor) if valor not in (None, "") else 0


def _momento(data: str | None, hora: str | None) -> pd.Timestamp | None:
    """'04/10/2026' + '18:54:23' -> Timestamp no horário de Brasília."""
    if not data or not hora:
        return None
    dt = datetime.strptime(f"{data} {hora}", "%d/%m/%Y %H:%M:%S")
    return pd.Timestamp(dt, tz=FUSO_BRASILIA)


def caminho_resultado(ciclo: str, eleicao: int, cargo: int, uf: str, municipio: str = "") -> str:
    return f"{ciclo}/{eleicao}/dados/{uf}/{uf}{municipio}-c{cargo:04d}-e{eleicao:06d}-u.json"


def caminho_andamento(ciclo: str, eleicao: int, uf: str) -> str:
    return f"{ciclo}/{eleicao}/dados/{uf}/{uf}-e{eleicao:06d}-ab.json"


def caminho_municipios(ciclo: str, eleicao: int) -> str:
    return f"{ciclo}/{eleicao}/config/mun-e{eleicao:06d}-cm.json"


# ---------------------------------------------------------------------------
# Leitura dos JSONs (funções puras, testáveis sem rede)
# ---------------------------------------------------------------------------

def ler_eleicoes(config: dict) -> pd.DataFrame:
    """Lista as eleições do `ele-c.json`: uma linha por eleição e cargo."""
    linhas = []
    for pleito in config["pl"]:
        for eleicao in pleito["e"]:
            for abrangencia in eleicao["abr"]:
                for cargo in abrangencia.get("cp", []):
                    linhas.append({
                        "ciclo": pleito["c"],
                        "cd_pleito": _int(pleito["cd"]),
                        "data_pleito": pleito["dt"],
                        "cd_eleicao": _int(eleicao["cd"]),
                        "cd_eleicao_2t": _int(eleicao.get("cdt2")),
                        "nm_eleicao": eleicao["nm"],
                        "turno": _int(eleicao["t"]),
                        "abrangencia": abrangencia["cd"],
                        "cd_cargo": _int(cargo["cd"]),
                        "ds_cargo": cargo["ds"],
                    })
    return pd.DataFrame(linhas)


def ler_municipios(config_mun: dict) -> pd.DataFrame:
    """Municípios da eleição, com o código do TSE e o do IBGE."""
    linhas = []
    for uf in config_mun["abr"]:
        for mun in uf["mu"]:
            linhas.append({
                "uf": uf["cd"],
                "cd_municipio_tse": mun["cd"],
                "cd_municipio_ibge": mun.get("cdi") or None,
                "nm_municipio": mun["nm"],
                "capital": mun.get("c") == "s",
                "qt_zonas": len(mun.get("z", [])),
            })
    return pd.DataFrame(linhas)


def _andamento(bloco: dict) -> dict:
    """Campos de andamento comuns aos arquivos -ab e -u."""
    s, e = bloco.get("s", {}), bloco.get("e", {})
    return {
        "dt_totalizacao": _momento(bloco.get("dt"), bloco.get("ht")),
        "qt_secoes": _int(s.get("ts")),
        "qt_secoes_totalizadas": _int(s.get("st")),
        "qt_eleitores": _int(e.get("te")),
        "qt_eleitores_secoes_totalizadas": _int(e.get("est")),
        "qt_comparecimento": _int(e.get("c")),
        "qt_abstencao": _int(e.get("a")),
    }


def ler_andamento(ab: dict, uf: str) -> pd.DataFrame:
    """Andamento da apuração de cada abrangência do arquivo -ab de uma UF."""
    linhas = []
    for bloco in ab["abr"]:
        linhas.append({
            "uf": uf,
            "tp_abrangencia": bloco["tpabr"],
            "cd_abrangencia": bloco["cdabr"],
            **_andamento(bloco),
        })
    return pd.DataFrame(linhas)


@dataclass
class Resultado:
    """Um arquivo -u lido: o resumo da abrangência e os votos por candidato."""

    resumo: dict
    candidatos: pd.DataFrame = field(repr=False)


def ler_resultado(u: dict) -> Resultado:
    """Lê um arquivo -u (resultado de um cargo numa abrangência)."""
    v = u.get("v", {})
    resumo = {
        "cd_eleicao": _int(u["ele"]),
        "turno": _int(u["t"]),
        "tp_abrangencia": u["tpabr"],
        "cd_abrangencia": u["cdabr"],
        "dt_geracao": _momento(u.get("dg"), u.get("hg")),
        "totalizacao_final": u.get("tf") == "s",
        **_andamento(u),
        "qt_votos_total": _int(v.get("tv")),
        "qt_votos_validos": _int(v.get("vv")),
        "qt_votos_nominais": _int(v.get("vnom")),
        "qt_votos_brancos": _int(v.get("vb")),
        "qt_votos_nulos": _int(v.get("tvn")),
        "qt_votos_anulados": _int(v.get("van")),
    }

    linhas = []
    for cargo in u["carg"]:
        for agrupamento in cargo["agr"]:
            for partido in agrupamento["par"]:
                for cand in partido["cand"]:
                    linhas.append({
                        "cd_cargo": _int(cargo["cd"]),
                        "ds_cargo": cargo["nmn"],
                        "nr_candidato": cand["n"],
                        "sq_candidato": cand["sqcand"],
                        "nm_urna": cand["nmu"],
                        "nm_candidato": cand["nm"],
                        "sg_partido": partido["sg"],
                        "nr_partido": partido["n"],
                        "nm_agrupamento": agrupamento["nm"],
                        "tp_agrupamento": {"c": "coligação", "i": "isolado", "f": "federação"}
                            .get(agrupamento["tp"], agrupamento["tp"]),
                        "situacao": cand.get("st"),
                        "destinacao_voto": cand.get("dvt"),
                        "qt_votos": _int(cand.get("vap")),
                    })
    candidatos = pd.DataFrame(linhas)
    if not candidatos.empty:
        validos = resumo["qt_votos_validos"]
        candidatos["pc_votos_validos"] = (
            candidatos["qt_votos"] / validos if validos else float("nan")
        )
    return Resultado(resumo=resumo, candidatos=candidatos)


# ---------------------------------------------------------------------------
# Cliente HTTP
# ---------------------------------------------------------------------------

class ClienteTSE:
    """Baixa os JSONs do TSE com repetição em caso de falha.

    Seja educado com o servidor: poucos downloads em paralelo e intervalos
    de pelo menos alguns segundos entre varreduras.
    """

    def __init__(self, ciclo: str = "ele2026", base_url: str = BASE_URL,
                 timeout: float = 30, tentativas: int = 4, sessao: requests.Session | None = None):
        self.ciclo = ciclo
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.tentativas = tentativas
        self.sessao = sessao or requests.Session()
        self.sessao.headers.setdefault("User-Agent", "eleicoes-2026-dados (projeto de estudo)")

    def baixar(self, caminho: str) -> dict | None:
        """GET de um JSON. Devolve None se o arquivo não existe (404)."""
        url = f"{self.base_url}/{caminho}"
        for tentativa in range(self.tentativas):
            try:
                resposta = self.sessao.get(url, timeout=self.timeout)
                if resposta.status_code == 404:
                    return None
                resposta.raise_for_status()
                return resposta.json()
            except (requests.RequestException, ValueError):
                if tentativa == self.tentativas - 1:
                    raise
                time.sleep(2 ** (tentativa + 1))
        return None

    def eleicoes(self) -> pd.DataFrame:
        return ler_eleicoes(self.baixar("comum/config/ele-c.json"))

    def municipios(self, eleicao: int) -> pd.DataFrame:
        return ler_municipios(self.baixar(caminho_municipios(self.ciclo, eleicao)))

    def andamento(self, eleicao: int, uf: str) -> pd.DataFrame | None:
        ab = self.baixar(caminho_andamento(self.ciclo, eleicao, uf))
        return None if ab is None else ler_andamento(ab, uf)

    def resultado(self, eleicao: int, cargo: int, uf: str = "br", municipio: str = "") -> Resultado | None:
        u = self.baixar(caminho_resultado(self.ciclo, eleicao, cargo, uf, municipio))
        return None if u is None else ler_resultado(u)

    def resultados(self, eleicao: int, cargo: int, alvos: list[tuple[str, str]],
                   paralelos: int = 6) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Baixa vários resultados (lista de (uf, municipio)) em paralelo.

        Devolve (resumos, candidatos), com as colunas `uf` e
        `cd_municipio_tse` identificando cada abrangência.
        """
        def um(alvo):
            uf, mun = alvo
            return uf, mun, self.resultado(eleicao, cargo, uf, mun)

        resumos, candidatos = [], []
        with ThreadPoolExecutor(max_workers=paralelos) as executor:
            for uf, mun, res in executor.map(um, alvos):
                if res is None:
                    continue
                resumos.append({"uf": uf, "cd_municipio_tse": mun, **res.resumo})
                if not res.candidatos.empty:
                    candidatos.append(res.candidatos.assign(uf=uf, cd_municipio_tse=mun))
        return (
            pd.DataFrame(resumos),
            pd.concat(candidatos, ignore_index=True) if candidatos else pd.DataFrame(),
        )
