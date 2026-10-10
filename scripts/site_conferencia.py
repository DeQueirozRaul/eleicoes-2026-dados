"""Prepara os dados da página "Conferência dos dados" do site.

A página mostra que o projeto confere os dados antes de concluir:

1. A soma das seções bate com o resultado oficial? Soma os votos de cada uma
   das ~499 mil seções (Presidente, 1º turno de 2026) por UF, município e
   candidato e compara com o resultado oficial (tabela votos_presidente, que
   vem dos arquivos de resultado do TSE).
2. Reprodução da apuração de 2022 × histórico oficial de totalização
   (lê dados/apuracao/comparacao_curva_2022.csv, de scripts/reproduzir_apuracao_2022.py).
3. Leitura voto a voto (RDV) × resultado oficial nas 9 disputas de Governador
   (lê dados/nulos/nulos_disputas_apertadas.csv, de scripts/nulos_disputas_apertadas.py).
4. Lei de Benford: 1º e 2º dígito dos votos por seção e por município, para
   todos os candidatos, comparados com a curva de Benford.
5. Checagens automáticas: roda sql/checagens/*.sql no banco e confere o
   coletor ao vivo (soma dos municípios × total do Brasil).
6. Seções fora do padrão: seções pequenas, não instaladas, com votação em
   cédula ou boletim recuperado, e com todos os votos válidos para um só
   candidato, com o tipo de local (exterior, presídio, aldeia...).

Fontes (Portal de Dados Abertos do TSE, pacote "resultados-2026"):
- Presidente - Votação por seção eleitoral - 2026:
  https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_2026_BR.zip
- Detalhe da apuração por seção eleitoral (só o arquivo de Presidente, _BR.csv):
  https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_secao/detalhe_votacao_secao_2026.zip
- Candidatos e situação da candidatura (só os arquivos _BR.csv):
  https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2026.zip
  https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand_complementar/consulta_cand_complementar_2026.zip
Catálogo: https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2026

Os arquivos brutos ficam em dados/brutos/conferencia/ (fora do git). Os CSVs
grandes são lidos uma vez, resumidos em Parquet e apagados; rodar de novo não
baixa nada outra vez. O resultado vai para app/dados/conferencia_*.parquet.

Antes: scripts/montar_base.py (banco), e, para as partes 2 e 3,
scripts/reproduzir_apuracao_2022.py e scripts/nulos_disputas_apertadas.py.

    python scripts/site_conferencia.py
"""

from __future__ import annotations

import re
import shutil
import sys
import time
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.tse_arquivos import CDN, extrair_do_zip, url_odsele  # noqa: E402

DADOS = RAIZ / "dados"
BRUTOS = DADOS / "brutos" / "conferencia"
DESTINO = RAIZ / "app" / "dados"
BANCO = DADOS / "eleicoes.duckdb"

URL_VOTACAO_SECAO = f"{CDN}/votacao_secao/votacao_secao_2026_BR.zip"   # só Presidente
URL_DETALHE_SECAO = url_odsele("detalhe_votacao_secao", 2026)
URL_CANDIDATOS = url_odsele("consulta_cand", 2026)
URL_CANDIDATOS_COMPLEMENTAR = url_odsele("consulta_cand_complementar", 2026)

# Códigos do TSE que não são candidatos no arquivo de votação por seção.
BRANCO, NULO = 95, 96
PARALELOS = 3   # o TSE devolve 403 com muitas conexões ao mesmo tempo


# ---------------------------------------------------------------------------
# Funções puras (testadas em tests/test_site_conferencia.py)
# ---------------------------------------------------------------------------

def benford(posicao: int = 1) -> pd.Series:
    """Proporção esperada de cada dígito pela lei de Benford.

    posicao=1: dígitos 1 a 9, P(d) = log10(1 + 1/d).
    posicao=2: dígitos 0 a 9, P(d) = soma, para k de 1 a 9, de log10(1 + 1/(10k + d)).
    """
    if posicao == 1:
        digitos = np.arange(1, 10)
        valores = np.log10(1 + 1 / digitos)
    elif posicao == 2:
        digitos = np.arange(0, 10)
        valores = np.array([np.log10(1 + 1 / (10 * np.arange(1, 10) + d)).sum() for d in digitos])
    else:
        raise ValueError("só o 1º e o 2º dígito")
    return pd.Series(valores, index=pd.Index(digitos, name="digito"), name="benford")


def digito(valores, posicao: int = 1) -> pd.Series:
    """O dígito na `posicao` (1 = primeiro) de cada número inteiro positivo.

    Números sem esse dígito (zero no 1º dígito; menores que 10 no 2º) ficam de
    fora: a lei de Benford não diz nada sobre eles.
    """
    serie = pd.Series(valores, dtype="int64")
    serie = serie[serie >= 10 ** (posicao - 1)]
    return serie.astype(str).str[posicao - 1].astype(int).reset_index(drop=True)


