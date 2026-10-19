"""Acompanhamento da apuração dentro do site: coleta e projeção num só processo.

Na noite do 2º turno, o site não depende de nenhum computador ligado: uma
linha de execução (thread) em segundo plano faz, a cada minuto,

1. o download do andamento de cada UF (28 arquivos pequenos);
2. o download do resultado só dos municípios que mudaram desde a última vez;
3. a projeção (eleicoes.ao_vivo.projetar) com o que já foi apurado;

e guarda o histórico de cada rodada para o gráfico da noite.

O site cria um único Acompanhamento por processo (st.cache_resource), então
o TSE recebe as mesmas poucas requisições por minuto, não importa quantas
pessoas estejam com a página aberta.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
import requests

from eleicoes.ao_vivo import Parametros, projetar
from eleicoes.tse_ao_vivo import FUSO_BRASILIA, UFS, ClienteTSE


@dataclass
class Rodada:
    """O retrato de uma rodada de coleta."""

    momento: datetime
    pct_secoes: float                 # fração do eleitorado apurada (soma dos municípios)
    qt_a: int                         # votos de A apurados (soma dos municípios)
    qt_b: int
    pct_a_oficial: float | None = None   # placar oficial divulgado pelo TSE (arquivo do Brasil)
    pct_secoes_oficial: float | None = None
    pct_a_mediana: float | None = None
    pct_a_inferior: float | None = None
    pct_a_superior: float | None = None
    prob_a_vence: float | None = None
    municipios_com_votos: int = 0
    falhas: int = 0                   # arquivos que o TSE recusou nesta rodada (tentados de novo na próxima)


@dataclass
class Acompanhamento:
    """Coleta e projeta em segundo plano. Leia `historico`, `placar_ufs` e `erro`."""

    eleicao: int
    cargo: int
    nr_a: int
    nr_b: int
    prior: pd.DataFrame               # uf, cd_municipio_tse, logit_prior, taxa_validos
    parametros: Parametros = field(default_factory=Parametros)
    intervalo: int = 60
    paralelos: int = 6
    cenarios: int = 3000
    cliente: ClienteTSE = field(default_factory=ClienteTSE)

    def __post_init__(self):
        self.municipios: dict[tuple[str, str], dict] = {}
        self.versao: dict[tuple[str, str], tuple] = {}
        self.historico: list[Rodada] = []
        self.placar_ufs = pd.DataFrame()
        self.erro: str | None = None
        self.ultima_tentativa: datetime | None = None
        self.publicado = False
        self.encerrado = False
        self._trava = threading.Lock()
        self._linha: threading.Thread | None = None
        self._falhas = 0

    # --- coleta ------------------------------------------------------------
    def _seguro(self, funcao, *args):
        """Chama o TSE sem deixar uma falha derrubar a rodada. O servidor do TSE às vezes
        recusa um arquivo (ex.: 403 passageiro); ele vira None e é pedido de novo na
        próxima rodada."""
        try:
            return funcao(*args)
        except requests.RequestException:
            with self._trava:
                self._falhas += 1
            return None

    def _andamentos(self) -> pd.DataFrame:
        with ThreadPoolExecutor(max_workers=self.paralelos) as executor:
            partes = [a for a in executor.map(
                lambda uf: self._seguro(self.cliente.andamento, self.eleicao, uf), UFS) if a is not None]
        return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()

    def _votos(self, uf: str, municipio: str) -> tuple[str, str, int, int] | None:
        r = self._seguro(self.cliente.resultado, self.eleicao, self.cargo, uf, municipio)
        if r is None or r.candidatos.empty:
            return None
        numeros = r.candidatos["nr_candidato"].astype(int)
        qt_a = int(r.candidatos.loc[numeros == self.nr_a, "qt_votos"].sum())
        qt_b = int(r.candidatos.loc[numeros == self.nr_b, "qt_votos"].sum())
        return uf, municipio, qt_a, qt_b

    def rodar_uma_vez(self) -> Rodada | None:
        """Uma rodada completa. Devolve None se o TSE ainda não publicou nada."""
        self.ultima_tentativa = datetime.now(FUSO_BRASILIA)
        self._falhas = 0
        andamento = self._andamentos()
        if andamento.empty:
            return None
        self.publicado = True
        municipios = andamento[andamento["tp_abrangencia"] == "mun"]
        mudaram = []
        for m in municipios.itertuples():
            chave = (m.uf, m.cd_abrangencia)
            info = self.municipios.setdefault(chave, {"qt_a": 0, "qt_b": 0, "qt_aptos_apurados": 0})
            info["qt_aptos"] = m.qt_eleitores
            versao = (m.qt_secoes_totalizadas, m.dt_totalizacao)
            if m.qt_secoes_totalizadas > 0 and self.versao.get(chave) != versao:
                mudaram.append((chave, versao, m.qt_eleitores_secoes_totalizadas))
        with ThreadPoolExecutor(max_workers=self.paralelos) as executor:
            resultados = list(executor.map(lambda item: self._votos(*item[0]), mudaram))
        # o eleitorado apurado só avança junto com os votos: se o download de um
        # município falhar, ele fica como estava e é tentado de novo na próxima rodada
        for (chave, versao, apurados), votos in zip(mudaram, resultados):
            if votos is not None:
                self.municipios[chave].update(qt_a=votos[2], qt_b=votos[3], qt_aptos_apurados=apurados)
                self.versao[chave] = versao

        self.placar_ufs = self._placar_por_uf()
        rodada = self._projetar()
        brasil = self._seguro(self.cliente.resultado, self.eleicao, self.cargo, "br")
        if brasil is not None and not brasil.candidatos.empty:
            numeros = brasil.candidatos["nr_candidato"].astype(int)
            a = brasil.candidatos.loc[numeros == self.nr_a, "qt_votos"].sum()
            b = brasil.candidatos.loc[numeros == self.nr_b, "qt_votos"].sum()
            if a + b:
                rodada.pct_a_oficial = float(a / (a + b))
            if brasil.resumo["qt_secoes"]:
                rodada.pct_secoes_oficial = brasil.resumo["qt_secoes_totalizadas"] / brasil.resumo["qt_secoes"]
        rodada.falhas = self._falhas
        with self._trava:
            self.historico.append(rodada)
            self.erro = None
        self.encerrado = rodada.pct_secoes >= 1 and not mudaram
        return rodada

    def _placar_por_uf(self) -> pd.DataFrame:
        estado = self.estado()
        por_uf = estado.groupby("uf")[["qt_a", "qt_b", "qt_aptos", "qt_aptos_apurados"]].sum().reset_index()
        return por_uf.assign(pct_secoes=lambda d: d["qt_aptos_apurados"] / d["qt_aptos"].where(d["qt_aptos"] > 0))

    def estado(self) -> pd.DataFrame:
        """Uma linha por município, no formato que eleicoes.ao_vivo.projetar espera."""
        linhas = [{"uf": uf.upper(), "cd_municipio_tse": cd, **valores}
                  for (uf, cd), valores in self.municipios.items()]
        estado = pd.DataFrame(linhas, columns=["uf", "cd_municipio_tse", "qt_aptos", "qt_aptos_apurados",
                                               "qt_a", "qt_b"])
        estado = estado.merge(self.prior, on=["uf", "cd_municipio_tse"], how="left")
        estado["logit_prior"] = estado["logit_prior"].fillna(0.0)
        estado["taxa_validos"] = estado["taxa_validos"].fillna(estado["taxa_validos"].median())
        return estado

    def _projetar(self) -> Rodada:
        estado = self.estado()
        agora = datetime.now(FUSO_BRASILIA)
        aptos = estado["qt_aptos"].sum()
        pct_secoes = float(estado["qt_aptos_apurados"].sum() / aptos) if aptos else 0.0
        rodada = Rodada(momento=agora, pct_secoes=pct_secoes, qt_a=int(estado["qt_a"].sum()),
                        qt_b=int(estado["qt_b"].sum()),
                        municipios_com_votos=int((estado["qt_a"] + estado["qt_b"] > 0).sum()))
        if rodada.qt_a + rodada.qt_b > 0:
            with np.errstate(over="ignore"):
                p = projetar(estado, self.parametros, cenarios=self.cenarios, semente=len(self.historico))
            rodada.pct_a_mediana, rodada.pct_a_inferior = p.pct_a_mediana, p.pct_a_inferior
            rodada.pct_a_superior, rodada.prob_a_vence = p.pct_a_superior, p.prob_a_vence
        return rodada

    # --- execução em segundo plano -------------------------------------------------
    def _laco(self) -> None:
        while True:
            inicio = time.monotonic()
            try:
                rodada = self.rodar_uma_vez()
                espera = self.intervalo if rodada is not None else 300   # antes de começar: a cada 5 min
                if self.encerrado:
                    espera = 1800
            except Exception as erro:  # noqa: BLE001 - o laço não pode morrer; o erro aparece na página
                with self._trava:
                    self.erro = f"{type(erro).__name__}: {erro}"
                espera = self.intervalo
            time.sleep(max(5, espera - (time.monotonic() - inicio)))

    def iniciar(self) -> "Acompanhamento":
        if self._linha is None:
            self._linha = threading.Thread(target=self._laco, name="acompanhamento", daemon=True)
            self._linha.start()
        return self

    def tabela_historico(self) -> pd.DataFrame:
        with self._trava:
            return pd.DataFrame([vars(r) for r in self.historico])
