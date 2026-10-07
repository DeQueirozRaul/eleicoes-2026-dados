"""Baixa os resultados presidenciais históricos (2002 a 2022) do Portal de Dados Abertos do TSE.

De cada zip anual só é extraído o CSV nacional ("_BR"), que contém o cargo
de Presidente por município e zona eleitoral.

    python scripts/baixar_historico.py               # todos os anos
    python scripts/baixar_historico.py --anos 2022   # só um ano
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eleicoes.tse_arquivos import extrair_do_zip, url_odsele  # noqa: E402

PASTA = Path(__file__).resolve().parents[1] / "dados" / "brutos"
ANOS = [2002, 2006, 2010, 2014, 2018, 2022]
CONJUNTOS = ["votacao_candidato_munzona", "detalhe_votacao_munzona"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--anos", nargs="*", type=int, default=ANOS)
    parser.add_argument("--forcar", action="store_true", help="baixa de novo mesmo se o arquivo já existir")
    args = parser.parse_args()

    for ano in args.anos:
        for conjunto in CONJUNTOS:
            nome = f"{conjunto}_{ano}_BR.csv"
            destino = PASTA / nome
            if destino.exists() and not args.forcar:
                print(f"já existe: {destino.name}")
                continue
            extrair_do_zip(url_odsele(conjunto, ano), nome, destino)
            print(f"baixado:   {destino.name} ({destino.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