def distribuicao(digitos: pd.Series, posicao: int = 1) -> pd.DataFrame:
    """Quantidade e proporção de cada dígito, ao lado da proporção de Benford."""
    esperado = benford(posicao)
    contagem = digitos.value_counts().reindex(esperado.index, fill_value=0)
    total = contagem.sum()
    return pd.DataFrame({
        "digito": esperado.index,
        "quantidade": contagem.to_numpy(),
        "proporcao": contagem.to_numpy() / total if total else np.nan,
        "benford": esperado.to_numpy(),
    })


def desvio_medio(observada, esperada) -> float:
    """Distância média entre duas distribuições (média do valor absoluto da
    diferença, em fração). 0,01 = 1 ponto percentual por dígito, em média."""
    return float(np.mean(np.abs(np.asarray(observada, float) - np.asarray(esperada, float))))


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()


PRISIONAL = re.compile(
    r"PRISIONA|PENITENCI|PRESIDIO|CADEIA PUBLICA|DETENCAO|CASA DE PRISAO|SOCIOEDUCA|CUSTODIA|RESSOCIALIZA"
    r"|INTERNACAO|\bCDP\b|\bCPP\b|\bPENAL\b|CARCER|\bAPAC\b|\bUPP?R|CENTRO DE RECUPERACAO"
    r"|FUNDACAO CASA|FUNASE|\bCASE\b|IASES|DEGASE|\bUIP?\b|SEMILIBERDADE|CENTRO EDUCACIONAL DO JOVEM"
    r"|CENTRO DE ATENDIMENTO .*ADOLESCENTE|UNIDADE DE ATENDIMENTO .*ADOLESCENTE")
INDIGENA = re.compile(r"ALDEIA|INDIGENA|TEKOA|TEKOHA|TERRA IND|\bEEIEF\b")


def tipo_de_local(nome_local: str | None, uf: str) -> str:
    """Classifica o local de votação pelo nome (critério simples, o mesmo para
    todas as seções): exterior, presídio ou unidade para adolescentes, aldeia ou
    escola indígena, ou outro. Um local indígena sem "aldeia" ou "indígena" no
    nome cai em "outro"; por isso as contagens são um piso, não um total."""
    if uf == "ZZ":
        return "exterior"
    nome = _sem_acento(nome_local or "")
    if PRISIONAL.search(nome):
        return "presídio ou unidade para adolescentes"
    if INDIGENA.search(nome):
        return "aldeia ou escola indígena"
    return "outro"


# ---------------------------------------------------------------------------
# Download (no máximo 3 conexões ao mesmo tempo, com novas tentativas)
# ---------------------------------------------------------------------------

def _espera(tentativa: int, erro: Exception, url: str) -> None:
    segundos = min(120, 10 * 2 ** tentativa)
    print(f"   falhou ({erro.__class__.__name__}: {str(erro)[:80]}); nova tentativa em {segundos} s: {url}", flush=True)
    time.sleep(segundos)


def baixar(url: str, destino: Path, tentativas: int = 6) -> Path:
    """Baixa `url` em `destino`, continuando de onde parou (HTTP Range) se a
    conexão cair. Se `destino` já existe, não baixa de novo."""
    if destino.exists():
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    for tentativa in range(tentativas):
        try:
            with requests.Session() as sessao:
                tamanho = int(sessao.head(url, timeout=60, allow_redirects=True).headers["Content-Length"])
                inicio = parcial.stat().st_size if parcial.exists() else 0
                if inicio < tamanho:
                    cabecalho = {"Range": f"bytes={inicio}-"} if inicio else {}
                    with sessao.get(url, headers=cabecalho, stream=True, timeout=120) as resposta:
                        resposta.raise_for_status()
                        modo = "ab" if resposta.status_code == 206 else "wb"
                        with open(parcial, modo) as saida:
                            for bloco in resposta.iter_content(4 * 1024 * 1024):
                                saida.write(bloco)
            if parcial.stat().st_size != tamanho:
                raise IOError(f"baixou {parcial.stat().st_size} de {tamanho} bytes")
            parcial.rename(destino)
            print(f"   baixado: {destino.name} ({tamanho / 1e6:.0f} MB)", flush=True)
            return destino
        except (requests.RequestException, IOError, KeyError) as erro:
            if tentativa == tentativas - 1:
                raise
            _espera(tentativa, erro, url)
    return destino


