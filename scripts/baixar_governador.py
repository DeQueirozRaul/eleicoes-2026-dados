"""Resultado para Governador por estado: 1º e 2º turnos de 2022 e 1º turno de 2026.

- 2022: "Votação nominal por município e zona" do Portal de Dados Abertos do TSE
  (só o CSV de cada UF é lido de dentro do zip nacional).
- 2026: arquivos ao vivo do site de resultados do TSE (eleição 6259, cargo 3).

Saída: dados/base/governador_uf.parquet, uma linha por eleição, turno, UF e
candidato, com os votos.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.tse_ao_vivo import UFS, ClienteTSE  # noqa: E402
from eleicoes.tse_arquivos import extrair_do_zip, url_odsele  # noqa: E402

DESTINO = RAIZ / "dados" / "base" / "governador_uf.parquet"
SEM_GOVERNADOR = {"ZZ", "BR"}


def governador_2022() -> pd.DataFrame:
    url = url_odsele("votacao_candidato_munzona", 2022)
    partes = []
    with tempfile.TemporaryDirectory() as tmp:
        for uf in [u.upper() for u in UFS if u.upper() not in SEM_GOVERNADOR]:
            csv = extrair_do_zip(url, f"votacao_candidato_munzona_2022_{uf}.csv", Path(tmp) / f"{uf}.csv")
            partes.append(duckdb.sql(f"""
                select 2022 as ano, NR_TURNO::int as turno, SG_UF as uf,
                       NR_CANDIDATO::int as nr_candidato, NM_URNA_CANDIDATO as nm_urna,
                       SG_PARTIDO as sg_partido,
                       sum(coalesce(QT_VOTOS_NOMINAIS_VALIDOS, QT_VOTOS_NOMINAIS)::bigint) as qt_votos
                from read_csv('{csv.as_posix()}', delim = ';', encoding = 'latin-1', all_varchar = true)
                where CD_CARGO = '3'
                group by all
            """).df())
            csv.unlink()
            print(f"2022 {uf}", flush=True)
    return pd.concat(partes, ignore_index=True)


def governador_2026() -> pd.DataFrame:
    cliente = ClienteTSE()
    partes = []
    for uf in [u for u in UFS if u.upper() not in SEM_GOVERNADOR]:
        resultado = cliente.resultado(6259, 3, uf)
        if resultado is None:
            continue
        c = resultado.candidatos
        partes.append(pd.DataFrame({
            "ano": 2026, "turno": 1, "uf": uf.upper(), "nr_candidato": c["nr_candidato"].astype(int),
            "nm_urna": c["nm_urna"], "sg_partido": c["sg_partido"], "qt_votos": c["qt_votos"],
        }))
    print("2026 ok", flush=True)
    return pd.concat(partes, ignore_index=True)


def main() -> None:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    tabela = pd.concat([governador_2022(), governador_2026()], ignore_index=True)
    tabela.to_parquet(DESTINO, index=False)
    print(f"{len(tabela)} linhas -> {DESTINO}")


if __name__ == "__main__":
    main()
