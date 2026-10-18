"""Dados das páginas "Perfil dos candidatos" e "Patrimônio declarado" do site.

Baixa os arquivos oficiais, liga cada candidatura à sua situação depois da
eleição e grava tabelas pequenas, já calculadas, em app/dados/.

Fontes (todas públicas):

- Portal de Dados Abertos do TSE, conjuntos "candidatos-2018", "candidatos-2022"
  e "candidatos-2026" (https://dadosabertos.tse.jus.br/dataset/candidatos-2026):
    https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip
    https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand_complementar/consulta_cand_complementar_{ano}.zip
    https://cdn.tse.jus.br/estatistica/sead/odsele/bem_candidato/bem_candidato_{ano}.zip
    https://cdn.tse.jus.br/estatistica/sead/odsele/historico_candidatura/historico_candidatura_2026.zip
- Situação de cada candidato de 2026 depois do 1º turno (eleito, 2º turno, não
  eleito), nos arquivos de resultado do TSE:
    https://resultados.tse.jus.br/oficial/ele2026/6259/dados/{uf}/{uf}-c000{cargo}-e006259-u.json
    https://resultados.tse.jus.br/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json
- Censo 2022 do IBGE, tabela 10061 do SIDRA ("Pessoas de 18 anos ou mais de
  idade, por nível de instrução, segundo os grupos de idade, o sexo e a cor ou raça"):
    https://apisidra.ibge.gov.br/values/t/10061/n1/all/v/2667/p/2022/...
- IPCA mensal (variação %), IBGE, tabela 1737 do SIDRA. Antes vinha da série 433 do
  Banco Central, que passou a recusar os pedidos automáticos em out/2026; o IBGE é
  quem calcula o IPCA, então os números são os mesmos:
    https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/63/p/all

Critérios (repetidos nas páginas):
- "Foi a voto": a candidatura estava na urna e os votos foram contados como
  válidos (NM_TIPO_DESTINACAO_VOTOS = "Válido" no arquivo complementar). Ficam
  de fora quem desistiu, quem foi barrado e quem teve os votos anulados (inclusive
  "anulado sub judice", à espera de julgamento de recurso).
- Eleitos de 2018 e 2022: situação final da totalização (DS_SIT_TOT_TURNO); quem
  foi ao 2º turno conta pelo resultado do 2º turno.
- Eleitos de 2026: situação nos arquivos de resultado (campo "st"), ligada à
  candidatura pelo número sequencial ("sqcand" = SQ_CANDIDATO). Quem está no
  2º turno é uma categoria à parte.
- A mesma pessoa em anos diferentes é ligada pelo CPF (conferido com o
  "Histórico de candidaturas" do TSE); sem CPF, por nome + data de nascimento.
  O CPF não é gravado em app/dados/.

Saídas em app/dados/ (candidatos_*.parquet e patrimonio_*.parquet) e, para o
modelo do Power BI (scripts/exportar_powerbi.py), dados/brutos/candidatos/candidaturas.parquet:
uma linha por candidatura que foi a voto em 2018, 2022 e 2026 (cargos acima;
idade na data do 1º turno; patrimônio em reais da época, sem correção). Os
arquivos baixados ficam em dados/brutos/candidatos/ e não são baixados de novo
(use --atualizar para buscar as versões mais recentes).

    python scripts/site_candidatos.py
    python scripts/site_candidatos.py --atualizar
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from eleicoes.tse_ao_vivo import BASE_URL, UFS, caminho_resultado  # noqa: E402
from eleicoes.tse_arquivos import ler_csv_tse, url_odsele  # noqa: E402

BRUTOS = RAIZ / "dados" / "brutos" / "candidatos"
SAIDA = RAIZ / "app" / "dados"

ANOS = [2018, 2022, 2026]
DATA_ELEICAO = {2018: "2018-10-07", 2022: "2022-10-02", 2026: "2026-10-04"}
URL_SIDRA = "https://apisidra.ibge.gov.br/values/t/10061/n1/all/v/2667/p/2022"
URL_IPCA = "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/63/p/all"
PARALELOS = 3  # o TSE devolve 403 com muitas conexões ao mesmo tempo

# Cargos analisados (vices e suplentes ficam de fora). Estadual e distrital juntos:
# o DF não tem deputado estadual, e sim distrital.
CARGOS = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal",
          7: "Deputado Estadual ou Distrital", 8: "Deputado Estadual ou Distrital"}
ORDEM_CARGOS = ["Presidente", "Governador", "Senador", "Deputado Federal", "Deputado Estadual ou Distrital"]
TODOS = "Todos os cargos"
DEPUTADOS = {6, 7, 8}
# Vagas em disputa (Senado: 2/3 das cadeiras em 2018 e 2026, 1/3 em 2022).
VAGAS = {
    "Presidente": {2018: 1, 2022: 1, 2026: 1},
    "Governador": {2018: 27, 2022: 27, 2026: 27},
    "Senador": {2018: 54, 2022: 27, 2026: 54},
    "Deputado Federal": {2018: 513, 2022: 513, 2026: 513},
    "Deputado Estadual ou Distrital": {2018: 1059, 2022: 1059, 2026: 1059},
}

ELEITO, NAO_ELEITO, SEGUNDO_TURNO, AGUARDANDO = "Eleito", "Não eleito", "2º turno", "Aguardando totalização"
NOME_CARGO = {1: "Presidente", 3: "Governador", 5: "Senador", 6: "Deputado Federal", 7: "Deputado Estadual",
              8: "Deputado Distrital"}

# --- categorias do perfil ------------------------------------------------------
GENERO = {"FEMININO": "Mulheres", "MASCULINO": "Homens"}
COR_RACA = {"BRANCA": "Branca", "PRETA": "Preta", "PARDA": "Parda", "AMARELA": "Amarela", "INDÍGENA": "Indígena"}
# Mesmos grupos que o IBGE usa no Censo (cada nível inclui o seguinte incompleto).
INSTRUCAO = {
    "LÊ E ESCREVE": "Até fundamental incompleto",
    "ENSINO FUNDAMENTAL INCOMPLETO": "Até fundamental incompleto",
    "ENSINO FUNDAMENTAL COMPLETO": "Fundamental completo",
    "ENSINO MÉDIO INCOMPLETO": "Fundamental completo",
    "ENSINO MÉDIO COMPLETO": "Médio completo",
    "SUPERIOR INCOMPLETO": "Médio completo",
    "SUPERIOR COMPLETO": "Superior completo",
}
FAIXAS = [(18, 29, "18 a 29 anos"), (30, 39, "30 a 39 anos"), (40, 49, "40 a 49 anos"),
          (50, 59, "50 a 59 anos"), (60, 69, "60 a 69 anos"), (70, 200, "70 anos ou mais")]
ORDEM_CATEGORIAS = {
    "Gênero": list(dict.fromkeys(GENERO.values())),
    "Cor ou raça": list(COR_RACA.values()),
    "Faixa etária": [f[2] for f in FAIXAS],
    "Grau de instrução": list(dict.fromkeys(INSTRUCAO.values())),
}
NAO_INFORMADO = "Não informado"

# --- títulos e profissões no nome de urna -----------------------------------------
# Só a primeira palavra do nome de urna conta (sem acento e sem pontuação):
# "BISPO" no fim do nome costuma ser sobrenome. Abreviações (PR, SGT, PROF...)
# também só valem no começo.
TITULOS = {
    "Religioso": {"PASTOR", "PASTORA", "PR", "PRA", "BISPO", "BISPA", "PADRE", "IRMAO", "IRMA",
                  "MISSIONARIO", "MISSIONARIA", "APOSTOLO", "APOSTOLA", "PRESBITERO", "DIACONO",
                  "DIACONISA", "EVANGELISTA", "FREI", "REVERENDO"},
    "Policial ou militar": {"SARGENTO", "SGT", "SUBTENENTE", "SUBTEN", "CAPITAO", "CAP", "CORONEL", "CEL",
                            "CABO", "CB", "SOLDADO", "SD", "TENENTE", "TEN", "MAJOR", "GENERAL", "BRIGADEIRO",
                            "ALMIRANTE", "COMANDANTE", "CMT", "DELEGADO", "DELEGADA", "DEL", "POLICIAL", "PM",
                            "INSPETOR", "INSPETORA", "INVESTIGADOR", "INVESTIGADORA", "ESCRIVAO", "ESCRIVA",
                            "PERITO", "PERITA", "BOMBEIRO", "BOMBEIRA", "GUARDA"},
    "Professor(a)": {"PROFESSOR", "PROFESSORA", "PROF", "PROFA", "PROFE"},
    "Doutor(a)": {"DR", "DRA", "DOUTOR", "DOUTORA"},
    "Enfermeiro(a) ou médico(a)": {"ENFERMEIRO", "ENFERMEIRA", "MEDICO", "MEDICA"},
}
SEM_TITULO = "Sem título"

# --- tipos de bens ------------------------------------------------------------------
IMOVEIS, VEICULOS, APLICACOES, EMPRESAS, CRIPTO, OUTROS = (
    "Imóveis", "Veículos, barcos e aviões", "Aplicações e dinheiro", "Participações em empresas",
    "Criptoativos", "Outros bens e direitos")
ORDEM_BENS = [IMOVEIS, APLICACOES, EMPRESAS, VEICULOS, CRIPTO, OUTROS]
# O TSE não tem um tipo próprio para criptoativos: eles aparecem em "outras
# aplicações", "outros bens e direitos" etc. Procuramos na descrição do bem.
RE_CRIPTO = re.compile(r"\b(CRIPTO\w*|BITCOIN\w*|BITCON|BTC|ETHEREUM|ETH|USDT|TETHER|BINANCE|ALTCOIN\w*)\b")
TIPOS_SEM_CRIPTO = set(range(1, 27)) | {31, 32, 39}  # imóveis, veículos, joias, ações e quotas


# ---------------------------------------------------------------------------------
# Funções puras (testadas em tests/test_site_candidatos.py)
# ---------------------------------------------------------------------------------

def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def titulo_nome_urna(nome: str | None) -> str:
    """Tipo de título/profissão com que o nome de urna começa ('Sem título' se nenhum)."""
    if not isinstance(nome, str):
        return SEM_TITULO
    palavras = re.sub(r"[^A-Z0-9 ]", " ", sem_acento(nome).upper()).split()
    if not palavras:
        return SEM_TITULO
    primeira = palavras[0]
    if primeira == "SUB" and len(palavras) > 1 and palavras[1] in {"TENENTE", "TEN", "OFICIAL"}:
        return "Policial ou militar"
    for tipo, palavras_tipo in TITULOS.items():
        if primeira in palavras_tipo:
            return tipo
    return SEM_TITULO


def situacao_final(sit_1t, sit_2t) -> str | None:
    """Situação de 2018/2022 a partir da totalização de cada turno (DS_SIT_TOT_TURNO).

    'ELEITO', 'ELEITO POR QP' e 'ELEITO POR MÉDIA' -> Eleito; '2º TURNO' -> o
    resultado do 2º turno; 'SUPLENTE' e 'NÃO ELEITO' -> Não eleito; sem
    totalização (candidatura fora da urna) -> None.
    """
    if not isinstance(sit_1t, str) or not sit_1t.strip():
        return None
    s1 = sit_1t.strip().upper()
    if s1.startswith("ELEITO"):
        return ELEITO
    if s1 == "2º TURNO":
        s2 = sit_2t.strip().upper() if isinstance(sit_2t, str) else ""
        if s2.startswith("ELEITO"):
            return ELEITO
        if s2 == "NÃO ELEITO":
            return NAO_ELEITO
        return SEGUNDO_TURNO
    return NAO_ELEITO


def texto_tse(texto) -> str:
    """'ENSINO MÉDIO COMPLETO' -> 'Ensino médio completo'; sem informação -> 'Não informado'."""
    if not isinstance(texto, str) or not texto.strip() or texto.strip().upper() in {
            "NÃO DIVULGÁVEL", "NÃO INFORMADO", "#NULO", "#NULO#", "#NE"}:
        return NAO_INFORMADO
    return re.sub(r"\bqp\b", "QP", texto.strip().capitalize())


def situacao_texto(ano: int, sit_1t, sit_2t, st_json) -> str:
    """Texto do resultado para a tabela do Power BI ('Eleito por QP', 'Suplente',
    'Eleito (2º turno)', '2º turno', 'Aguardando totalização'...)."""
    if ano >= 2026:
        return st_json.strip() if isinstance(st_json, str) and st_json.strip() else AGUARDANDO
    if not isinstance(sit_1t, str) or not sit_1t.strip():
        return AGUARDANDO
    if sit_1t.strip().upper() == "2º TURNO":
        final = situacao_final(sit_1t, sit_2t)
        return f"{final} (2º turno)" if final in (ELEITO, NAO_ELEITO) else SEGUNDO_TURNO
    return texto_tse(sit_1t)


def situacao_json(st) -> str:
    """Situação de 2026 no campo "st" dos arquivos de resultado do TSE."""
    s = st.strip().lower() if isinstance(st, str) else ""
    if s.startswith("eleito"):
        return ELEITO
    if s in {"2º turno", "2o turno", "segundo turno"}:
        return SEGUNDO_TURNO
    if s in {"suplente", "não eleito", "nao eleito"}:
        return NAO_ELEITO
    return AGUARDANDO


def idade_na_data(nascimento: pd.Series, data: str) -> pd.Series:
    """Idade em anos completos na data (nascimento no formato dd/mm/aaaa)."""
    nasc = pd.to_datetime(nascimento, format="%d/%m/%Y", errors="coerce")
    ref = pd.Timestamp(data)
    anos = ref.year - nasc.dt.year
    ainda_nao_fez = (nasc.dt.month > ref.month) | ((nasc.dt.month == ref.month) & (nasc.dt.day > ref.day))
    return (anos - ainda_nao_fez.astype(int)).where(nasc.notna())


def faixa_etaria(idade: pd.Series) -> pd.Series:
    rotulos = pd.Series(NAO_INFORMADO, index=idade.index, dtype=object)
    for minimo, maximo, rotulo in FAIXAS:
        rotulos[(idade >= minimo) & (idade <= maximo)] = rotulo
    return rotulos


def agremiacao(sg_partido: str, sg_federacao) -> str:
    """Partido isolado ou federação (a cota de gênero vale para a federação inteira).

    '13-PT/65-PC do B/43-PV' -> 'PT/PC do B/PV (federação)'.
    """
    if not isinstance(sg_federacao, str) or not sg_federacao.strip():
        return sg_partido
    partes = [re.sub(r"^\s*\d+\s*-\s*", "", p).strip() for p in sg_federacao.split("/")]
    return "/".join(p for p in partes if p) + " (federação)"


def categoria_bem(cd_tipo: int, descricao) -> str:
    """Agrupa os ~50 tipos de bem do TSE em poucas categorias."""
    texto = sem_acento(descricao).upper() if isinstance(descricao, str) else ""
    if cd_tipo not in TIPOS_SEM_CRIPTO and RE_CRIPTO.search(texto):
        return CRIPTO
    if 1 <= cd_tipo <= 19:
        return IMOVEIS
    if cd_tipo in (21, 22, 23):
        return VEICULOS
    if cd_tipo in (31, 32, 39):
        return EMPRESAS
    if 41 <= cd_tipo <= 49 or cd_tipo in (53, 54) or 61 <= cd_tipo <= 79 or cd_tipo == 97:
        return APLICACOES
    return OUTROS


def valor_reais(texto: pd.Series) -> pd.Series:
    """'1234567,89' -> 1234567.89 (valores dos bens vêm com vírgula decimal)."""
    return pd.to_numeric(texto.astype(str).str.replace(".", "", regex=False)
                         .str.replace(",", ".", regex=False), errors="coerce").fillna(0.0)


def indice_ipca(sidra: list[dict]) -> pd.Series:
    """Número-índice mensal a partir das variações % do IPCA (SIDRA, tabela 1737,
    variável 63). A 1ª linha da resposta do SIDRA é o cabeçalho; meses sem valor
    ("..." ou "-") ficam de fora."""
    linhas = [x for x in sidra[1:] if x["V"] not in ("...", "-", "", "X")]
    variacao = pd.Series([float(x["V"]) for x in linhas],
                         index=pd.to_datetime([x["D3C"] for x in linhas], format="%Y%m"))
    return (1 + variacao.sort_index() / 100).cumprod()


def fatores_ipca(indice: pd.Series, anos: list[int], referencia: pd.Timestamp | None = None
                 ) -> tuple[dict[int, float], pd.Timestamp]:
    """Fator que leva um valor de agosto de cada ano (mês do registro das
    candidaturas) para a `referencia` (padrão: agosto do último ano, ou o último
    mês disponível se ele ainda não saiu)."""
    if referencia is None:
        referencia = pd.Timestamp(max(anos), 8, 1)
        if referencia not in indice.index:
            referencia = indice.index.max()
    # asof: se agosto de um ano ainda não saiu, usa o último mês disponível antes dele
    return {ano: float(indice[referencia] / indice.asof(pd.Timestamp(ano, 8, 1))) for ano in anos}, referencia


def chave_pessoa(cpf, nome, nascimento) -> str | None:
    """CPF quando existe; senão nome sem acento + data de nascimento."""
    if isinstance(cpf, str) and re.fullmatch(r"\d{11}", cpf.strip()):
        return "cpf:" + cpf.strip()
    if isinstance(nome, str) and isinstance(nascimento, str) and nascimento.strip():
        return "nome:" + re.sub(r"\s+", " ", sem_acento(nome).upper().strip()) + "|" + nascimento.strip()
    return None


def ler_sidra(linhas: list[dict], classificacao: str) -> pd.DataFrame:
    """Resposta da API do SIDRA -> (categoria do IBGE, pessoas). A 1ª linha é o cabeçalho."""
    cabecalho, dados = linhas[0], linhas[1:]
    coluna = next(k for k, v in cabecalho.items() if v == classificacao and k.endswith("N"))
    return pd.DataFrame({"categoria_ibge": [d[coluna] for d in dados],
                         "pessoas": [int(d["V"]) for d in dados]})


def mediana_ou_nada(valores: pd.Series, minimo: int) -> float:
    """Mediana só para grupos com pelo menos `minimo` pessoas (não expõe indivíduos)."""
    return float(valores.median()) if len(valores) >= minimo else float("nan")


# ---------------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------------

def nova_sessao() -> requests.Session:
    sessao = requests.Session()
    sessao.headers["User-Agent"] = "eleicoes-2026-dados (projeto de estudo)"
    return sessao


def baixar(url: str, destino: Path, sessao: requests.Session, atualizar: bool = False,
           tentativas: int = 6) -> Path:
    """Baixa `url` para `destino`, com novas tentativas e espera crescente (o TSE
    responde 403 quando recebe muitos pedidos). Não baixa de novo se já existe."""
    if destino.exists() and destino.stat().st_size > 0 and not atualizar:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    for tentativa in range(tentativas):
        try:
            resposta = sessao.get(url, timeout=180)
            resposta.raise_for_status()
            if destino.suffix == ".json":
                # alguns servidores respondem 200 com uma página de erro em HTML:
                # só troca o arquivo bom se a resposta for JSON de verdade
                try:
                    json.loads(resposta.content)
                except ValueError:
                    raise requests.RequestException(f"resposta não é JSON: {resposta.text[:80]!r}")
            parcial = destino.with_name(destino.name + ".parcial")
            parcial.write_bytes(resposta.content)
            parcial.replace(destino)
            return destino
        except requests.RequestException as erro:
            if tentativa == tentativas - 1:
                raise
            espera = 5 * 2 ** tentativa
            print(f"   {url.rsplit('/', 1)[-1]}: {erro.__class__.__name__}, nova tentativa em {espera}s", flush=True)
            time.sleep(espera)
    return destino


def alvos_resultados_2026() -> list[tuple[int, int, str]]:
    alvos = [(6257, 1, "br")]
    for uf in [u for u in UFS if u != "zz"]:
        alvos += [(6259, cargo, uf) for cargo in (3, 5, 6, 8 if uf == "df" else 7)]
    return alvos


def baixar_tudo(atualizar: bool) -> None:
    sessao = nova_sessao()
    tarefas = []
    for ano in ANOS:
        for conjunto in ("consulta_cand", "consulta_cand_complementar", "bem_candidato"):
            tarefas.append((url_odsele(conjunto, ano), BRUTOS / f"{conjunto}_{ano}.zip"))
    tarefas.append((url_odsele("historico_candidatura", 2026), BRUTOS / "historico_candidatura_2026.zip"))
    for eleicao, cargo, uf in alvos_resultados_2026():
        caminho = caminho_resultado("ele2026", eleicao, cargo, uf)
        tarefas.append((f"{BASE_URL}/{caminho}", BRUTOS / "resultados_2026" / Path(caminho).name))
    for nome, filtro in CONSULTAS_SIDRA.items():
        tarefas.append((f"{URL_SIDRA}/{filtro}", BRUTOS / "ibge" / f"censo2022_t10061_{nome}.json"))
    tarefas.append((URL_IPCA, BRUTOS / "ipca_sidra1737.json"))

    with ThreadPoolExecutor(max_workers=PARALELOS) as executor:
        list(executor.map(lambda t: baixar(*t, sessao=sessao, atualizar=atualizar), tarefas))
    print(f"{len(tarefas)} arquivos em {BRUTOS}", flush=True)


# ---------------------------------------------------------------------------------
# Leitura e montagem da base de candidaturas
# ---------------------------------------------------------------------------------

def ler_do_zip(conjunto: str, ano: int, colunas: list[str]) -> pd.DataFrame:
    """Lê só as colunas pedidas do CSV nacional (_BRASIL) de dentro do zip."""
    caminho = BRUTOS / f"{conjunto}_{ano}.zip"
    with zipfile.ZipFile(caminho) as zf, zf.open(f"{conjunto}_{ano}_BRASIL.csv") as arquivo:
        return ler_csv_tse(arquivo, colunas)


COLUNAS_CAND = ["CD_TIPO_ELEICAO", "NR_TURNO", "CD_ELEICAO", "SG_UF", "CD_CARGO", "SQ_CANDIDATO", "NR_CANDIDATO",
                "NM_CANDIDATO", "NM_URNA_CANDIDATO", "NR_CPF_CANDIDATO", "SG_PARTIDO", "SG_FEDERACAO",
                "DT_NASCIMENTO", "DS_GENERO", "DS_GRAU_INSTRUCAO", "DS_COR_RACA", "DS_SIT_TOT_TURNO"]
COLUNAS_COMPL = ["CD_ELEICAO", "SQ_CANDIDATO", "NM_TIPO_DESTINACAO_VOTOS"]


def situacoes_2026() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Situação de cada candidato nos arquivos de resultado de 2026 e as vagas por UF."""
    linhas, vagas = [], []
    for eleicao, cargo, uf in alvos_resultados_2026():
        caminho = BRUTOS / "resultados_2026" / Path(caminho_resultado("ele2026", eleicao, cargo, uf)).name
        u = json.loads(caminho.read_text(encoding="utf-8"))
        final = u.get("tf") == "s"
        for c in u["carg"]:
            vagas.append({"uf": uf.upper(), "cd_cargo": int(c["cd"]), "vagas": int(c.get("nv") or 0),
                          "totalizacao_final": final})
            for agr in c["agr"]:
                for par in agr["par"]:
                    for cand in par["cand"]:
                        linhas.append({"sq_candidato": str(cand["sqcand"]), "st_json": cand.get("st", ""),
                                       "dvt_json": cand.get("dvt"), "totalizacao_final": final})
    return pd.DataFrame(linhas), pd.DataFrame(vagas)