def baixar_membro(url: str, membro: str, destino: Path, tentativas: int = 6) -> Path:
    """Baixa só um arquivo de dentro do zip remoto (sem baixar o zip inteiro)."""
    if destino.exists():
        return destino
    parcial = destino.with_name(destino.name + ".parcial")
    for tentativa in range(tentativas):
        try:
            extrair_do_zip(url, membro, parcial)
            parcial.rename(destino)
            print(f"   baixado: {membro} ({destino.stat().st_size / 1e6:.0f} MB)", flush=True)
            return destino
        except (requests.RequestException, zipfile.BadZipFile, OSError) as erro:
            if tentativa == tentativas - 1:
                raise
            _espera(tentativa, erro, url)
    return destino


# ---------------------------------------------------------------------------
# Leitura dos arquivos grandes (uma vez só; depois fica o Parquet resumido)
# ---------------------------------------------------------------------------

VOTOS_SECAO = BRUTOS / "votos_secao_presidente_2026_1t.parquet"
DETALHE_SECAO = BRUTOS / "detalhe_secao_presidente_2026_1t.parquet"
CANDIDATOS = BRUTOS / "consulta_cand_2026_BR.csv"
CANDIDATOS_COMPLEMENTAR = BRUTOS / "consulta_cand_complementar_2026_BR.csv"


def preparar_votos_secao(con: duckdb.DuckDBPyConnection) -> None:
    """Votos por seção e número votado (1 GB de CSV) -> Parquet de ~20 MB."""
    if VOTOS_SECAO.exists():
        return
    zip_local = BRUTOS / "votacao_secao_2026_BR.zip"
    csv = BRUTOS / "votacao_secao_2026_BR.csv"
    if not csv.exists():
        with zipfile.ZipFile(zip_local) as zf, zf.open("votacao_secao_2026_BR.csv") as origem, \
                open(csv, "wb") as saida:
            shutil.copyfileobj(origem, saida, length=4 * 1024 * 1024)
    con.execute(f"""
        copy (
            select SG_UF as uf, lpad(CD_MUNICIPIO, 5, '0') as cd_municipio_tse,
                   NR_ZONA::int as zona, NR_SECAO::int as secao,
                   NR_VOTAVEL::int as nr_votavel, any_value(NM_VOTAVEL) as nm_votavel,
                   sum(QT_VOTOS::int)::int as qt_votos
            from read_csv('{csv.as_posix()}', delim = ';', encoding = 'latin-1', header = true,
                          all_varchar = true)
            where CD_CARGO = '1' and NR_TURNO = '1'
            group by all
        ) to '{VOTOS_SECAO.as_posix()}' (format parquet)
    """)
    csv.unlink()


def preparar_detalhe_secao(con: duckdb.DuckDBPyConnection) -> None:
    """Eleitores, comparecimento, brancos, nulos e local de cada seção -> Parquet."""
    if DETALHE_SECAO.exists():
        return
    csv = BRUTOS / "detalhe_votacao_secao_2026_BR.csv"
    con.execute(f"""
        copy (
            select SG_UF as uf, lpad(CD_MUNICIPIO, 5, '0') as cd_municipio_tse, NM_MUNICIPIO as nm_municipio,
                   NR_ZONA::int as zona, NR_SECAO::int as secao,
                   QT_APTOS::int as qt_aptos, QT_COMPARECIMENTO::int as qt_comparecimento,
                   QT_VOTOS_NOMINAIS::int as qt_nominais, QT_VOTOS_BRANCOS::int as qt_brancos,
                   QT_VOTOS_NULOS::int as qt_nulos, NM_LOCAL_VOTACAO as nm_local,
                   DS_ORIGEM_VOTO as origem, ST_SECAO_INSTALADA = 'Sim' as instalada
            from read_csv('{csv.as_posix()}', delim = ';', encoding = 'latin-1', header = true,
                          all_varchar = true)
            where CD_CARGO = '1' and NR_TURNO = '1'
        ) to '{DETALHE_SECAO.as_posix()}' (format parquet)
    """)
    csv.unlink()


def baixar_tudo() -> None:
    BRUTOS.mkdir(parents=True, exist_ok=True)
    tarefas = []
    if not VOTOS_SECAO.exists():
        tarefas.append(lambda: baixar(URL_VOTACAO_SECAO, BRUTOS / "votacao_secao_2026_BR.zip"))
    if not DETALHE_SECAO.exists():
        tarefas.append(lambda: baixar_membro(URL_DETALHE_SECAO, "detalhe_votacao_secao_2026_BR.csv",
                                             BRUTOS / "detalhe_votacao_secao_2026_BR.csv"))
    tarefas.append(lambda: baixar_membro(URL_CANDIDATOS, "consulta_cand_2026_BR.csv", CANDIDATOS))
    tarefas.append(lambda: baixar_membro(URL_CANDIDATOS_COMPLEMENTAR, "consulta_cand_complementar_2026_BR.csv",
                                         CANDIDATOS_COMPLEMENTAR))
    with ThreadPoolExecutor(max_workers=PARALELOS) as executor:
        for futuro in [executor.submit(t) for t in tarefas]:
            futuro.result()


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------

