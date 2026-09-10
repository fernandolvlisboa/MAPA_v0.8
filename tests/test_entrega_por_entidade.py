"""
Uma entrega por ENTIDADE, não uma coluna por entidade.

Uma pasta de trabalho real trazia dois balanços — holding e controlada — em abas
distintas, do mesmo período. Tratá-los como "exercícios" somaria duas empresas
numa só planilha (uma vira coluna da outra). Cada entidade é uma entrega própria.

Ver REVISAO_QUALIDADE.md §33 e `service.gerar_por_entidade`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import require_corpus_file

from src.bp.app import service


# ---------------------------------------------------------------------------
# Discriminante exercícios × entidades (puro, sem arquivo)
# ---------------------------------------------------------------------------


def test_serie_historica_e_exercicios():
    """Um ano distinto por aba = série histórica (uma entrega, várias colunas)."""
    p = Path("x.xlsx")
    entradas = [
        service.Entrada(p, ano=2023, aba="Balancetes 2023"),
        service.Entrada(p, ano=2024, aba="Balancetes 2024"),
        service.Entrada(p, ano=2025, aba="Balancetes 2025"),
    ]
    assert service.e_serie_de_exercicios(entradas)


def test_mesmo_periodo_sao_entidades():
    """Duas abas do MESMO ano não são série — são empresas diferentes."""
    p = Path("x.xlsx")
    entradas = [
        service.Entrada(p, ano=2024, aba="Holding"),
        service.Entrada(p, ano=2024, aba="Controlada"),
    ]
    assert not service.e_serie_de_exercicios(entradas)


def test_uma_aba_so_e_caminho_normal():
    assert service.e_serie_de_exercicios([service.Entrada(Path("x.xlsx"), ano=2024)])


def test_rotulo_da_entidade_distingue_as_empresas():
    p = Path("x.xlsx")
    e = service.Entrada(p, ano=2024, aba="LA BSB")
    assert service.rotulo_da_entidade(e, "Grupo LA") == "Grupo LA - LA BSB"
    # Sem cliente digitado, a própria aba nomeia a entidade.
    assert service.rotulo_da_entidade(e, "") == "LA BSB"


# ---------------------------------------------------------------------------
# Fim a fim: duas entidades -> dois arquivos (usa corpus quando presente)
# ---------------------------------------------------------------------------

ARQUIVO_DUAS_ENTIDADES = "WP Mais valia - LA BSB v2 1.xls"
ABAS = ("LA BSB", "2008 Emp")


def test_duas_entidades_geram_dois_arquivos(tmp_path):
    caminho = require_corpus_file(ARQUIVO_DUAS_ENTIDADES)
    entradas = [service.Entrada(caminho, ano=2024, aba=a) for a in ABAS]

    # Não é série: o app deve oferecer uma entrega por entidade.
    assert not service.e_serie_de_exercicios(entradas)

    resultados = service.gerar_por_entidade(entradas, tmp_path, "Grupo LA")

    assert len(resultados) == len(ABAS)
    assert all(r.ok for r in resultados), [r.erro for r in resultados if not r.ok]

    arquivos = sorted(p.name for p in tmp_path.glob("*.xlsx"))
    assert len(arquivos) == 2, f"esperava uma entrega por entidade, veio {arquivos}"
    # Cada arquivo nomeia a sua empresa — não se sobrescrevem nem se fundem.
    # (o nome de saída troca espaços por "_", então comparamos sem separadores)
    def _achatar(s: str) -> str:
        return s.replace(" ", "").replace("_", "").lower()

    achatados = [_achatar(a) for a in arquivos]
    assert any("labsb" in a for a in achatados), arquivos
    assert any("2008emp" in a for a in achatados), arquivos


def test_entidades_nao_se_sobrescrevem(tmp_path):
    """Os dois arquivos coexistem: caminhos distintos, nenhum perde o outro."""
    caminho = require_corpus_file(ARQUIVO_DUAS_ENTIDADES)
    entradas = [service.Entrada(caminho, ano=2024, aba=a) for a in ABAS]
    resultados = service.gerar_por_entidade(entradas, tmp_path, "Grupo LA")
    saidas = {r.saida for r in resultados if r.ok}
    assert len(saidas) == len(resultados), "duas entidades gravaram no mesmo arquivo"