def candidaturas(ano: int) -> pd.DataFrame:
    """Uma linha por pedido de registro para os cargos analisados (1º turno)."""
    c = ler_do_zip("consulta_cand", ano, COLUNAS_CAND)
    c = c[(c["CD_TIPO_ELEICAO"] == "2") & c["CD_CARGO"].astype(int).isin(CARGOS)]
    turno2 = (c[c["NR_TURNO"] == "2"].drop_duplicates("SQ_CANDIDATO")
              .set_index("SQ_CANDIDATO")["DS_SIT_TOT_TURNO"])
    c = c[c["NR_TURNO"] == "1"].drop_duplicates("SQ_CANDIDATO").copy()

    k = ler_do_zip("consulta_cand_complementar", ano, COLUNAS_COMPL).drop_duplicates(["CD_ELEICAO", "SQ_CANDIDATO"])
    c = c.merge(k, on=["CD_ELEICAO", "SQ_CANDIDATO"], how="left")

    base = pd.DataFrame({
        "ano": ano,
        "sq_candidato": c["SQ_CANDIDATO"].values,
        "uf": c["SG_UF"].values,
        "cd_cargo": c["CD_CARGO"].astype(int).values,
        "nr_candidato": pd.to_numeric(c["NR_CANDIDATO"], errors="coerce").astype("Int64").values,
        "nm_urna": c["NM_URNA_CANDIDATO"].values,
        "nm_candidato": c["NM_CANDIDATO"].values,
        "sg_partido": c["SG_PARTIDO"].values,
        "agremiacao": [agremiacao(p, f) for p, f in zip(c["SG_PARTIDO"], c["SG_FEDERACAO"])],
        "foi_a_voto": (c["NM_TIPO_DESTINACAO_VOTOS"] == "Válido").values,
        "sit_tot_1t": c["DS_SIT_TOT_TURNO"].values,
        "sit_tot_2t": c["SQ_CANDIDATO"].map(turno2).values,
        "ds_genero": c["DS_GENERO"].map(texto_tse).values,
        "ds_cor_raca": c["DS_COR_RACA"].map(texto_tse).values,
        "ds_grau_instrucao": c["DS_GRAU_INSTRUCAO"].map(texto_tse).values,
        "genero": c["DS_GENERO"].map(GENERO).fillna(NAO_INFORMADO).values,
        "cor_raca": c["DS_COR_RACA"].map(COR_RACA).fillna(NAO_INFORMADO).values,
        "instrucao": c["DS_GRAU_INSTRUCAO"].map(INSTRUCAO).fillna(NAO_INFORMADO).values,
        "idade": idade_na_data(c["DT_NASCIMENTO"], DATA_ELEICAO[ano]).values,
        "pessoa": [chave_pessoa(cpf, n, d) for cpf, n, d in
                   zip(c["NR_CPF_CANDIDATO"], c["NM_CANDIDATO"], c["DT_NASCIMENTO"])],
        "pessoa_por_cpf": c["NR_CPF_CANDIDATO"].astype(str).str.fullmatch(r"\d{11}").values,
    })
    base["cargo"] = base["cd_cargo"].map(CARGOS)
    base["faixa_etaria"] = faixa_etaria(base["idade"])
    base["titulo"] = base["nm_urna"].map(titulo_nome_urna)

    if ano < 2026:
        base["situacao"] = [situacao_final(a, b) for a, b in zip(base["sit_tot_1t"], base["sit_tot_2t"])]
        base["st_json"] = None
    else:
        sit, _ = situacoes_2026()
        sit = sit.drop_duplicates("sq_candidato").set_index("sq_candidato")
        base["st_json"] = base["sq_candidato"].map(sit["st_json"])
        base["dvt_json"] = base["sq_candidato"].map(sit["dvt_json"])
        base["situacao"] = [situacao_json(s) if isinstance(s, str) else None for s in base["st_json"]]
        # Candidatos substituídos depois de a urna ser preparada (o substituto herda
        # o número e os votos) seguem "Válido" no arquivo complementar, mas não
        # aparecem no resultado: não contam como quem foi a voto.
        base["substituido"] = base["foi_a_voto"] & base["st_json"].isna()
        base["foi_a_voto"] = base["foi_a_voto"] & base["st_json"].notna()
    return base