def gravar(tabela: pd.DataFrame, nome: str) -> None:
    caminho = DESTINO / f"{nome}.parquet"
    tabela.to_parquet(caminho, index=False)
    print(f"  {caminho.relative_to(RAIZ)}: {len(tabela)} linhas, {caminho.stat().st_size / 1024:.0f} KB")


# ---------------------------------------------------------------------------
# 1. Soma das seções × resultado oficial
# ---------------------------------------------------------------------------

def candidatos_fora_do_oficial(con: duckdb.DuckDBPyConnection, numeros: list[int]) -> pd.DataFrame:
    """Nome de urna, partido e situação, no cadastro do TSE, dos números que têm
    voto nas seções mas não aparecem no resultado oficial."""
    if not numeros:
        return pd.DataFrame(columns=["nr_candidato", "nm_urna", "sg_partido", "situacao", "destino_votos"])
    lista = ", ".join(f"'{n}'" for n in numeros)
    return con.sql(f"""
        select c.NR_CANDIDATO::int as nr_candidato, c.NM_URNA_CANDIDATO as nm_urna, c.SG_PARTIDO as sg_partido,
               x.DS_SITUACAO_CANDIDATO_TOT as situacao, x.NM_TIPO_DESTINACAO_VOTOS as destino_votos
        from read_csv('{CANDIDATOS.as_posix()}', delim = ';', encoding = 'latin-1', all_varchar = true) c
        join read_csv('{CANDIDATOS_COMPLEMENTAR.as_posix()}', delim = ';', encoding = 'latin-1',
                      all_varchar = true) x using (SQ_CANDIDATO)
        where c.CD_CARGO = '1' and c.NR_TURNO = '1' and c.NR_CANDIDATO in ({lista})
          and x.ST_CANDIDATO_INSERIDO_URNA = 'SIM'
    """).df()


