"""Leitura dos arquivos do Portal de Dados Abertos do TSE (cdn.tse.jus.br).

Os arquivos vêm em zips grandes com um CSV por UF e um CSV nacional ("_BR").
O servidor aceita pedidos parciais (HTTP Range), então `ZipRemoto` lê só o
índice do zip e o arquivo de que precisamos, sem baixar o zip inteiro: para o
resultado presidencial de 2022 são ~40 MB em vez de 640 MB.

Os CSVs do TSE usam `;` como separador, codificação Latin-1 e alguns códigos
para "sem informação" (`#NULO#`, `#NE#`, `-1`, `-3`).
"""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

import pandas as pd
import requests

CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"
SEM_INFORMACAO = ["#NULO#", "#NULO", "#NE#", "#NE"]


def url_odsele(conjunto: str, ano: int) -> str:
    """Ex.: url_odsele("votacao_candidato_munzona", 2022)."""
    return f"{CDN}/{conjunto}/{conjunto}_{ano}.zip"


class ArquivoRemoto(io.RawIOBase):
    """Arquivo remoto somente leitura que busca os bytes sob demanda (HTTP Range)."""

    def __init__(self, url: str, sessao: requests.Session | None = None,
                 bloco: int = 4 * 1024 * 1024, timeout: float = 120):
        self.url = url
        self.sessao = sessao or requests.Session()
        self.bloco = bloco
        self.timeout = timeout
        resposta = self.sessao.head(url, timeout=timeout, allow_redirects=True)
        resposta.raise_for_status()
        self.tamanho = int(resposta.headers["Content-Length"])
        self.posicao = 0
        self._cache: dict[int, bytes] = {}

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.posicao

    def seek(self, deslocamento: int, origem: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.posicao, io.SEEK_END: self.tamanho}[origem]
        self.posicao = max(0, base + deslocamento)
        return self.posicao

    def _bloco(self, indice: int) -> bytes:
        if indice not in self._cache:
            inicio = indice * self.bloco
            fim = min(inicio + self.bloco, self.tamanho) - 1
            resposta = self.sessao.get(self.url, headers={"Range": f"bytes={inicio}-{fim}"},
                                       timeout=self.timeout)
            resposta.raise_for_status()
            if len(self._cache) > 8:  # leitura é sequencial; guarda só os blocos recentes
                self._cache.pop(next(iter(self._cache)))
            self._cache[indice] = resposta.content
        return self._cache[indice]

    def readinto(self, destino) -> int:
        if self.posicao >= self.tamanho:
            return 0
        indice, deslocamento = divmod(self.posicao, self.bloco)
        dados = self._bloco(indice)[deslocamento:deslocamento + len(destino)]
        destino[:len(dados)] = dados
        self.posicao += len(dados)
        return len(dados)


def listar_zip(url: str) -> list[str]:
    with zipfile.ZipFile(ArquivoRemoto(url)) as zf:
        return zf.namelist()


def extrair_do_zip(url: str, membro: str, destino: Path) -> Path:
    """Baixa só `membro` de dentro do zip remoto e salva em `destino`."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BufferedReader(ArquivoRemoto(url), buffer_size=1024 * 1024)) as zf:
        with zf.open(membro) as origem, open(destino, "wb") as saida:
            shutil.copyfileobj(origem, saida, length=1024 * 1024)
    return destino


def ler_csv_tse(caminho, colunas: list[str] | None = None) -> pd.DataFrame:
    """Lê um CSV do TSE como texto, trocando os códigos de "sem informação" por nulo."""
    return pd.read_csv(
        caminho, sep=";", encoding="latin-1", dtype=str, usecols=colunas,
        na_values=SEM_INFORMACAO, keep_default_na=False,
    )
