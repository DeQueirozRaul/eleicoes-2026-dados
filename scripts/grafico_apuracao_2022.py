"""Gráfico da noite de apuração de 2022: placar oficial × projeção ao vivo.

Lê dados/apuracao/teste_ao_vivo_2022_{turno}t.csv (gerado por
scripts/testar_ao_vivo_2022.py) e salva docs/img/apuracao_2022_{turno}t.png.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.ao_vivo import MINIMO_APURADO  # noqa: E402

# Cores neutras (não lembram partidos) e validadas para daltonismo.
SUPERFICIE, TINTA, TINTA_2, MUDO, GRADE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
PLACAR, PROJECAO = "#2a78d6", "#eb6834"

TITULOS = {
    1: ("1º turno de 2022: placar oficial × projeção ao vivo",
        "% de LULA nos votos dos dois primeiros colocados (JAIR BOLSONARO = 100% − valor)"),
    2: ("2º turno de 2022: placar oficial × projeção ao vivo",
        "% de LULA nos votos válidos (JAIR BOLSONARO = 100% − valor)"),
}


def pct(v: float) -> str:
    return f"{v * 100:.1f}%".replace(".", ",")


def grafico(turno: int) -> Path | None:
    arquivo = RAIZ / "dados" / "apuracao" / f"teste_ao_vivo_2022_{turno}t.csv"
    if not arquivo.exists():
        return None
    r = pd.read_csv(arquivo, parse_dates=["momento"])
    r = r[(r["pct_secoes"] >= 0.01) & (r["pct_secoes"] <= 0.995)]
    final = float(r["pct_a_final"].iloc[0])

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=150)
    fig.patch.set_facecolor(SUPERFICIE)
    ax.set_facecolor(SUPERFICIE)

    ax.axhline(0.5, color=GRADE, lw=1, zorder=1)
    ax.axhline(final, color=MUDO, lw=1.2, ls=(0, (4, 3)), zorder=2)
    proj = r[r["pct_secoes"] >= MINIMO_APURADO]   # o que teria sido publicado
    ax.fill_between(proj["momento"], proj["pct_a_inferior"], proj["pct_a_superior"],
                    color=PROJECAO, alpha=0.18, lw=0, zorder=3)
    ax.plot(r["momento"], r["pct_a_apurado"], color=PLACAR, lw=2, zorder=4)
    ax.plot(proj["momento"], proj["pct_a_mediana"], color=PROJECAO, lw=2, zorder=5)
    ax.annotate(f"projeção publicada a partir de {MINIMO_APURADO:.0%} apurado",
                (proj["momento"].iloc[0], proj["pct_a_superior"].iloc[0]), xytext=(0, 8),
                textcoords="offset points", color=MUDO, fontsize=9)

    # rótulos diretos
    fim = r.iloc[-1]
    ax.annotate("Resultado\nfinal " + pct(final), (r["momento"].iloc[-1], final), xytext=(10, 0),
                textcoords="offset points", color=TINTA_2, fontsize=10, va="center", annotation_clip=False)
    meio = r.iloc[len(r) // 3]
    meio_proj = proj.iloc[len(proj) // 3]
    ax.annotate("Placar oficial", (meio["momento"], meio["pct_a_apurado"]), xytext=(0, -16),
                textcoords="offset points", color=TINTA, fontsize=10, fontweight="bold")
    ax.annotate("Projeção ao vivo (faixa: intervalo de 90%)", (meio_proj["momento"], meio_proj["pct_a_superior"]),
                xytext=(0, 8), textcoords="offset points", color=TINTA, fontsize=10, fontweight="bold")

    # quando a liderança muda no placar e na projeção
    lado_final = final > 0.5
    do_lado_final = ((r["pct_a_apurado"] > 0.5) == lado_final)[::-1].cummin()[::-1]  # daí em diante não muda mais
    virada_placar = r[do_lado_final]
    if len(virada_placar) and len(virada_placar) < len(r):
        v = virada_placar.iloc[0]
        ax.scatter([v["momento"]], [v["pct_a_apurado"]], s=40, color=PLACAR, edgecolor=SUPERFICIE, lw=2, zorder=6)
        ax.annotate(f"{v['momento']:%Hh%M}: o placar oficial vira\n({pct(v['pct_secoes'])} apurado)",
                    (v["momento"], v["pct_a_apurado"]), xytext=(10, -34), textcoords="offset points",
                    color=TINTA_2, fontsize=9.5)

    ax.yaxis.set_major_formatter(lambda v, _: pct(v))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh%M"))
    ax.grid(axis="y", color=GRADE, lw=0.8)
    ax.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors=MUDO, length=0)
    baixo = min(r["pct_a_apurado"].min(), proj["pct_a_inferior"].min())
    alto = max(r["pct_a_apurado"].max(), proj["pct_a_superior"].max())
    ax.set_ylim(baixo - 0.003, alto + 0.006)

    titulo, subtitulo = TITULOS[turno]
    fig.text(0.06, 0.95, titulo, fontsize=15, fontweight="bold", color=TINTA)
    fig.text(0.06, 0.905, subtitulo, fontsize=10.5, color=TINTA_2)
    fig.text(0.06, 0.018, "Fonte: TSE (boletins de urna e histórico de totalização). Apuração reproduzida seção por seção,\n"
             "na hora em que cada boletim chegou ao TSE. Projeção: modelo deste projeto (github.com/DeQueirozRaul/eleicoes-2026-dados).",
             fontsize=8.5, color=MUDO, linespacing=1.4)
    fig.subplots_adjust(left=0.06, right=0.9, top=0.86, bottom=0.13)

    destino = RAIZ / "docs" / "img" / f"apuracao_2022_{turno}t.png"
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, facecolor=SUPERFICIE)
    plt.close(fig)
    return destino


def main() -> None:
    for turno in (1, 2):
        destino = grafico(turno)
        print(destino or f"turno {turno}: rode antes scripts/testar_ao_vivo_2022.py --turno {turno}")


if __name__ == "__main__":
    sys.exit(main())
