#!/usr/bin/env python
"""
Constroi MAPA.exe e valida que ele nao carrega dado de cliente.

Uso:

    uv run python build.py

Dois passos, um script:

1. **Compila** com PyInstaller usando `bp.spec` (allowlist de recursos —
   nada entra sem estar declarado la).
2. **Audita** o `.exe` gerado: descompacta em uma pasta temporaria e checa,
   arquivo por arquivo, que nada de cliente foi junto. Falha o comando com
   codigo != 0 se achar; nao entrega um `.exe` inseguro.

O `.exe` sai em `dist/MAPA.exe`. Roda de qualquer conta Windows — nao
precisa de admin porque o modo onefile descompacta em %TEMP% do usuario.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SPEC = RAIZ / "bp.spec"
EXE_ESPERADO = RAIZ / "dist" / ("MAPA.exe" if sys.platform == "win32" else "MAPA")


def _passo(msg: str) -> None:
    print(f"\n=== {msg} ===", flush=True)


def _rodar(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd), flush=True)
    resultado = subprocess.run(cmd, cwd=RAIZ)
    if resultado.returncode != 0:
        raise SystemExit(resultado.returncode)


def compilar() -> None:
    _passo(f"Compilando {SPEC.name}")
    if not SPEC.exists():
        raise SystemExit(f"nao encontrei {SPEC}")
    _rodar([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)])
    if not EXE_ESPERADO.exists():
        raise SystemExit(f"PyInstaller nao gerou {EXE_ESPERADO}")


def auditar() -> None:
    """
    Roda a auditoria em cima do binario recem-criado.

    Sao duas perguntas: nada de cliente entrou, e o que PRECISA entrar entrou —
    inclusive a biblioteca `tkdnd` do arrastar-e-soltar, que ficou de fora do
    .exe da v0.8 e so apareceu quando o binario ja estava circulando.

    A auditoria depende de `pyinstxtractor-ng` (extra `packaging`). Sem ele os
    testes PULAM, e um build que pula a auditoria inteira e um build nao
    auditado — este passo entao para, em vez de deixar passar por omissao.
    """
    _passo("Auditando o .exe (dado de cliente fora, recursos obrigatorios dentro)")
    if importlib.util.find_spec("pyinstxtractor_ng") is None:
        raise SystemExit(
            "pyinstxtractor-ng nao esta instalado, entao a auditoria nao roda e "
            "o .exe sai SEM CONFERENCIA — nem de vazamento de dado de cliente, "
            "nem da biblioteca do arrastar-e-soltar.\n"
            "Instale o extra de empacotamento:\n"
            "    uv sync --extra packaging"
        )
    _rodar([
        sys.executable, "-m", "pytest", "-q", "-x",
        "tests/test_build_seguranca.py",
    ])


def autotestar() -> None:
    """
    Roda o `.exe` recem-criado e exige que ele complete o pipeline.

    A auditoria confere o CONTEUDO do binario. Este passo confere que ele
    FUNCIONA — e e o que faltava. O .exe distribuido aos usuarios abria, aceitava
    o balancete e morria em "No module named 'pandas.plotting'": bp.spec excluia
    do bundle um modulo que `import pandas` carrega. Nenhum dos 617 testes pegou,
    porque todos rodam sobre a arvore de codigo, onde pandas esta inteiro.

    Um `.exe` so se prova rodando. Se este passo falha, o binario nao sai.
    """
    _passo("Autoteste: o .exe roda o pipeline completo?")
    resultado = subprocess.run([str(EXE_ESPERADO), "--autoteste"], cwd=RAIZ)
    relatorio = EXE_ESPERADO.parent / "MAPA_autoteste.txt"
    if relatorio.exists():
        print(relatorio.read_text(encoding="utf-8"))
    if resultado.returncode != 0:
        raise SystemExit(
            "O .exe NAO completou o pipeline. NAO DISTRIBUA este binario.\n"
            f"Relatorio: {relatorio}\n"
            "Causa tipica: `excludes` do bp.spec tirando um modulo que uma "
            "biblioteca carrega sozinha (foi o caso de pandas.plotting)."
        )


def resumo() -> None:
    tamanho_mb = EXE_ESPERADO.stat().st_size / (1024 * 1024)
    _passo("Pronto")
    print(f"  binario: {EXE_ESPERADO}")
    print(f"  tamanho: {tamanho_mb:.1f} MB")
    print("\nEntregue esse arquivo — sem instalar nada — para quem for usar.")


def main() -> int:
    compilar()
    auditar()
    autotestar()
    resumo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
