"""Exporta as principais tabelas do banco para CSV, para abrir no Power BI ou no Excel.

Os arquivos vão para dados/exportar/, com ";" como separador e vírgula decimal
(o padrão do Excel em português) e codificação UTF-8 com BOM, para o Excel
mostrar os acentos certos.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "dados" / "exportar"

TABELAS = {
    "votos_presidente": "votos para Presidente por eleição, turno, município e candidato",
    "comparecimento_presidente": "eleitores aptos, comparecimento, abstenção, brancos, nulos e válidos",
    "municipios": "cadastro de municípios com códigos TSE e IBGE",
    "transicao_turnos": "1º e 2º turno lado a lado, por município",
}

ARQUIVOS_EXTRAS = [
    "dados/modelo/validacao_historica.csv",
    "dados/modelo/previsao_2026_uf.csv",
    "dados/modelo/cenarios_transferencia_2026.csv",
    "dados/apuracao/teste_ao_vivo_2022_1t.csv",
    "dados/apuracao/teste_ao_vivo_2022_2t.csv",
    "dados/nulos/disputas_governador.csv",
    "dados/nulos/nulos_disputas_apertadas.csv",
]


def salvar(tabela: pd.DataFrame, destino: Path) -> None:
    tabela.to_csv(destino, sep=";", decimal=",", index=False, encoding="utf-8-sig")


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    banco = RAIZ / "dados" / "eleicoes.duckdb"
    if banco.exists():
        con = duckdb.connect(str(banco), read_only=True)
        for tabela, descricao in TABELAS.items():
            salvar(con.sql(f"select * from {tabela}").df(), DESTINO / f"{tabela}.csv")
            print(f"{tabela}.csv  ({descricao})")
        con.close()
    for extra in ARQUIVOS_EXTRAS:
        origem = RAIZ / extra
        if origem.exists():
            salvar(pd.read_csv(origem), DESTINO / origem.name)
            print(origem.name)
    print(f"-> {DESTINO}")


if __name__ == "__main__":
    main()
