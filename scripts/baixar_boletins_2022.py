"""Baixa os boletins de urna de 2022 (Presidente) e guarda só o necessário.

Os boletins trazem, para cada seção eleitoral, os votos e a hora em que o
boletim chegou ao TSE. São usados para reproduzir a apuração seção por seção.
Cada zip (um por UF) é baixado, as linhas de Presidente vão para um Parquet
em dados/brutos/bweb_2022_{turno}t/ e os arquivos temporários são apagados.

    python scripts/baixar_boletins_2022.py --turno 2
    python scripts/baixar_boletins_2022.py --turno 1     # ~1,2 GB de download
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import duckdb
import requests

RAIZ = Path(__file__).resolve().parents[1]
PACOTE = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2022-boletim-de-urna"
COLUNAS = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "QT_APTOS", "QT_COMPARECIMENTO",
           "NR_VOTAVEL", "QT_VOTOS", "DT_BU_RECEBIDO"]


def urls(turno: int) -> dict[str, str]:
    """URL do zip de cada UF, lida do catálogo do Portal de Dados Abertos."""
    recursos = requests.get(PACOTE, timeout=60).json()["result"]["resources"]
    prefixo = f"bweb_{turno}t_"
    saida = {}
    for r in recursos:
        nome = r["url"].rsplit("/", 1)[-1]
        if nome.startswith(prefixo) and nome.endswith(".zip"):
            saida[nome[len(prefixo):len(prefixo) + 2]] = r["url"]
    return saida


def baixar_uf(url: str, destino: Path, sessao: requests.Session) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        zip_tmp = Path(tmp) / "bu.zip"
        with sessao.get(url, stream=True, timeout=600) as resposta:
            resposta.raise_for_status()
            with open(zip_tmp, "wb") as f:
                shutil.copyfileobj(resposta.raw, f, length=4 * 1024 * 1024)
        with zipfile.ZipFile(zip_tmp) as zf:
            membro = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            csv_tmp = Path(zf.extract(membro, tmp))
        zip_tmp.unlink()
        colunas = ", ".join(COLUNAS)
        duckdb.sql(f"""
            copy (
                select {colunas}
                from read_csv('{csv_tmp}', delim = ';', encoding = 'latin-1', all_varchar = true)
                where CD_CARGO_PERGUNTA = '1'
            ) to '{destino}' (format parquet)
        """)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--turno", type=int, choices=[1, 2], default=2)
    args = parser.parse_args()

    pasta = RAIZ / "dados" / "brutos" / f"bweb_2022_{args.turno}t"
    pasta.mkdir(parents=True, exist_ok=True)
    sessao = requests.Session()
    for uf, url in sorted(urls(args.turno).items()):
        destino = pasta / f"{uf}.parquet"
        if destino.exists():
            continue
        baixar_uf(url, destino, sessao)
        print(f"{uf}: {destino.stat().st_size / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    sys.exit(main())
