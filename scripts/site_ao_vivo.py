"""Prepara o que o site precisa para a apuração ao vivo do 2º turno.

Grava em app/dados/:
- ao_vivo_prior.parquet: a previsão de antes da eleição para cada município
  (o ponto de partida da projeção) e os votos válidos esperados por eleitor;
- ao_vivo_config.json: os finalistas e os parâmetros da projeção.

    python scripts/site_ao_vivo.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from previsao_ao_vivo import preparar_prior  # noqa: E402

DESTINO = RAIZ / "app" / "dados"


def main() -> None:
    prior, parametros, nomes = preparar_prior()
    prior.to_parquet(DESTINO / "ao_vivo_prior.parquet", index=False)
    config = {
        "eleicao": 6258,
        "cargo": 1,
        "inicio_apuracao": "2026-10-25T17:00:00-03:00",
        # Governador, 2º turno: só o placar oficial (sem projeção); o DF vem primeiro
        "eleicao_governador": 6260,
        "ufs_governador_2t": ["df", "ac", "am", "es", "rn", "to"],
        "finalistas": {lado: {"nr_candidato": int(v["nr_candidato"]), "nm_urna": v["nm_urna"]}
                       for lado, v in nomes.items()},
        "parametros": asdict(parametros),
    }
    (DESTINO / "ao_vivo_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(prior)} municípios; finalistas: {config['finalistas']}")


if __name__ == "__main__":
    main()
