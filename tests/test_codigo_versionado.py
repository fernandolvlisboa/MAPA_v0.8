"""
O codigo-fonte chega inteiro ao repositorio? — o guard do `.gitignore`.

O que aconteceu
---------------

Na limpeza que preparou o repositorio publico, o `.gitignore` ganhou uma
regra para nao versionar a pasta de saida::

    output/

Sem barra inicial, esse padrao casa **qualquer** diretorio chamado ``output``
em qualquer profundidade. E existe um: ``src/bp/output/``, o pacote que monta
a entrega — ``build_gt_output.py``, ``origem.py``, ``template_map.py``.

O repositorio publico foi ao ar sem ele. O efeito:

- ``pytest --collect-only`` parava com 5 arquivos de teste sem importar
  (``ModuleNotFoundError: No module named 'src.bp.output'``);
- o programa **abria normalmente** — ``service.py`` e ``main.py`` importam o
  modulo de forma tardia — e morria exatamente na hora de gerar o Template
  GT, que e a razao de o programa existir.

O defeito nao estava no codigo. Estava no que o codigo *nao* chegou a ser.
Nenhum teste do mundo que rode sobre a arvore local pega isso, porque
localmente o arquivo esta la: so o git nao o leva.

O guard
-------

Este teste pergunta ao proprio git — ``git check-ignore`` — se algum arquivo
de codigo sob ``src/`` esta sendo ignorado. E a mesma pergunta que o defeito
respondeu errado, feita antes do commit em vez de depois do push.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

#: Extensoes que compoem o pacote instalavel. Dado de cliente (`.xlsx` de
#: balancete) fica de fora de proposito: aquele **deve** ser ignorado.
EXTENSOES_DE_CODIGO = {".py", ".json", ".md"}


def _e_repo_git() -> bool:
    return (RAIZ / ".git").exists()


def _arquivos_de_codigo() -> list[Path]:
    return sorted(
        p
        for p in (RAIZ / "src").rglob("*")
        if p.is_file()
        and p.suffix in EXTENSOES_DE_CODIGO
        and "__pycache__" not in p.parts
        # Cache de treino e estado, nao codigo — e ignorado por design.
        and not p.name.endswith(("_cache.json", "_stats.json"))
        and "_backup_master_train" not in p.parts
        and "DFS_Exemple" not in p.parts
    )


@pytest.mark.skipif(not _e_repo_git(), reason="fora de um clone git")
def test_nenhum_arquivo_de_codigo_e_ignorado_pelo_git():
    """
    A pergunta que faltava: o que eu escrevi vai junto quando eu empurrar?

    Falha nomeando o arquivo **e a linha do `.gitignore`** que o engole —
    porque a primeira coisa que se quer saber e qual regra foi longe demais.
    """
    arquivos = _arquivos_de_codigo()
    assert len(arquivos) > 50, (
        f"so {len(arquivos)} arquivos de codigo sob src/ — o teste seria vacuoso"
    )

    resultado = subprocess.run(
        ["git", "check-ignore", "-v", "--stdin"],
        input="\n".join(str(p.relative_to(RAIZ)) for p in arquivos),
        capture_output=True,
        text=True,
        cwd=RAIZ,
    )
    # check-ignore sai com 0 quando ACHOU algo ignorado, 1 quando nao achou.
    if resultado.returncode == 1 and not resultado.stdout.strip():
        return
    assert not resultado.stdout.strip(), (
        "arquivo(s) de codigo sob src/ estao no .gitignore — eles nao chegam "
        "ao repositorio, e o clone publico fica sem eles:\n"
        + resultado.stdout
    )


@pytest.mark.skipif(not _e_repo_git(), reason="fora de um clone git")
def test_o_pacote_da_entrega_esta_versionado():
    """
    O caso concreto, nomeado.

    ``src/bp/output/`` e o unico caminho de codigo cujo nome colide com um
    diretorio de artefato. Vale citar explicitamente: se alguem reintroduzir
    ``output/`` sem barra, este teste diz exatamente o que se perdeu.
    """
    rastreados = subprocess.run(
        ["git", "ls-files", "src/bp/output"],
        capture_output=True, text=True, cwd=RAIZ,
    ).stdout.split()
    for modulo in ("__init__.py", "build_gt_output.py", "origem.py", "template_map.py"):
        assert f"src/bp/output/{modulo}" in rastreados, (
            f"src/bp/output/{modulo} nao esta versionado — sem ele o programa "
            f"le o balancete e nao entrega o Template GT"
        )


@pytest.mark.skipif(not _e_repo_git(), reason="fora de um clone git")
def test_dado_de_cliente_continua_ignorado():
    """
    Nao-vacuidade, do lado oposto: o guard nao pode ter afrouxado a regra que
    protege dado de cliente. ``docs/DADOS_PRIVADOS.md`` depende dela.
    """
    alvos = [
        "src/bp/training/DFS_Exemple/Balancete de um cliente.xlsx",
        "auxil/BP_PDF_ex/DF de um cliente.pdf",
        "data/samples/Balancete de um cliente.xlsx",
        "output/saida.xlsx",
    ]
    resultado = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        input="\n".join(alvos), capture_output=True, text=True, cwd=RAIZ,
    )
    ignorados = set(resultado.stdout.split("\n"))
    for alvo in alvos:
        assert alvo in ignorados, f"{alvo} deixou de ser ignorado pelo .gitignore"