# ---------------------------------------------------------------------------------
# Página "Perfil dos candidatos"
# ---------------------------------------------------------------------------------

def com_todos_os_cargos(d: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([d, d.assign(cargo=TODOS)], ignore_index=True)


def tabela_perfil(base: pd.DataFrame) -> pd.DataFrame:
    """Contagem por ano, cargo, grupo (candidatos, eleitos, 2º turno), dimensão e categoria."""
    v = base[base["foi_a_voto"]]
    grupos = pd.concat([v.assign(grupo="Candidatos"),
                        v[v["situacao"] == ELEITO].assign(grupo="Eleitos"),
                        v[v["situacao"] == SEGUNDO_TURNO].assign(grupo="No 2º turno")], ignore_index=True)
    dimensoes = {"genero": "Gênero", "cor_raca": "Cor ou raça", "faixa_etaria": "Faixa etária",
                 "instrucao": "Grau de instrução"}
    longo = com_todos_os_cargos(grupos).melt(id_vars=["ano", "cargo", "grupo"], value_vars=list(dimensoes),
                                             var_name="dimensao", value_name="categoria")
    longo["dimensao"] = longo["dimensao"].map(dimensoes)
    return longo.groupby(["ano", "cargo", "grupo", "dimensao", "categoria"]).size().rename("n").reset_index()


CONSULTAS_SIDRA = {
    "sexo": "c1568/120704/c58/95253/c2/4,5/c86/95251",
    "cor_raca": "c1568/120704/c58/95253/c2/6794/c86/2776,2777,2778,2779,2780",
    "idade": "c1568/120704/c58/2793,1144,1145,1146,1147,1148,1149,1150,1151,1152,1153,1154,1155,2503"
             "/c2/6794/c86/95251",
    "instrucao": "c1568/9493,9494,9495,99713/c58/108866/c2/6794/c86/95251",
}
IDADE_IBGE = {"18 a 19 anos": 18, "20 a 24 anos": 20, "25 a 29 anos": 25, "30 a 34 anos": 30, "35 a 39 anos": 35,
              "40 a 44 anos": 40, "45 a 49 anos": 45, "50 a 54 anos": 50, "55 a 59 anos": 55, "60 a 64 anos": 60,
              "65 a 69 anos": 65, "70 a 74 anos": 70, "75 a 79 anos": 75, "80 anos ou mais": 80}
INSTRUCAO_IBGE = {"Sem instrução e fundamental incompleto": "Até fundamental incompleto",
                  "Fundamental completo e médio incompleto": "Fundamental completo",
                  "Médio completo e superior incompleto": "Médio completo",
                  "Superior completo": "Superior completo"}


def tabela_populacao() -> pd.DataFrame:
    def ler(nome: str, classificacao: str) -> pd.DataFrame:
        caminho = BRUTOS / "ibge" / f"censo2022_t10061_{nome}.json"
        return ler_sidra(json.loads(caminho.read_text(encoding="utf-8")), classificacao)

    sexo = ler("sexo", "Sexo").assign(dimensao="Gênero", base="18 anos ou mais")
    sexo["categoria"] = sexo["categoria_ibge"].map({"Homens": "Homens", "Mulheres": "Mulheres"})
    cor = ler("cor_raca", "Cor ou raça").assign(dimensao="Cor ou raça", base="18 anos ou mais")
    cor["categoria"] = cor["categoria_ibge"]
    idade = ler("idade", "Grupo de idade").assign(dimensao="Faixa etária", base="18 anos ou mais")
    idade["categoria"] = faixa_etaria(idade["categoria_ibge"].map(IDADE_IBGE))
    instrucao = ler("instrucao", "Nível de instrução").assign(dimensao="Grau de instrução", base="25 anos ou mais")
    instrucao["categoria"] = instrucao["categoria_ibge"].map(INSTRUCAO_IBGE)
    pop = pd.concat([sexo, cor, idade, instrucao], ignore_index=True)
    assert pop["categoria"].notna().all() and (pop["categoria"] != NAO_INFORMADO).all(), "categoria do IBGE sem par"
    return pop.groupby(["dimensao", "categoria", "base"], as_index=False)["pessoas"].sum()


def tabela_eleitos(base: pd.DataFrame, vagas_2026: pd.DataFrame) -> pd.DataFrame:
    """Conferência: eleitos e candidatos no 2º turno por cargo, contra as vagas."""
    v = base[base["foi_a_voto"]]
    linhas = []
    for (ano, cargo), d in v.groupby(["ano", "cargo"]):
        aguardando = d[d["situacao"] == AGUARDANDO]
        linhas.append({
            "ano": ano, "cargo": cargo, "vagas": VAGAS[cargo][ano],
            "candidatos": len(d),
            "eleitos": int((d["situacao"] == ELEITO).sum()),
            "no_2o_turno": int((d["situacao"] == SEGUNDO_TURNO).sum()),
            "aguardando_totalizacao": len(aguardando),
            "vagas_aguardando": int(vagas_2026[(vagas_2026["uf"].isin(aguardando["uf"].unique()))
                                               & (vagas_2026["cd_cargo"].isin(aguardando["cd_cargo"].unique()))
                                               ]["vagas"].sum()) if ano == 2026 and len(aguardando) else 0,
            "ufs_aguardando": ", ".join(sorted(aguardando["uf"].unique())),
        })
    t = pd.DataFrame(linhas)
    t["cargo"] = pd.Categorical(t["cargo"], ORDEM_CARGOS, ordered=True)
    return t.sort_values(["ano", "cargo"]).reset_index(drop=True)


def tabela_mulheres_partido(base: pd.DataFrame) -> pd.DataFrame:
    """2026, deputados: mulheres entre os pedidos de registro, entre quem foi a voto
    e entre os eleitos, por partido ou federação."""
    d = base[(base["ano"] == 2026) & base["cd_cargo"].isin(DEPUTADOS)].copy()
    d["mulher"] = d["genero"] == "Mulheres"
    d["a_voto"] = d["foi_a_voto"]
    d["a_voto_mulher"] = d["foi_a_voto"] & d["mulher"]
    d["eleito"] = d["foi_a_voto"] & (d["situacao"] == ELEITO)
    d["eleita"] = d["eleito"] & d["mulher"]
    t = (d.groupby(["cargo", "agremiacao"])
         .agg(registros=("mulher", "size"), registros_mulheres=("mulher", "sum"),
              candidatos=("a_voto", "sum"), candidatas=("a_voto_mulher", "sum"),
              eleitos=("eleito", "sum"), eleitas=("eleita", "sum"))
         .reset_index())
    return t.astype({c: "int64" for c in t.columns if c not in ("cargo", "agremiacao")})


def tabela_mulheres_anos(base: pd.DataFrame) -> pd.DataFrame:
    d = com_todos_os_cargos(base)
    d["mulher"] = d["genero"] == "Mulheres"
    d["a_voto_mulher"] = d["foi_a_voto"] & d["mulher"]
    d["eleito"] = d["foi_a_voto"] & (d["situacao"] == ELEITO)
    d["eleita"] = d["eleito"] & d["mulher"]
    t = (d.groupby(["ano", "cargo"])
         .agg(registros=("mulher", "size"), registros_mulheres=("mulher", "sum"),
              candidatos=("foi_a_voto", "sum"), candidatas=("a_voto_mulher", "sum"),
              eleitos=("eleito", "sum"), eleitas=("eleita", "sum"))
         .reset_index())
    return t.astype({c: "int64" for c in t.columns if c not in ("cargo",)})


def tabela_titulos(base: pd.DataFrame) -> pd.DataFrame:
    """Deputados: candidatos que foram a voto e eleitos por tipo de título no nome de urna."""
    d = base[base["foi_a_voto"] & base["cd_cargo"].isin(DEPUTADOS)].copy()
    d["com_resultado"] = d["situacao"].isin([ELEITO, NAO_ELEITO])
    d["eleito"] = d["situacao"] == ELEITO
    t = (d.groupby(["ano", "cargo", "titulo"])
         .agg(candidatos=("eleito", "size"), com_resultado=("com_resultado", "sum"), eleitos=("eleito", "sum"))
         .reset_index())
    return t.astype({"candidatos": "int64", "com_resultado": "int64", "eleitos": "int64"})


def tabela_reeleicao(base: pd.DataFrame) -> pd.DataFrame:
    """Deputados federais eleitos numa eleição: o que aconteceu na seguinte."""
    linhas = []
    for antes, depois in [(2018, 2022), (2022, 2026)]:
        eleitos = base[(base["ano"] == antes) & (base["cd_cargo"] == 6) & (base["situacao"] == ELEITO)
                       & base["foi_a_voto"]]
        seguinte = base[(base["ano"] == depois) & base["foi_a_voto"] & base["pessoa"].notna()]
        seguinte = seguinte.drop_duplicates("pessoa").set_index("pessoa")
        mesmo = seguinte[seguinte["cd_cargo"] == 6]
        outro = seguinte[seguinte["cd_cargo"] != 6]
        tentou = eleitos[eleitos["pessoa"].isin(mesmo.index)]
        sit = tentou["pessoa"].map(mesmo["situacao"])
        eleitos_depois = base[(base["ano"] == depois) & (base["cd_cargo"] == 6) & (base["situacao"] == ELEITO)
                              & base["foi_a_voto"]]
        valores = {
            "eleitos_antes": len(eleitos),
            "concorreram_de_novo": len(tentou),
            "concorreram_a_outro_cargo": int(eleitos["pessoa"].isin(outro.index).sum()),
            "reeleitos": int((sit == ELEITO).sum()),
            "nao_reeleitos": int((sit == NAO_ELEITO).sum()),
            "aguardando": int((sit == AGUARDANDO).sum()),
            "eleitos_depois": len(eleitos_depois),
            "eleitos_depois_que_ja_eram": int(eleitos_depois["pessoa"].isin(eleitos["pessoa"]).sum()),
        }
        linhas += [{"periodo": f"{antes} → {depois}", "ano_antes": antes, "ano_depois": depois,
                    "indicador": k, "n": v} for k, v in valores.items()]
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------------
# Página "Patrimônio declarado"
# ---------------------------------------------------------------------------------

MINIMO_GRUPO = 10  # grupos menores não têm mediana publicada


def bens(ano: int) -> pd.DataFrame:
    b = ler_do_zip("bem_candidato", ano, ["CD_TIPO_ELEICAO", "SQ_CANDIDATO", "CD_TIPO_BEM_CANDIDATO",
                                          "DS_BEM_CANDIDATO", "VR_BEM_CANDIDATO"])
    b = b[b["CD_TIPO_ELEICAO"] == "2"]
    cd = pd.to_numeric(b["CD_TIPO_BEM_CANDIDATO"], errors="coerce").fillna(99).astype(int)
    return pd.DataFrame({
        "ano": ano, "sq_candidato": b["SQ_CANDIDATO"].values,
        "categoria": [categoria_bem(c, d) for c, d in zip(cd, b["DS_BEM_CANDIDATO"])],
        "valor": valor_reais(b["VR_BEM_CANDIDATO"]).values,
    })


def grupo_situacao(situacao: pd.Series) -> pd.Series:
    return situacao.map({ELEITO: "Eleitos", SEGUNDO_TURNO: "No 2º turno", NAO_ELEITO: "Não eleitos"})


def resumo_patrimonio(d: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    linhas = []
    for chave, g in d.groupby(chaves):
        chave = chave if isinstance(chave, tuple) else (chave,)
        linhas.append({**dict(zip(chaves, chave)), "n": len(g),
                       "mediana": mediana_ou_nada(g["patrimonio"], MINIMO_GRUPO),
                       "zero": int((g["patrimonio"] <= 0).sum())})
    return pd.DataFrame(linhas)


def tabelas_patrimonio_2026(pat: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pat[pat["ano"] == 2026]
    d = pd.concat([d.assign(grupo="Todos"), d.assign(grupo=grupo_situacao(d["situacao"])).dropna(subset=["grupo"])],
                  ignore_index=True)
    d = com_todos_os_cargos(d)
    por_cargo = resumo_patrimonio(d, ["cargo", "grupo"])
    por_partido = resumo_patrimonio(d[d["grupo"] != "No 2º turno"], ["cargo", "sg_partido", "grupo"])
    return por_cargo, por_partido


def tabela_tipos_bens(b: pd.DataFrame, pat: pd.DataFrame) -> pd.DataFrame:
    """2026: valor declarado e quantos candidatos têm cada categoria de bem."""
    a_voto = pat[pat["ano"] == 2026]
    b = b[(b["ano"] == 2026) & b["sq_candidato"].isin(a_voto["sq_candidato"])]
    t = (b.groupby("categoria")
         .agg(valor=("valor", "sum"), bens=("valor", "size"), candidatos_com=("sq_candidato", "nunique"))
         .reindex(ORDEM_BENS).fillna(0).reset_index())
    t["candidatos_total"] = len(a_voto)
    return t.astype({"bens": "int64", "candidatos_com": "int64"})


def tabela_evolucao(pat: pd.DataFrame, fatores: dict[int, float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mesma pessoa em duas eleições: patrimônio corrigido pelo IPCA e variação real."""
    p = pat[pat["pessoa"].notna()].copy()
    p["real"] = p["patrimonio"] * p["ano"].map(fatores)
    p = p.drop_duplicates(["ano", "pessoa"])
    largo = {ano: p[p["ano"] == ano].set_index("pessoa") for ano in ANOS}

    linhas = []
    for antes, depois in [(2018, 2022), (2022, 2026), (2018, 2026)]:
        a, b = largo[antes], largo[depois]
        comuns = b.index.intersection(a.index)
        par = pd.DataFrame({"antes": a.loc[comuns, "real"], "depois": b.loc[comuns, "real"],
                            "cargo": b.loc[comuns, "cargo"], "sg_partido": b.loc[comuns, "sg_partido"]})
        par["variacao"] = np.where(par["antes"] > 0, par["depois"] / par["antes"].where(par["antes"] > 0) - 1, np.nan)
        par = com_todos_os_cargos(par)
        for recorte, coluna in [("cargo", "cargo"), ("partido", "sg_partido")]:
            dados = par if recorte == "cargo" else par[par["cargo"] == TODOS]
            for grupo, g in dados.groupby(coluna):
                com_base = g["variacao"].dropna()
                linhas.append({
                    "periodo": f"{antes} → {depois}", "ano_antes": antes, "ano_depois": depois,
                    "recorte": recorte, "grupo": grupo, "pessoas": len(g),
                    "mediana_antes": mediana_ou_nada(g["antes"], MINIMO_GRUPO),
                    "mediana_depois": mediana_ou_nada(g["depois"], MINIMO_GRUPO),
                    "pessoas_com_base": len(com_base),
                    "variacao_mediana": mediana_ou_nada(com_base, MINIMO_GRUPO),
                    "subiu": int((com_base > 0).sum()),
                })

    # tabela pesquisável: todos que foram a voto em 2026
    pessoas = largo[2026][["nm_urna", "nm_candidato", "uf", "cargo", "sg_partido", "situacao", "real"]].copy()
    pessoas = pessoas.rename(columns={"real": "patrimonio_2026"})
    for ano in (2018, 2022):
        pessoas[f"patrimonio_{ano}"] = largo[ano]["real"].reindex(pessoas.index)
    sem_cpf = pat[(pat["ano"] == 2026) & pat["pessoa"].isna()]
    pessoas = pd.concat([pessoas.reset_index(drop=True),
                         sem_cpf[["nm_urna", "nm_candidato", "uf", "cargo", "sg_partido", "situacao", "patrimonio"]]
                         .rename(columns={"patrimonio": "patrimonio_2026"})], ignore_index=True)
    pessoas["situacao"] = pessoas["situacao"].fillna(AGUARDANDO)
    pessoas = pessoas.sort_values(["nm_urna", "uf"]).reset_index(drop=True)
    for col in ("patrimonio_2018", "patrimonio_2022", "patrimonio_2026"):
        pessoas[col] = pessoas[col].round(0)
    return pd.DataFrame(linhas), pessoas[["nm_urna", "nm_candidato", "uf", "cargo", "sg_partido", "situacao",
                                          "patrimonio_2018", "patrimonio_2022", "patrimonio_2026"]]


def tabela_ligacao(base: pd.DataFrame) -> pd.DataFrame:
    """Quantos candidatos de cada ano foram encontrados nas eleições anteriores, e
    quanto a ligação por CPF concorda com o "Histórico de candidaturas" do TSE."""
    v = base[base["foi_a_voto"]]
    linhas = []
    for ano in ANOS:
        d = v[v["ano"] == ano]
        linhas.append({"chave": f"candidatos_{ano}", "valor": len(d)})
        linhas.append({"chave": f"com_cpf_{ano}", "valor": int(d["pessoa_por_cpf"].sum())})
        linhas.append({"chave": f"sem_chave_{ano}", "valor": int(d["pessoa"].isna().sum())})
    for antes, depois in [(2018, 2022), (2022, 2026), (2018, 2026)]:
        a = set(v.loc[v["ano"] == antes, "pessoa"].dropna())
        d = v[v["ano"] == depois]
        linhas.append({"chave": f"ligados_{antes}_{depois}", "valor": int(d["pessoa"].isin(a).sum())})
    tres = set.intersection(*[set(v.loc[v["ano"] == ano, "pessoa"].dropna()) for ano in ANOS])
    linhas.append({"chave": "ligados_tres_anos", "valor": len(tres)})

    # conferência com o histórico de candidaturas (só existe para quem concorreu em 2026)
    h = ler_do_zip("historico_candidatura", 2026, ["SQ_CANDIDATO_ATUAL", "ANO_ELEICAO", "CD_TIPO_ELEICAO",
                                                   "SQ_CANDIDATO"])
    todos = base.set_index(["ano", "sq_candidato"])["pessoa"]
    for antes in (2018, 2022):
        hh = h[(h["ANO_ELEICAO"] == str(antes)) & (h["CD_TIPO_ELEICAO"] == "2")].drop_duplicates()
        p_atual = hh["SQ_CANDIDATO_ATUAL"].map(todos.loc[2026])
        p_antes = hh["SQ_CANDIDATO"].map(todos.loc[antes])
        avaliaveis = p_atual.notna() & p_antes.notna()
        linhas.append({"chave": f"historico_pares_{antes}", "valor": int(avaliaveis.sum())})
        linhas.append({"chave": f"historico_confirmados_{antes}", "valor": int((p_atual == p_antes)[avaliaveis].sum())})
    return pd.DataFrame(linhas).astype({"valor": "float64"})


def tabela_powerbi(pat: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por candidatura que foi a voto (2018, 2022 e 2026), para o Power BI."""
    d = pat.sort_values(["ano", "uf", "cd_cargo", "nm_urna"])
    return pd.DataFrame({
        "ano": d["ano"].astype("int16").values,
        "uf": d["uf"].values,
        "cd_cargo": d["cd_cargo"].astype("int8").values,
        "ds_cargo": d["cd_cargo"].map(NOME_CARGO).values,
        "sq_candidato": d["sq_candidato"].values,
        "nr_candidato": d["nr_candidato"].values,
        "nm_urna": d["nm_urna"].values,
        "sg_partido": d["sg_partido"].values,
        "ds_genero": d["ds_genero"].values,
        "ds_cor_raca": d["ds_cor_raca"].values,
        "idade": d["idade"].round().astype("Int64").values,
        "ds_grau_instrucao": d["ds_grau_instrucao"].values,
        "situacao": [situacao_texto(a, s1, s2, sj) for a, s1, s2, sj in
                     zip(d["ano"], d["sit_tot_1t"], d["sit_tot_2t"], d["st_json"])],
        "eleito": (d["situacao"] == ELEITO).values,
        "vr_patrimonio": d["patrimonio"].round().astype("int64").values,
    })


# ---------------------------------------------------------------------------------
# Conferências impressas no fim
# ---------------------------------------------------------------------------------

def conferir(base: pd.DataFrame, eleitos: pd.DataFrame) -> None:
    print("\nCandidaturas que foram a voto e eleitos, por ano e cargo:")
    print(eleitos.to_string(index=False))
    erro_eleitos = base[(base["situacao"] == ELEITO) & ~base["foi_a_voto"]]
    print(f"\nEleitos fora do critério 'foi a voto': {len(erro_eleitos)}")
    d26 = base[base["ano"] == 2026]
    print(f"2026: substituídos ('Válido' no complementar, ausentes do resultado; ficam de fora): "
          f"{int(d26['substituido'].sum())}")
    destino_difere = d26[d26["st_json"].notna() & (d26["foi_a_voto"] != (d26["dvt_json"] == "Válido"))]
    print(f"2026: destinação do voto diferente entre o arquivo complementar e o resultado: {len(destino_difere)}")
    sit_csv = [situacao_final(s, None) for s in d26["sit_tot_1t"]]
    compara = pd.DataFrame({"json": d26["situacao"], "csv": sit_csv})[d26["foi_a_voto"].values]
    print("2026: situação nos resultados (linhas) x DS_SIT_TOT_TURNO do consulta_cand publicado em 09/10 (colunas):")
    print(pd.crosstab(compara["json"].fillna("-"), compara["csv"].fillna("sem totalização")).to_string())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--atualizar", action="store_true", help="baixa de novo todos os arquivos")
    args = parser.parse_args()

    baixar_tudo(args.atualizar)
    base = pd.concat([candidaturas(ano) for ano in ANOS], ignore_index=True)
    _, vagas_2026 = situacoes_2026()

    # patrimônio de quem foi a voto (quem não declarou bens tem patrimônio zero)
    todos_bens = pd.concat([bens(ano) for ano in ANOS], ignore_index=True)
    totais = todos_bens.groupby(["ano", "sq_candidato"])["valor"].sum()
    pat = base[base["foi_a_voto"]].copy()
    pat["patrimonio"] = pd.Series(list(zip(pat["ano"], pat["sq_candidato"])), index=pat.index).map(totais).fillna(0.0)

    powerbi = tabela_powerbi(pat)
    powerbi.to_parquet(BRUTOS / "candidaturas.parquet", index=False)
    print(f"{(BRUTOS / 'candidaturas.parquet').relative_to(RAIZ)}: {len(powerbi)} candidaturas "
          f"({powerbi.groupby('ano').size().to_dict()}), {int(powerbi['eleito'].sum())} eleitos")

    indice = indice_ipca(json.loads((BRUTOS / "ipca_sidra1737.json").read_text(encoding="utf-8")))
    fatores, referencia = fatores_ipca(indice, ANOS)

    SAIDA.mkdir(parents=True, exist_ok=True)
    eleitos = tabela_eleitos(base, vagas_2026)
    saidas = {
        "candidatos_perfil": tabela_perfil(base),
        "candidatos_populacao": tabela_populacao(),
        "candidatos_eleitos": eleitos.assign(cargo=eleitos["cargo"].astype(str)),
        "candidatos_mulheres_partido": tabela_mulheres_partido(base),
        "candidatos_mulheres_anos": tabela_mulheres_anos(base),
        "candidatos_titulos": tabela_titulos(base),
        "candidatos_reeleicao": tabela_reeleicao(base),
    }
    por_cargo, por_partido = tabelas_patrimonio_2026(pat)
    evolucao, pessoas = tabela_evolucao(pat, fatores)
    tipos = tabela_tipos_bens(todos_bens, pat)
    p26 = pat.loc[pat["ano"] == 2026, "patrimonio"].sort_values(ascending=False)
    resumo = pd.concat([tabela_ligacao(base), pd.DataFrame([
        {"chave": "ipca_referencia", "valor": float(referencia.year * 100 + referencia.month)},
        *[{"chave": f"ipca_fator_{ano}", "valor": f} for ano, f in fatores.items()],
        {"chave": "parcela_1pct_maiores_2026", "valor": float(p26.head(len(p26) // 100).sum() / p26.sum())},
        {"chave": "minimo_grupo", "valor": float(MINIMO_GRUPO)},
    ])], ignore_index=True)
    saidas.update({
        "patrimonio_cargo": por_cargo, "patrimonio_partido": por_partido, "patrimonio_tipos": tipos,
        "patrimonio_evolucao": evolucao, "patrimonio_pessoas": pessoas, "patrimonio_resumo": resumo,
    })
    for nome, tabela in saidas.items():
        destino = SAIDA / f"{nome}.parquet"
        tabela.to_parquet(destino, index=False, compression="zstd")
        print(f"{destino.relative_to(RAIZ)}: {len(tabela)} linhas, {destino.stat().st_size / 1024:.0f} KB")

    conferir(base, eleitos)
    print(f"\nIPCA: valores levados para {referencia:%m/%Y}; fatores {fatores}")
    print(resumo.to_string(index=False))


if __name__ == "__main__":
    main()
