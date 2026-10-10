"""Gera todos os arquivos pequenos que o site lê (app/dados/).

    python scripts/preparar_site.py              # todas as páginas
    python scripts/preparar_site.py base ao_vivo # só estas etapas

Cada etapa é um script scripts/site_<nome>.py. As etapas que baixam dados do
TSE e do IBGE só baixam o que ainda não está em dados/brutos/.
Antes: scripts/rodar_tudo.py (o banco e o modelo precisam existir).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

ETAPAS = {
    "base": "Início, Previsão do 2º turno, Apuração (teste de 2022) e Votos no número errado",
    "ao_vivo": "Ponto de partida da projeção ao vivo do 2º turno",
    "resultados": "Resultados e mapa (baixa a malha de municípios do IBGE e resultados do TSE)",
    "candidatos": "Perfil dos candidatos e patrimônio (baixa candidatos e bens de 2018, 2022 e 2026)",
    "eleitorado": "Eleitorado (baixa o perfil do eleitorado e a população do IBGE)",
    "conferencia": "Conferência dos dados (baixa a votação por seção de 2026)",
    "df": "Mapa do Distrito Federal",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("etapas", nargs="*", help=f"vazio = todas; opções: {', '.join(ETAPAS)}")
    args = parser.parse_args()
    if desconhecidas := set(args.etapas) - set(ETAPAS):
        parser.error(f"etapa desconhecida: {', '.join(sorted(desconhecidas))}")

    for nome in args.etapas or ETAPAS:
        script = RAIZ / "scripts" / f"site_{nome}.py"
        if not script.exists():
            print(f"[{nome}] ainda não existe ({script.name}); pulando")
            continue
        print(f"\n[{nome}] {ETAPAS[nome]}", flush=True)
        inicio = time.monotonic()
        retorno = subprocess.run([sys.executable, str(script)], cwd=RAIZ)
        if retorno.returncode != 0:
            print(f"A etapa {nome} falhou (código {retorno.returncode}).")
            return retorno.returncode
        print(f"      ok em {time.monotonic() - inicio:.0f} s", flush=True)
    tamanho = sum(f.stat().st_size for f in (RAIZ / "app" / "dados").iterdir()) / 2**20
    print(f"\nPronto. app/dados/ tem {tamanho:.1f} MB. Para ver: python -m streamlit run app/site.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
