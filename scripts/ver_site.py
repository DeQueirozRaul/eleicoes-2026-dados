"""Abre o site num navegador sem janela e tira uma foto de cada página, para
conferir o visual sem precisar abrir o navegador.

    python scripts/ver_site.py                      # todas as páginas
    python scripts/ver_site.py resultados nulos     # só estas (url_path definido em app/site.py)
    python scripts/ver_site.py --celular            # largura de celular

Precisa do Playwright (pip install playwright; python -m playwright install chromium).
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PAGINAS = ["", "resultados", "numero-errado", "candidatos", "patrimonio", "campanha", "eleitorado",
           "previsao", "apuracao", "df", "conferencia"]


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paginas", nargs="*", help="url_path das páginas (vazio = todas)")
    parser.add_argument("--saida", type=Path, default=RAIZ / "dados" / "fotos_site")
    parser.add_argument("--celular", action="store_true", help="largura de 390 px")
    parser.add_argument("--espera", type=float, default=8, help="segundos para a página terminar de desenhar")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    args.saida.mkdir(parents=True, exist_ok=True)
    porta = porta_livre()
    servidor = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app/site.py", "--server.port", str(porta),
         "--server.headless", "true"], cwd=RAIZ, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    erros = 0
    try:
        time.sleep(4)
        executavel = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium")
        with sync_playwright() as p:
            navegador = p.chromium.launch(executable_path=executavel if Path(executavel).exists() else None)
            largura = 390 if args.celular else 1300
            pagina = navegador.new_page(viewport={"width": largura, "height": 900})
            for nome in args.paginas or PAGINAS:
                pagina.goto(f"http://127.0.0.1:{porta}/{nome}", wait_until="networkidle")
                time.sleep(args.espera)
                altura = pagina.evaluate(
                    "() => Math.max(...[...document.querySelectorAll('section, div')].map(e => e.scrollHeight))")
                pagina.set_viewport_size({"width": largura, "height": min(max(altura, 900), 12000)})
                time.sleep(1.5)
                excecoes = pagina.locator("[data-testid='stException']").count()
                erros += excecoes
                arquivo = args.saida / f"{nome or 'inicio'}{'_celular' if args.celular else ''}.png"
                pagina.screenshot(path=str(arquivo), full_page=True)
                pagina.set_viewport_size({"width": largura, "height": 900})
                print(f"{arquivo}  {'ERRO NA PÁGINA' if excecoes else 'ok'}")
            navegador.close()
    finally:
        servidor.terminate()
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
