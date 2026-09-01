"""
Verificação de dependências do projeto BP usando uv
Compara pyproject.toml com pacotes instalados
"""

import tomllib
from pathlib import Path
import subprocess
import json


def get_installed_packages_uv():
    """Retorna dict {package_name: version} dos pacotes instalados via uv"""
    result = subprocess.run(
        ["uv", "pip", "list", "--format=json"], capture_output=True, text=True
    )
    packages = json.loads(result.stdout)
    # Normalizar nomes: pdfminer-six -> pdfminer.six
    normalized = {}
    for pkg in packages:
        name = pkg["name"].lower()
        # Adicionar tanto com - quanto com .
        normalized[name] = pkg["version"]
        normalized[name.replace("-", ".")] = pkg["version"]
        normalized[name.replace(".", "-")] = pkg["version"]
    return normalized


def parse_requirement(req_str):
    """Extrai nome e versão de requirement string (ex: 'pandas>=2.3.3')"""
    import re

    # Regex para capturar nomes com - ou . (ex: pdfminer.six, python-dotenv)
    match = re.match(r"^([a-zA-Z0-9_.-]+)([><=!]+)?(.+)?$", req_str)
    if match:
        name = match.group(1).lower()
        operator = match.group(2) or ""
        version = match.group(3) or ""
        return name, operator, version
    return req_str.lower(), "", ""


def main():
    # Carregar pyproject.toml
    pyproject_path = Path("pyproject.toml")
    with open(pyproject_path, "rb") as f:
        config = tomllib.load(f)

    required = config.get("project", {}).get("dependencies", [])
    dev_deps = config.get("dependency-groups", {}).get("dev", [])

    # Pacotes instalados
    try:
        installed = get_installed_packages_uv()
    except FileNotFoundError:
        print("[ERRO] uv nao encontrado. Instale com: pip install uv")
        return
    except Exception as e:
        print(f"[ERRO] Falha ao listar pacotes: {e}")
        return

    print("=" * 80)
    print("VERIFICACAO DE DEPENDENCIAS (usando uv)")
    print("=" * 80)
    print()

    # Verificar dependências principais
    print("DEPENDENCIAS PRINCIPAIS:")
    print("-" * 80)

    missing = []
    ok = []

    for req in required:
        name, op, ver = parse_requirement(req)

        if name in installed:
            installed_ver = installed[name]
            ok.append((name, installed_ver, f"{op}{ver}" if ver else "any"))
        else:
            missing.append((name, f"{op}{ver}" if ver else "any"))

    # Resultados
    if ok:
        print(f"\n[OK] INSTALADAS ({len(ok)}):")
        for name, inst_ver, req_ver in sorted(ok):
            print(f"  {name:30s} {inst_ver:15s} (requerido: {req_ver})")

    if missing:
        print(f"\n[FALTANDO] ({len(missing)}):")
        for name, req_ver in missing:
            print(f"  {name:30s} (requerido: {req_ver})")

    # Dependências de desenvolvimento
    if dev_deps:
        print()
        print("=" * 80)
        print("DEPENDENCIAS DE DESENVOLVIMENTO:")
        print("-" * 80)

        for req in dev_deps:
            name, op, ver = parse_requirement(req)
            if name in installed:
                print(f"  [OK] {name:30s} {installed[name]}")
            else:
                print(f"  [FALTANDO] {name:30s} (requerido: {op}{ver})")

    # Resumo
    print()
    print("=" * 80)
    print("RESUMO:")
    print(f"  Total requerido: {len(required)}")
    print(f"  Instaladas OK:   {len(ok)}")
    print(f"  Faltando:        {len(missing)}")

    if missing:
        print()
        print("ACAO RECOMENDADA:")
        print("  uv pip install -e .")
        print()
        print("  Ou individualmente:")
        for name, req_ver in missing:
            spec = f"{name}{req_ver}" if req_ver != "any" else name
            print(f"  uv pip install {spec}")
    else:
        print()
        print("[OK] Todas as dependencias estao instaladas corretamente!")

    print("=" * 80)


if __name__ == "__main__":
    main()