def soma_das_secoes(con: duckdb.DuckDBPyConnection) -> dict:
    oficiais = con.sql("""
        select distinct nr_candidato from votos_presidente where ano = 2026 and turno = 1
    """).df()["nr_candidato"].tolist()
    lista = ", ".join(str(n) for n in oficiais)

    # números com voto nas seções que não estão no resultado oficial (ex.: candidatura com renúncia)
    fora = con.sql(f"""
        select nr_votavel, sum(qt_votos)::bigint as qt_votos from secoes
        where nr_votavel not in ({lista}, {BRANCO}, {NULO}) group by all
    """).df()
    info_fora = candidatos_fora_do_oficial(con, fora["nr_votavel"].tolist())
    lista_fora = ", ".join(str(n) for n in fora["nr_votavel"]) or "-1"

    # por UF: votos nos candidatos do resultado oficial, nulos e brancos
    por_uf = con.sql(f"""
        with s as (
            select uf,
                   count(distinct (cd_municipio_tse, zona, secao)) as secoes,
                   sum(qt_votos) filter (where nr_votavel in ({lista}))::bigint as validos_secoes,
                   coalesce(sum(qt_votos) filter (where nr_votavel in ({lista_fora})), 0)::bigint as votos_fora,
                   sum(qt_votos) filter (where nr_votavel = {NULO})::bigint as nulos_secoes,
                   sum(qt_votos) filter (where nr_votavel = {BRANCO})::bigint as brancos_secoes,
                   sum(qt_votos)::bigint as comparecimento_secoes
            from secoes group by uf
        ),
        o as (
            select uf, sum(qt_validos)::bigint as validos_oficial, sum(qt_nulos)::bigint as nulos_oficial,
                   sum(qt_brancos)::bigint as brancos_oficial, sum(qt_comparecimento)::bigint as comparecimento_oficial
            from comparecimento_presidente where ano = 2026 and turno = 1 group by uf
        ),
        v as (
            select uf, sum(qt_votos)::bigint as candidatos_oficial
            from votos_presidente where ano = 2026 and turno = 1 group by uf
        )
        select s.*, v.candidatos_oficial, o.validos_oficial, o.nulos_oficial, o.brancos_oficial,
               o.comparecimento_oficial
        from s full join o using (uf) full join v using (uf)
        order by uf = 'ZZ', uf
    """).df()
    por_uf["diferenca"] = por_uf["validos_secoes"] - por_uf["candidatos_oficial"]
    por_uf["diferenca_nulos"] = por_uf["nulos_secoes"] + por_uf["votos_fora"] - por_uf["nulos_oficial"]
    gravar(por_uf, "conferencia_secoes_uf")

    # por candidato (Brasil) e quantas UFs têm alguma diferença
    por_candidato = con.sql(f"""
        with s as (select uf, nr_votavel as nr_candidato, sum(qt_votos)::bigint as q from secoes
                   where nr_votavel not in ({BRANCO}, {NULO}) group by all),
             o as (select uf, nr_candidato, any_value(nm_urna) as nm_urna, any_value(sg_partido) as sg_partido,
                          sum(qt_votos)::bigint as q
                   from votos_presidente where ano = 2026 and turno = 1 group by all)
        select coalesce(s.nr_candidato, o.nr_candidato) as nr_candidato,
               any_value(o.nm_urna) as nm_urna, any_value(o.sg_partido) as sg_partido,
               coalesce(sum(s.q), 0)::bigint as soma_secoes, coalesce(sum(o.q), 0)::bigint as oficial,
               count(*) filter (where coalesce(s.q, 0) <> coalesce(o.q, 0)) as ufs_com_diferenca
        from s full join o using (uf, nr_candidato)
        group by all
    """).df()
    por_candidato["diferenca"] = por_candidato["soma_secoes"] - por_candidato["oficial"]
    for _, c in info_fora.iterrows():
        linha = por_candidato["nr_candidato"] == c["nr_candidato"]
        por_candidato.loc[linha, ["nm_urna", "sg_partido"]] = [c["nm_urna"], c["sg_partido"]]
    por_candidato["no_resultado_oficial"] = por_candidato["nr_candidato"].isin(oficiais)
    por_candidato = por_candidato.sort_values(["no_resultado_oficial", "nm_urna"], ascending=[False, True])
    gravar(por_candidato, "conferencia_secoes_candidato")

    # por município: em quantos a soma bate para todos os candidatos
    municipios = con.sql(f"""
        with s as (select uf, cd_municipio_tse, nr_votavel as nr_candidato, sum(qt_votos) as q from secoes
                   where nr_votavel in ({lista}) group by all),
             o as (select uf, cd_municipio_tse, nr_candidato, qt_votos as q
                   from votos_presidente where ano = 2026 and turno = 1)
        select uf, cd_municipio_tse, bool_and(coalesce(s.q, 0) = coalesce(o.q, 0)) as bate
        from s full join o using (uf, cd_municipio_tse, nr_candidato)
        group by all
    """).df()

    # eleitores aptos e comparecimento (arquivo de detalhe por seção × oficial)
    aptos = con.sql("""
        select (select sum(qt_aptos) from detalhe)::bigint as aptos_secoes,
               (select sum(qt_aptos) from comparecimento_presidente where ano = 2026 and turno = 1)::bigint as aptos_oficial,
               (select sum(qt_comparecimento) from detalhe)::bigint as comparecimento_detalhe,
               (select count(*) from detalhe)::bigint as secoes_detalhe
    """).df().iloc[0]

    fora_info = info_fora.iloc[0] if len(info_fora) else None
    resumo = {
        "secoes_detalhe": int(aptos["secoes_detalhe"]),
        "secoes_com_voto": int(por_uf["secoes"].sum()),
        "municipios": len(municipios),
        "municipios_exterior": int((municipios["uf"] == "ZZ").sum()),
        "municipios_com_diferenca": int((~municipios["bate"]).sum()),
        "candidatos_oficiais": len(oficiais),
        "validos_secoes": int(por_uf["validos_secoes"].sum()),
        "validos_oficial": int(por_uf["candidatos_oficial"].sum()),
        "diferenca_validos": int(por_uf["diferenca"].sum()),
        "votos_fora": int(fora["qt_votos"].sum()),
        "nr_fora": ", ".join(str(n) for n in fora["nr_votavel"]),
        "nm_urna_fora": fora_info["nm_urna"] if fora_info is not None else "",
        "partido_fora": fora_info["sg_partido"] if fora_info is not None else "",
        "situacao_fora": fora_info["situacao"] if fora_info is not None else "",
        "destino_votos_fora": fora_info["destino_votos"] if fora_info is not None else "",
        "nulos_secoes": int(por_uf["nulos_secoes"].sum()),
        "nulos_oficial": int(por_uf["nulos_oficial"].sum()),
        "brancos_secoes": int(por_uf["brancos_secoes"].sum()),
        "brancos_oficial": int(por_uf["brancos_oficial"].sum()),
        "comparecimento_secoes": int(por_uf["comparecimento_secoes"].sum()),
        "comparecimento_oficial": int(por_uf["comparecimento_oficial"].sum()),
        "aptos_secoes": int(aptos["aptos_secoes"]),
        "aptos_oficial": int(aptos["aptos_oficial"]),
    }
    print(f"  seções: {resumo['validos_secoes']:,} votos nos candidatos; oficial: {resumo['validos_oficial']:,}; "
          f"diferença {resumo['diferenca_validos']:,}; {resumo['municipios_com_diferenca']} municípios com diferença; "
          f"votos em números fora do oficial: {resumo['votos_fora']:,} ({resumo['nr_fora']})")
    return resumo


