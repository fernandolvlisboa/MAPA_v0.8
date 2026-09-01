"""Teste de fumaça do ponto de entrada interativo (main.py)."""

import subprocess
import sys
from pathlib import Path

import main

RAIZ = Path(__file__).resolve().parent.parent


def test_slug_gera_nome_de_arquivo_seguro():
    assert main._slug("Real Life Ltda") == "Real_Life_Ltda"
    assert main._slug("A/B: C") == "A_B_C"
    assert main._slug("   ") == "cliente"  # fallback


def test_menu_tem_as_acoes_esperadas():
    assert set(main._OPCOES) == {"0", "1", "2", "3"}
    # toda opção != sair aponta para um callable
    for chave, (_, acao) in main._OPCOES.items():
        assert (acao is None) == (chave == "0")


def test_menu_abre_e_sai_limpo():
    """`python main.py --menu` e escolher 0 deve encerrar com código 0."""
    proc = subprocess.run(
        [sys.executable, "main.py", "--menu"],
        input="0\n",
        capture_output=True,
        text=True,
        cwd=RAIZ,
        timeout=60,
    )
    assert proc.returncode == 0
    assert "BP — Padronização de Balancetes" in proc.stdout
    assert "Até logo" in proc.stdout


def test_opcao_invalida_nao_derruba():
    proc = subprocess.run(
        [sys.executable, "main.py", "--menu"],
        input="banana\n0\n",
        capture_output=True,
        text=True,
        cwd=RAIZ,
        timeout=60,
    )
    assert proc.returncode == 0
    assert "opção inválida" in proc.stdout


def test_sem_argumento_abre_a_janela(monkeypatch):
    """
    ``python main.py`` (sem bandeira) chama a janela do usuário final — o
    mesmo alvo que o executável vai abrir. Este é o comportamento novo que a
    apresentação exige (`main` é a vitrine, não o menu).
    """
    chamadas: list[str] = []

    def _falso_abrir():
        chamadas.append("abriu")
        return 0

    monkeypatch.setattr("src.bp.app.main", _falso_abrir)
    assert main.main([]) == 0
    assert chamadas == ["abriu"]


def test_help_nao_abre_nada(capsys):
    assert main.main(["--help"]) == 0
    assert "menu de terminal" in capsys.readouterr().out
