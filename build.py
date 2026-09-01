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
    """Roda o teste anti-vazamento em cima do binario recem-criado."""
    _passo("Auditando o .exe (nenhum arquivo de cliente pode estar dentro)")
    _rodar([
        sys.executable, "-m", "pytest", "-q", "-x",
        "tests/test_build_seguranca.py",
    ])


def resumo() -> None:
    tamanho_mb = EXE_ESPERADO.stat().st_size / (1024 * 1024)
    _passo("Pronto")
    print(f"  binario: {EXE_ESPERADO}")
    print(f"  tamanho: {tamanho_mb:.1f} MB")
    print("\nEntregue esse arquivo — sem instalar nada — para quem for usar.")


def main() -> int:
    compilar()
    auditar()
    resumo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
