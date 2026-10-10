"""Testes do leitor do RDV (Registro Digital do Voto), com arquivos reais de urnas."""

from pathlib import Path

from eleicoes.rdv import TIPOS, ler_rdv

FIXTURES = Path(__file__).parent / "fixtures"


def por_cargo(votos):
    total = {}
    for (_, cargo, _, _), q in votos.items():
        total[cargo] = total.get(cargo, 0) + q
    return total


def test_rdv_2022_conta_os_votos_por_cargo_e_numero():
    # urna da seção 446, zona 4, município 1074 (AC), 1º turno de 2022
    votos = ler_rdv((FIXTURES / "o00406-0107400040446.rdv").read_bytes())
    # todo eleitor vota para os 5 cargos, então cada cargo tem o mesmo total
    assert por_cargo(votos) == {1: 104, 3: 104, 5: 104, 6: 104, 7: 104}
    assert votos[(544, 1, 2, "22")] == 81      # 81 votos nominais no 22 para Presidente
    assert votos[(544, 1, 3, "")] == 1         # 1 voto em branco para Presidente


def test_rdv_2026_tem_formato_novo_e_dois_senadores():
    votos = ler_rdv((FIXTURES / "o03220ac0101500020088-rdv.dat").read_bytes())
    totais = por_cargo(votos)
    assert totais[1] == totais[3] == totais[6] == totais[7] == 141
    assert totais[5] == 2 * 141                # em 2026 cada eleitor votou em 2 senadores
    assert {e for e, *_ in votos} == {6257, 6259}


def test_rdv_so_tem_tipos_conhecidos_e_nulos_guardam_o_numero():
    votos = ler_rdv((FIXTURES / "o03220ac0101500020088-rdv.dat").read_bytes())
    assert {tipo for _, _, tipo, _ in votos} <= set(TIPOS)
    assert all(digitos == "" for _, _, tipo, digitos in votos if tipo == 3)   # branco não tem número
