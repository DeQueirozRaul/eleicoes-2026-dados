"""Leitura do RDV (Registro Digital do Voto) das urnas eletrônicas.

O RDV de cada urna lista todos os votos, embaralhados e sem identificar o
eleitor: para cada cargo, o tipo de voto e os dígitos digitados. Nos votos
nulos, os dígitos ficam registrados, o que permite saber, por exemplo, quantos
eleitores digitaram para governador o número de um candidato a presidente.

Formato: ASN.1 codificado em DER (especificação do TSE). Este leitor percorre a
estrutura TLV diretamente, sem depender do arquivo de especificação.

Tipos de voto encontrados nos arquivos (conferidos com o boletim de urna: a
soma de 4 e 6 bate com os nulos, 3 com os brancos e 2 com os votos nominais)
estão em TIPOS.
"""

from __future__ import annotations

import io
import time
import zipfile
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

TIPOS = {1: "legenda", 2: "nominal", 3: "branco", 4: "nulo", 6: "nulo sem número",
         7: "anulado (visto só para Senador em 2026, que tem duas vagas)"}
VALIDOS_OU_BRANCOS = {1, 2, 3}   # qualquer outro tipo é voto nulo/anulado
CARGOS = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal",
          7: "Deputado Estadual", 8: "Deputado Distrital"}


def _tlv(buf: bytes, pos: int) -> tuple[int, int, int]:
    """Lê um cabeçalho DER e devolve (tag, início do conteúdo, fim do conteúdo)."""
    tag = buf[pos]
    pos += 1
    if tag & 0x1F == 0x1F:          # tag em mais de um byte
        while buf[pos] & 0x80:
            pos += 1
        pos += 1
    tamanho = buf[pos]
    pos += 1
    if tamanho & 0x80:
        n = tamanho & 0x7F
        tamanho = int.from_bytes(buf[pos:pos + n], "big")
        pos += n
    return tag, pos, pos + tamanho


def _filhos(buf: bytes, inicio: int, fim: int) -> list[tuple[int, int, int]]:
    filhos = []
    while inicio < fim:
        tag, a, b = _tlv(buf, inicio)
        filhos.append((tag, a, b))
        inicio = b
    return filhos


def _inteiro(buf: bytes, item: tuple[int, int, int]) -> int:
    return int.from_bytes(buf[item[1]:item[2]], "big")


def ler_rdv(conteudo: bytes) -> Counter:
    """Conta os votos de um RDV por (código da eleição, cargo, tipo, dígitos)."""
    raiz = _filhos(conteudo, 0, len(conteudo))[0]
    corpo = _filhos(conteudo, raiz[1], raiz[2])[2]
    # a lista de eleições é o último campo de contexto do corpo: [0] em 2022, [1] em 2026
    eleicoes = [f for f in _filhos(conteudo, corpo[1], corpo[2]) if f[0] in (0xA0, 0xA1)][-1]
    votos: Counter = Counter()
    for _, a, b in _filhos(conteudo, eleicoes[1], eleicoes[2]):
        cod_eleicao, lista_cargos = _filhos(conteudo, a, b)[:2]
        eleicao = _inteiro(conteudo, cod_eleicao)
        for _, a2, b2 in _filhos(conteudo, lista_cargos[1], lista_cargos[2]):
            itens = _filhos(conteudo, a2, b2)
            if len(itens) < 3:          # cargo sem nenhum voto nesta urna
                continue
            cargo_item, _, lista_votos = itens[:3]
            cargo = _inteiro(conteudo, cargo_item)
            for _, a3, b3 in _filhos(conteudo, lista_votos[1], lista_votos[2]):
                campos = _filhos(conteudo, a3, b3)
                tipo = _inteiro(conteudo, campos[0])
                digitos = conteudo[campos[1][1]:campos[1][2]].decode("ascii") if len(campos) > 1 else ""
                if not (0 < eleicao < 100_000 and 0 < cargo < 100 and 0 < tipo < 50
                        and (digitos == "" or (digitos.isdigit() and len(digitos) <= 6))):
                    raise ValueError(f"estrutura inesperada: {(eleicao, cargo, tipo, digitos)!r}")
                votos[(eleicao, cargo, tipo, digitos)] += 1
    return votos


class ZipRemotoRDV:
    """Lê só os arquivos .rdv de dentro de um zip remoto de "arquivos transmitidos
    para totalização", pedindo ao servidor exatamente os bytes de cada um."""

    def __init__(self, url: str, sessao: requests.Session | None = None):
        from eleicoes.tse_arquivos import ArquivoRemoto

        self.url = url
        with zipfile.ZipFile(io.BufferedReader(ArquivoRemoto(url, bloco=1 << 20))) as zf:
            # 2022: "...-0102.rdv"; 2026: "...-rdv.dat"
            self.membros = [i for i in zf.infolist() if i.filename.endswith((".rdv", "-rdv.dat"))]

    def _baixar(self, info: zipfile.ZipInfo, sessao: requests.Session) -> bytes:
        inicio = info.header_offset
        fim = inicio + 30 + len(info.filename.encode()) + 512 + info.compress_size
        for tentativa in range(5):
            try:
                r = sessao.get(self.url, headers={"Range": f"bytes={inicio}-{fim}"}, timeout=60)
                r.raise_for_status()
                bruto = r.content
                break
            except requests.RequestException:
                if tentativa == 4:
                    raise
                time.sleep(2 ** tentativa)
        n_nome = int.from_bytes(bruto[26:28], "little")
        n_extra = int.from_bytes(bruto[28:30], "little")
        dados = bruto[30 + n_nome + n_extra:30 + n_nome + n_extra + info.compress_size]
        if info.compress_type == zipfile.ZIP_DEFLATED:
            return zlib.decompressobj(-15).decompress(dados)
        return dados

    def contar(self, paralelos: int = 4, membros: list[zipfile.ZipInfo] | None = None) -> Counter:
        """Soma os votos dos RDVs do zip (todos, ou só `membros`). Arquivos que não
        puderem ser lidos ficam em `self.falhas` (nome e erro), sem interromper."""
        membros = self.membros if membros is None else membros
        total: Counter = Counter()
        self.falhas: list[tuple[str, str]] = []

        def lote(membros):
            sessao = requests.Session()
            parcial: Counter = Counter()
            for info in membros:
                try:
                    parcial += ler_rdv(self._baixar(info, sessao))
                except (ValueError, IndexError, StopIteration, zlib.error) as erro:
                    self.falhas.append((info.filename, repr(erro)))
            return parcial

        fatias = [membros[i::paralelos] for i in range(paralelos)]
        with ThreadPoolExecutor(max_workers=paralelos) as executor:
            for parcial in executor.map(lote, fatias):
                total += parcial
        return total
