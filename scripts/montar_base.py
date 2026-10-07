"""Monta o banco DuckDB (dados/eleicoes.duckdb) a partir dos dados baixados.

Roda, em ordem, os arquivos de sql/*.sql e depois as checagens de qualidade em
sql/checagens/*.sql (cada checagem lista as linhas com problema; o esperado é
nenhuma).

Antes, rode:
    python scripts/baixar_historico.py
    python scripts/coletar_ao_vivo.py --eleicao 6257 --cargo 1
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.tse_ao_vivo import ClienteTSE  # noqa: E402

BANCO = RAIZ / "dados" / "eleicoes.duckdb"


def salvar_municipios() -> None:
    destino = RAIZ / "dados" / "base" / "municipios_2026.parquet"
    if destino.exists():
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    ClienteTSE().municipios(6257).to_parquet(destino, index=False)


def main() -> int:
    os.chdir(RAIZ)  # os SQLs usam caminhos relativos à raiz do projeto
    salvar_municipios()
    con = duckdb.connect(str(BANCO))

    for arquivo in sorted((RAIZ / "sql").glob("*.sql")):
        con.execute(arquivo.read_text(encoding="utf-8"))
        print(f"ok  {arquivo.name}")

    problemas = 0
    for arquivo in sorted((RAIZ / "sql" / "checagens").glob("*.sql")):
        linhas = con.execute(arquivo.read_text(encoding="utf-8")).df()
        if linhas.empty:
            print(f"ok  checagem {arquivo.name}")
        else:
            problemas += 1
            print(f"!!  checagem {arquivo.name}: {len(linhas)} linhas com problema")
            print(linhas.head(10).to_string(index=False))

    print(con.sql("""
        select ano, count(*) as municipios,
               sum(qt_validos_1t) as validos_1t, sum(qt_validos_2t) as validos_2t
        from transicao_turnos group by ano order by ano
    """))
    con.close()
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
