"""Roda o projeto inteiro, em ordem, explicando cada etapa.

    python scripts/rodar_tudo.py              # essencial: ~5 min, ~300 MB de download
    python scripts/rodar_tudo.py --completo   # tudo: ~1h30, ~2 GB de download

Cada etapa só refaz o que falta: rodar de novo é rápido.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

ESSENCIAL = [
    ("Baixar o 1º turno de 2026 (Presidente), município a município",
     ["coletar_ao_vivo.py", "--eleicao", "6257", "--cargo", "1"], "dados/ao_vivo/"),
    ("Baixar os resultados de Presidente de 2002 a 2022",
     ["baixar_historico.py"], "dados/brutos/"),
    ("Montar o banco DuckDB e rodar as checagens de qualidade",
     ["montar_base.py"], "dados/eleicoes.duckdb"),
    ("Testar o modelo do 2º turno nas eleições passadas e prever 2026",
     ["prever_2t.py"], "dados/modelo/validacao_historica.csv e previsao_2026*.csv"),
    ("Cenários de transferência dos votos dos eliminados",
     ["cenarios_transferencia.py"], "dados/modelo/cenarios_transferencia_2026.csv"),
]

COMPLETO = [
    ("Baixar os boletins de urna do 2º turno de 2022 (hora de chegada de cada urna)",
     ["baixar_boletins_2022.py", "--turno", "2"], "dados/brutos/bweb_2022_2t/"),
    ("Baixar os boletins de urna do 1º turno de 2022 (~1,2 GB, demora)",
     ["baixar_boletins_2022.py", "--turno", "1"], "dados/brutos/bweb_2022_1t/"),
    ("Reproduzir a apuração de 2022 e conferir com o histórico oficial",
     ["reproduzir_apuracao_2022.py"], "dados/apuracao/comparacao_curva_2022.csv"),
    ("Testar a previsão ao vivo na noite do 2º turno de 2022",
     ["testar_ao_vivo_2022.py", "--turno", "2"], "dados/apuracao/teste_ao_vivo_2022_2t.csv"),
    ("Testar a previsão ao vivo na noite do 1º turno de 2022",
     ["testar_ao_vivo_2022.py", "--turno", "1"], "dados/apuracao/teste_ao_vivo_2022_1t.csv"),
    ("Desenhar os gráficos das duas noites",
     ["grafico_apuracao_2022.py"], "docs/img/apuracao_2022_*.png"),
    ("Baixar o resultado de Governador por estado (2022 e 2026)",
     ["baixar_governador.py"], "dados/base/governador_uf.parquet"),
    ("Votos nulos com número de presidenciável nas disputas apertadas (~1 h)",
     ["nulos_disputas_apertadas.py"], "dados/nulos/nulos_disputas_apertadas.csv"),
    ("Exportar as tabelas para abrir no Power BI ou no Excel",
     ["exportar_tabelas.py"], "dados/exportar/"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--completo", action="store_true", help="roda também as etapas demoradas")
    args = parser.parse_args()

    etapas = ESSENCIAL + (COMPLETO if args.completo else [("Exportar as tabelas para abrir no Power BI ou no Excel",
                                                           ["exportar_tabelas.py"], "dados/exportar/")])
    inicio_geral = time.monotonic()
    for i, (descricao, comando, resultado) in enumerate(etapas, 1):
        print(f"\n[{i}/{len(etapas)}] {descricao}", flush=True)
        inicio = time.monotonic()
        retorno = subprocess.run([sys.executable, str(RAIZ / "scripts" / comando[0]), *comando[1:]], cwd=RAIZ)
        if retorno.returncode != 0:
            print(f"\nA etapa {i} falhou (código {retorno.returncode}). Veja a mensagem acima.")
            return retorno.returncode
        print(f"      ok em {time.monotonic() - inicio:.0f} s -> {resultado}", flush=True)

    print(f"\nPronto em {(time.monotonic() - inicio_geral) / 60:.1f} min. "
          "Os resultados estão em dados/ (e os gráficos em docs/img/).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