# ---------------------------------------------------------------------------
# 2. Reprodução da apuração de 2022
# ---------------------------------------------------------------------------

def apuracao_2022() -> dict:
    curva = pd.read_csv(DADOS / "apuracao" / "comparacao_curva_2022.csv", parse_dates=["momento"])
    gravar(curva, "conferencia_apuracao_2022")
    dif_secoes = (curva["pct_secoes_reproduzida"] - curva["pct_secoes_oficial"]).abs()
    dif_placar = (curva["pct_a_reproduzida"] - curva["pct_a_oficial"]).abs()
    depois_5 = curva["pct_secoes_oficial"] >= 0.05
    resumo = {
        "apuracao_momentos": len(curva),
        "apuracao_dif_secoes_media": float(dif_secoes.mean()),
        "apuracao_dif_secoes_max": float(dif_secoes.max()),
        "apuracao_dif_placar_media": float(dif_placar.mean()),
        "apuracao_dif_placar_max": float(dif_placar.max()),
        "apuracao_dif_placar_media_depois_5": float(dif_placar[depois_5].mean()),
    }
    print(f"  diferença média: {100 * resumo['apuracao_dif_secoes_media']:.2f} ponto no % apurado, "
          f"{100 * resumo['apuracao_dif_placar_media']:.3f} ponto no placar")
    return resumo


# ---------------------------------------------------------------------------
# 3. RDV × oficial
# ---------------------------------------------------------------------------

EXPLICACAO_RDV = {
    ("RS", 2022): "Uma urna (de 27 mil) tem o RDV num formato que o leitor não reconhece; os votos dela ficam de fora.",
    ("SC", 2022): "Votos digitados para candidaturas indeferidas: no RDV aparecem no número; no resultado oficial, como anulados.",
    ("BA", 2022): "Votos digitados para candidaturas indeferidas: no RDV aparecem no número; no resultado oficial, como anulados.",
}


def rdv() -> pd.DataFrame:
    apertadas = pd.read_csv(DADOS / "nulos" / "nulos_disputas_apertadas.csv")
    governador = pd.read_parquet(DADOS / "base" / "governador_uf.parquet")
    oficial = (governador.groupby(["ano", "turno", "uf"], as_index=False)["qt_votos"].sum()
               .rename(columns={"qt_votos": "votos_oficial"}))
    tabela = apertadas[["ano", "turno", "uf", "resultado_oficial", "diferenca_rdv_oficial"]].merge(
        oficial, on=["ano", "turno", "uf"], how="left")
    tabela["votos_oficial"] = tabela["votos_oficial"].astype("int64")
    tabela["votos_rdv"] = tabela["votos_oficial"] + tabela["diferenca_rdv_oficial"]
    tabela["diferenca_pct"] = tabela["diferenca_rdv_oficial"] / tabela["votos_oficial"]
    tabela["explicacao"] = [EXPLICACAO_RDV.get((uf, ano), "") if dif else ""
                            for uf, ano, dif in zip(tabela["uf"], tabela["ano"], tabela["diferenca_rdv_oficial"])]
    tabela = tabela.sort_values(["ano", "uf"]).reset_index(drop=True)
    gravar(tabela, "conferencia_rdv")
    return tabela


# ---------------------------------------------------------------------------
# 4. Lei de Benford
# ---------------------------------------------------------------------------

