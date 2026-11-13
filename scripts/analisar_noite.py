"""A noite do 2º turno de 2026: a projeção ao vivo comparada com o resultado final.

Lê o que scripts/gravar_noite.py gravou em dados/ao_vivo/ e salva para o site:

    app/dados/noite_2026_2t.parquet          uma linha por rodada, com as mesmas colunas do teste de 2022
                                             (placar oficial, projeção, erro, final dentro da margem)
    app/dados/noite_2026_governador.parquet  placar de Governador nas UFs com 2º turno, por rodada

e o gráfico docs/img/apuracao_2026_2t.png, e imprime os números usados em docs/previsao.md.

    python scripts/analisar_noite.py             # resultado final lido do TSE (ou, se falhar, da gravação)
    python scripts/analisar_noite.py --sem-tse   # só a gravação
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from eleicoes.ao_vivo import MINIMO_APURADO  # noqa: E402
from eleicoes.tse_ao_vivo import ClienteTSE  # noqa: E402

GRAVACAO = RAIZ / "dados" / "ao_vivo"
DADOS_SITE = RAIZ / "app" / "dados"
FUSO = "America/Sao_Paulo"
RECOMECO = "2026-10-25 19:00"
FIM_COBERTURA = 0.995           # como na página: depois disso a margem é mais estreita que o que ainda muda   # a votação foi prorrogada até as 19h e a divulgação ficou parada antes disso


def hora_local(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, utc=True).dt.tz_convert(FUSO).dt.tz_localize(None)


def final_do_tse(eleicao: int, nr_a: int, nr_b: int) -> dict | None:
    try:
        r = ClienteTSE().resultado(eleicao, 1, "br")
    except requests.RequestException as erro:
        print(f"resultado final: TSE indisponível ({erro}); usando a gravação")
        return None
    numeros = r.candidatos["nr_candidato"].astype(int)
    a = int(r.candidatos.loc[numeros == nr_a, "qt_votos"].sum())
    b = int(r.candidatos.loc[numeros == nr_b, "qt_votos"].sum())
    return {"qt_a": a, "qt_b": b, "pct_secoes": r.resumo["qt_secoes_totalizadas"] / r.resumo["qt_secoes"]}


def noite(gravacao: pd.DataFrame, final: dict) -> pd.DataFrame:
    g = gravacao.assign(momento=hora_local(gravacao["momento"])).sort_values("momento")
    g = g[g["momento"] >= pd.Timestamp(RECOMECO)].reset_index(drop=True)
    pct_final = final["qt_a"] / (final["qt_a"] + final["qt_b"])
    # quando o arquivo do Brasil não veio (TSE recusou), repete o último placar recebido
    recebido = g["pct_a_oficial"].notna()
    r = pd.DataFrame({
        "momento": g["momento"],
        "pct_a_apurado": g["pct_a_oficial"].ffill(),
        "pct_secoes": g["pct_secoes_oficial"].ffill(),
        "placar_recebido": recebido,
        "pct_secoes_projecao": g["pct_secoes"],   # o que a projeção já tinha visto
    })
    publicada = g["pct_secoes"] >= MINIMO_APURADO
    for coluna in ("pct_a_mediana", "pct_a_inferior", "pct_a_superior", "prob_a_vence"):
        r[coluna] = g[coluna].where(publicada)
    r["falhas"] = g["falhas"]
    r["pct_a_final"] = pct_final
    r["qt_a_final"], r["qt_b_final"], r["pct_secoes_final"] = final["qt_a"], final["qt_b"], final["pct_secoes"]
    r["erro_projecao_pp"] = (r["pct_a_mediana"] - pct_final) * 100
    r["erro_placar_pp"] = (r["pct_a_apurado"] - pct_final) * 100
    r["final_no_intervalo"] = (r["pct_a_inferior"].le(pct_final) & r["pct_a_superior"].ge(pct_final)).where(publicada)
    return r[r["pct_a_apurado"].notna()].reset_index(drop=True)


def governador(gravacao: pd.DataFrame) -> pd.DataFrame:
    g = gravacao.assign(momento=hora_local(gravacao["momento"]))
    g = g[g["momento"] >= pd.Timestamp(RECOMECO)].copy()
    g["nr_candidato"] = g["nr_candidato"].astype(str)
    validos = g.groupby(["momento", "uf"])["qt_votos"].transform("sum")
    g["pct_validos"] = (g["qt_votos"] / validos).where(validos > 0)
    return g[["momento", "uf", "pct_secoes", "nr_candidato", "nm_urna", "sg_partido", "qt_votos", "pct_validos"]]


def resumo(r: pd.DataFrame, nome_a: str, nome_b: str) -> None:
    final = r["pct_a_final"].iloc[0]
    print(f"Resultado final: {nome_a} {final:.4%} × {nome_b} {1 - final:.4%} "
          f"({r['pct_secoes_final'].iloc[0]:.3%} das seções)")
    print("\nErro em relação ao final, no momento em que o TSE chegou a cada % apurado (pontos):")
    for alvo in (0.05, 0.10, 0.25, 0.50, 0.75, 0.90):
        linha = r[r["pct_secoes"] >= alvo].iloc[0]
        print(f"  {alvo:4.0%} ({linha['momento']:%H:%M}) placar {linha['erro_placar_pp']:+.2f} | projeção "
              f"{linha['erro_projecao_pp']:+.2f} (a projeção tinha visto {linha['pct_secoes_projecao']:.1%})")
    print("\nErro da projeção quando ela mesma tinha visto cada % do eleitorado:")
    for alvo in (0.05, 0.10, 0.25, 0.50, 0.75, 0.90):
        linha = r[r["pct_secoes_projecao"] >= alvo].iloc[0]
        print(f"  {alvo:4.0%} ({linha['momento']:%H:%M}) projeção {linha['erro_projecao_pp']:+.2f} "
              f"[{linha['pct_a_inferior']:.2%}, {linha['pct_a_superior']:.2%}]")

    pub = r[r["pct_a_mediana"].notna()]
    ate = pub[pub["pct_secoes"] <= FIM_COBERTURA]
    print(f"\nProjeção publicada desde {pub['momento'].iloc[0]:%H:%M}; final dentro da margem de 90% em "
          f"{ate['final_no_intervalo'].astype(float).mean():.0%} das {len(ate)} rodadas até {FIM_COBERTURA:.1%} apurado "
          f"({pub['final_no_intervalo'].astype(float).mean():.0%} das {len(pub)}, contando o fim da noite)")
    fora = pub[~pub["final_no_intervalo"].astype(bool)]
    if len(fora):
        print(f"  fora da margem: {len(fora)} rodadas, de {fora['momento'].min():%H:%M} a {fora['momento'].max():%H:%M}")
        dentro_desde = pub[pub["momento"] > fora["momento"].max()]
        if len(dentro_desde):
            print(f"  dentro da margem sem interrupção desde {dentro_desde['momento'].iloc[0]:%H:%M}")
    largura = (pub["pct_a_superior"] - pub["pct_a_inferior"]) * 100
    for faixa, (de, ate) in {"5–10%": (0.05, 0.10), "10–25%": (0.10, 0.25), "25–50%": (0.25, 0.50),
                             "50–75%": (0.50, 0.75)}.items():
        sel = pub["pct_secoes_projecao"].between(de, ate, inclusive="left")
        if sel.any():
            print(f"  largura média da margem com {faixa} visto: {largura[sel].mean():.1f} pontos")

    a_vence = final > 0.5
    lado_placar = (r["pct_a_apurado"] > 0.5) == a_vence
    errado = r[~lado_placar]
    if len(errado):
        virada = r[r["momento"] > errado["momento"].max()].iloc[0]
        print(f"\nPlacar oficial do lado do vencedor desde {virada['momento']:%H:%M} ({virada['pct_secoes']:.1%} apurado)")
    lado_proj = (pub["pct_a_mediana"] > 0.5) == a_vence
    print(f"Projeção do lado do vencedor em {lado_proj.mean():.0%} das rodadas publicadas")
    chance = pub["prob_a_vence"] if a_vence else 1 - pub["prob_a_vence"]
    abaixo = pub[chance < 0.9]
    desde = pub[pub["momento"] > abaixo["momento"].max()] if len(abaixo) else pub
    if len(desde):
        print(f"Chance do vencedor acima de 90% sem interrupção desde {desde['momento'].iloc[0]:%H:%M}")
    print(f"Rodadas sem o arquivo do Brasil (TSE recusou): {(~r['placar_recebido']).sum()} de {len(r)}")


def grafico(r: pd.DataFrame, nome_a: str, nome_b: str) -> Path:
    from grafico_apuracao_2022 import desenhar

    r = r[r["pct_secoes"] >= 0.01]   # como no gráfico de 2022: sem os primeiríssimos boletins
    proj = r[r["pct_a_mediana"].notna()]
    return desenhar(
        r, proj, float(r["pct_a_final"].iloc[0]),
        "2º turno de 2026: placar oficial × projeção ao vivo",
        f"% de {nome_a} nos votos válidos ({nome_b} = 100% − valor)",
        "Fonte: TSE (resultados divulgados ao vivo em 25/10/2026, lidos a cada minuto). Projeção: modelo deste projeto,\n"
        "o mesmo do site (github.com/DeQueirozRaul/eleicoes-2026-dados). A divulgação ficou parada das 17h06 às 19h01.",
        RAIZ / "docs" / "img" / "apuracao_2026_2t.png",
        placar_em=(r["momento"] < "2026-10-25 19:06").mean(), placar_dy=-18, aviso_a_esquerda=True,
        projecao_em=(proj["momento"] < "2026-10-25 20:12").mean(), projecao_abaixo=True, virada_dy=14)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sem-tse", action="store_true", help="não buscar o resultado final no TSE")
    args = parser.parse_args()
    config = json.loads((DADOS_SITE / "ao_vivo_config.json").read_text(encoding="utf-8"))
    a, b = config["finalistas"]["A"], config["finalistas"]["B"]

    gravacao = pd.read_csv(GRAVACAO / f"noite_e{config['eleicao']}.csv")
    final = None if args.sem_tse else final_do_tse(config["eleicao"], a["nr_candidato"], b["nr_candidato"])
    if final is None:
        ultima = gravacao.dropna(subset=["pct_a_oficial"]).sort_values("pct_secoes_oficial").iloc[-1]
        validos = ultima["qt_a"] + ultima["qt_b"]
        final = {"qt_a": round(ultima["pct_a_oficial"] * validos), "qt_b": round((1 - ultima["pct_a_oficial"]) * validos),
                 "pct_secoes": ultima["pct_secoes_oficial"]}
    r = noite(gravacao, final)
    r.to_parquet(DADOS_SITE / "noite_2026_2t.parquet", index=False)
    print(grafico(r, a["nm_urna"], b["nm_urna"]))

    gov = governador(pd.read_csv(GRAVACAO / f"noite_governador_e{config.get('eleicao_governador', 6260)}.csv",
                                 dtype={"nr_candidato": str}))
    gov.to_parquet(DADOS_SITE / "noite_2026_governador.parquet", index=False)

    resumo(r, a["nm_urna"], b["nm_urna"])
    print("\nGovernador (última leitura de cada UF):")
    ultimo = gov[gov["momento"] == gov.groupby("uf")["momento"].transform("max")]
    for uf, linhas in ultimo.groupby("uf"):
        nomes = " × ".join(f"{l.nm_urna} {l.pct_validos:.2%}" for l in linhas.sort_values("nm_urna").itertuples())
        print(f"  {uf} ({linhas['pct_secoes'].iloc[0]:.2%} das seções): {nomes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