def benford_votos(con: duckdb.DuckDBPyConnection) -> dict:
    nomes = con.sql("""
        select nr_candidato, any_value(nm_urna) as nm_urna, sum(qt_votos)::bigint as total
        from votos_presidente where ano = 2026 and turno = 1 group by all
    """).df()
    lista = ", ".join(str(n) for n in nomes["nr_candidato"])
    niveis = {
        "seção": con.sql(f"""select nr_votavel as nr_candidato, qt_votos from secoes
                             where nr_votavel in ({lista}) and qt_votos > 0""").df(),
        "município": con.sql("""select nr_candidato, qt_votos::bigint as qt_votos from votos_presidente
                                where ano = 2026 and turno = 1 and qt_votos > 0""").df(),
    }
    partes = []
    for nivel, votos in niveis.items():
        for nr, grupo in votos.groupby("nr_candidato"):
            for posicao in (1, 2):
                tabela = distribuicao(digito(grupo["qt_votos"], posicao), posicao)
                tabela.insert(0, "posicao", posicao)
                tabela.insert(0, "nr_candidato", nr)
                tabela.insert(0, "nivel", nivel)
                partes.append(tabela)
    tabela = pd.concat(partes).merge(nomes, on="nr_candidato")
    gravar(tabela, "conferencia_benford")

    # quantos votos cada candidato teve por seção (faixas de 10 votos), com as seções de 0 voto
    faixas = con.sql(f"""
        with base as (
            select d.uf, d.cd_municipio_tse, d.zona, d.secao, c.nr_candidato
            from detalhe d cross join (select unnest([{lista}]) as nr_candidato) c
            where d.qt_comparecimento > 0
        )
        select b.nr_candidato, least(floor(coalesce(s.qt_votos, 0) / 10) * 10, 500)::int as faixa,
               count(*) as secoes
        from base b left join secoes s
          on s.uf = b.uf and s.cd_municipio_tse = b.cd_municipio_tse and s.zona = b.zona
         and s.secao = b.secao and s.nr_votavel = b.nr_candidato
        group by all order by all
    """).df().merge(nomes[["nr_candidato", "nm_urna"]], on="nr_candidato")
    gravar(faixas, "conferencia_votos_por_secao")

    desvios = (tabela[tabela["posicao"] == 1].groupby(["nivel", "nm_urna"])
               .apply(lambda g: desvio_medio(g["proporcao"], g["benford"]), include_groups=False))
    print("  distância média até a curva de Benford (1º dígito, pontos):")
    print((100 * desvios).round(2).unstack(0).to_string())

    # o menor e o maior município em votos válidos (para explicar as "ordens de grandeza")
    extremos = con.sql("""
        select m.nm_municipio, c.uf, c.qt_validos::bigint as qt_validos
        from comparecimento_presidente c join municipios m using (uf, cd_municipio_tse)
        where c.ano = 2026 and c.turno = 1 and c.uf <> 'ZZ'
        order by c.qt_validos
    """).df()
    menor, maior = extremos.iloc[0], extremos.iloc[-1]
    return {"municipio_menor": f"{menor['nm_municipio']} ({menor['uf']})", "municipio_menor_validos": int(menor["qt_validos"]),
            "municipio_maior": f"{maior['nm_municipio']} ({maior['uf']})", "municipio_maior_validos": int(maior["qt_validos"])}


# ---------------------------------------------------------------------------
# 5. Checagens automáticas
# ---------------------------------------------------------------------------

def checagens(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    linhas = []
    for arquivo in sorted((RAIZ / "sql" / "checagens").glob("*.sql")):
        sql = arquivo.read_text(encoding="utf-8")
        descricao = next(l for l in sql.splitlines() if l.startswith("--")).lstrip("- ").strip()
        problemas = len(con.execute(sql).df())
        linhas.append({"checagem": arquivo.name, "o_que_confere": descricao, "linhas_com_problema": problemas})
    tabela = pd.DataFrame(linhas)

    # coletor ao vivo: a soma dos municípios bate com o total do Brasil publicado pelo TSE?
    ao_vivo = (DADOS / "ao_vivo" / "e6257_c1").as_posix()
    if list(Path(ao_vivo).glob("*/candidatos.parquet")):
        nacional = con.sql(f"""
            with ultimo as (
                select * from read_parquet('{ao_vivo}/*/candidatos.parquet')
                qualify row_number() over (partition by uf, cd_municipio_tse, nr_candidato order by dt_coleta desc) = 1
            )
            select nr_candidato,
                   sum(qt_votos) filter (where cd_municipio_tse <> '') as soma_municipios,
                   sum(qt_votos) filter (where cd_municipio_tse = '' and uf = 'br') as total_brasil
            from ultimo group by all
        """).df()
        diferenca = int((nacional["soma_municipios"] - nacional["total_brasil"]).abs().sum())
        linhas = [{"checagem": "coletor ao vivo",
                   "o_que_confere": "A soma dos votos dos municípios (e cidades do exterior) é igual ao total do "
                                    "Brasil divulgado pelo TSE (1º turno de 2026).",
                   "linhas_com_problema": diferenca}]
        tabela = pd.concat([tabela, pd.DataFrame(linhas)], ignore_index=True)
    else:
        print("  (sem dados do coletor ao vivo em dados/ao_vivo/; essa checagem fica de fora)")

    # diferença conhecida de 2006 (a checagem 03 tolera, mas ela fica registrada)
    fecha = con.sql("""
        select ano, turno, sum(qt_comparecimento - (qt_validos + qt_brancos + qt_nulos + qt_anulados_separado))::bigint
               as votos_que_nao_fecham, sum(qt_comparecimento)::bigint as comparecimento
        from comparecimento_presidente group by all order by all
    """).df()
    gravar(tabela, "conferencia_checagens")
    gravar(fecha, "conferencia_comparecimento_fecha")
    print(tabela.to_string(index=False))
    return tabela


# ---------------------------------------------------------------------------
# 6. Seções fora do padrão
# ---------------------------------------------------------------------------

def secoes_fora_do_padrao(con: duckdb.DuckDBPyConnection) -> None:
    nomes = con.sql("""select nr_candidato as nr_maior, any_value(nm_urna) as nm_urna
                       from votos_presidente where ano = 2026 and turno = 1 group by all""").df()
    lista = ", ".join(str(n) for n in nomes["nr_maior"])
    # votos válidos = votos nos candidatos do resultado oficial
    secoes = con.sql(f"""
        with v as (
            select uf, cd_municipio_tse, zona, secao, sum(qt_votos) as validos, max(qt_votos) as maior,
                   arg_max(nr_votavel, qt_votos) as nr_maior
            from secoes where nr_votavel in ({lista}) group by all
        )
        select d.uf, d.cd_municipio_tse, d.zona, d.secao, d.qt_aptos, d.qt_comparecimento, d.nm_local,
               d.origem, d.instalada, coalesce(v.validos, 0) as validos, v.maior, v.nr_maior
        from detalhe d left join v using (uf, cd_municipio_tse, zona, secao)
    """).df()
    secoes["tipo_local"] = [tipo_de_local(n, uf) for n, uf in zip(secoes["nm_local"], secoes["uf"])]
    secoes["um_so_candidato"] = (secoes["validos"] > 0) & (secoes["maior"] == secoes["validos"])
    secoes = secoes.merge(nomes, on="nr_maior", how="left")

    instaladas = secoes["instalada"]
    grupos = {
        "não instalada": ~instaladas,
        "instalada, sem nenhum voto": instaladas & (secoes["qt_comparecimento"] == 0),
        "votação em cédula (sistema de apuração)": instaladas & (secoes["origem"] == "Sistema de apuração"),
        "boletim recuperado da urna (RED)": secoes["origem"].str.startswith("BU gerado por RED"),
        "menos de 50 eleitores": instaladas & (secoes["qt_aptos"] < 50),
        "todos os votos válidos para um só candidato": secoes["um_so_candidato"],
    }
    linhas = []
    for situacao, filtro in grupos.items():
        sub = secoes[filtro]
        por_tipo = sub["tipo_local"].value_counts()
        linha = {"situacao": situacao, "secoes": len(sub), "eleitores": int(sub["qt_aptos"].sum()),
                 "votantes": int(sub["qt_comparecimento"].sum())}
        for tipo in ["exterior", "presídio ou unidade para adolescentes", "aldeia ou escola indígena", "outro"]:
            linha[tipo] = int(por_tipo.get(tipo, 0))
        if situacao == "todos os votos válidos para um só candidato":
            for nome, q in sub["nm_urna"].value_counts().items():
                linha[f"candidato: {nome}"] = int(q)
            linha["votantes_mediana"] = float(sub["qt_comparecimento"].median())
            linha["ate_50_votantes"] = int((sub["qt_comparecimento"] <= 50).sum())
        linhas.append(linha)
    tabela = pd.DataFrame(linhas)
    gravar(tabela, "conferencia_secoes_fora_padrao")

    tamanhos = con.sql("""
        select count(*) filter (where instalada) as secoes_instaladas,
               median(qt_aptos) filter (where instalada) as aptos_mediana,
               avg(qt_comparecimento) filter (where instalada and qt_comparecimento > 0) as votantes_media,
               quantile_cont(qt_comparecimento, 0.05) filter (where instalada and qt_comparecimento > 0) as votantes_p05,
               quantile_cont(qt_comparecimento, 0.95) filter (where instalada and qt_comparecimento > 0) as votantes_p95,
               min(qt_aptos) filter (where instalada) as aptos_min,
               max(qt_aptos) filter (where instalada) as aptos_max
        from detalhe
    """).df()
    gravar(tamanhos, "conferencia_tamanho_secoes")
    print(tabela.drop(columns=["eleitores"]).to_string(index=False))


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    print("Baixando (se ainda não tiver)...")
    baixar_tudo()
    con = duckdb.connect(str(BANCO), read_only=True)
    print("Resumindo os arquivos por seção...")
    preparar_votos_secao(con)
    preparar_detalhe_secao(con)
    con.execute(f"create or replace temp view secoes as select * from read_parquet('{VOTOS_SECAO.as_posix()}')")
    con.execute(f"create or replace temp view detalhe as select * from read_parquet('{DETALHE_SECAO.as_posix()}')")

    print("1. Soma das seções × resultado oficial")
    resumo = soma_das_secoes(con)
    print("2. Reprodução da apuração de 2022")
    resumo |= apuracao_2022()
    print("3. RDV × oficial")
    rdv()
    print("4. Lei de Benford")
    resumo |= benford_votos(con)
    print("5. Checagens automáticas")
    checagens(con)
    print("6. Seções fora do padrão")
    secoes_fora_do_padrao(con)
    gravar(pd.DataFrame([resumo]), "conferencia_resumo")
    con.close()


if __name__ == "__main__":
    main()
