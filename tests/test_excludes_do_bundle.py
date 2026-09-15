"""
A lista de exclusões do `bp.spec` é medida, não raciocinada.

O que aconteceu
---------------

O `.exe` distribuído aos usuários abria, aceitava o balancete e morria na hora
de gerar::

    Não consegui carregar o motor do BP: No module named 'pandas.plotting'

Causa: `bp.spec` excluía `pandas.plotting` e `pandas.io.sql` do bundle, sob o
comentário *"Cada exclusão foi verificada: nenhum import de src/bp/app,
src/bp/output, src/bp/parsers, src/bp/matchers toca esses módulos"*.

A verificação estava certa. A conclusão, errada. **O que decide não é se NÓS
importamos o módulo — é se a BIBLIOTECA importa.** E `pandas/__init__.py`, na
linha 138, faz::

    from pandas import api, arrays, errors, io, plotting, tseries

`import pandas` carrega `pandas.plotting` e, via `pandas.io.api`,
`pandas.io.sql`. Excluídos, o pandas inteiro deixa de importar — e como o
motor é carregado tarde (``service.py`` importa ``build_gt_output`` só quando
o analista clica em Gerar), a janela abre normalmente e a falha só aparece na
última etapa, com o balancete já na tela.

O guard
-------

Este teste importa o que o app importa em runtime e pergunta ao próprio
``sys.modules`` quais módulos foram carregados. Qualquer nome da lista de
exclusões que apareça ali é uma exclusão fatal — o bundle sairia sem ele.

É a pergunta certa, e ela não depende de compilar nada: roda na suíte normal,
em qualquer sistema, em milissegundos.

Referência: ``REVISAO_QUALIDADE.md`` §24.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SPEC = RAIZ / "bp.spec"

#: Os módulos que o programa carrega para fazer o trabalho de verdade. É a
#: superfície que o `.exe` precisa ter: ler balancete, casar contas, montar a
#: entrega, desenhar a janela.
_IMPORTS_DE_RUNTIME = (
    "src.bp.parsers.dispatcher",
    "src.bp.matchers.conta_matcher",
    "src.bp.output.build_gt_output",
    "src.bp.output.origem",
    "src.bp.validators.hierarquia",
    "src.bp.validators.entrega",
    "src.bp.app.service",
)


def _excludes_do_spec() -> list[str]:
    """Lê a lista `excludes` direto do bp.spec, sem executá-lo."""
    texto = SPEC.read_text(encoding="utf-8")
    bloco = re.search(r"^excludes = \[(.*?)^\]", texto, re.S | re.M)
    assert bloco, "não achei a lista `excludes` no bp.spec"
    return re.findall(r'"([^"]+)"', bloco.group(1))


def test_o_spec_declara_exclusoes():
    """Não-vacuidade: sem lista, o teste abaixo não provaria nada."""
    assert len(_excludes_do_spec()) >= 5


def test_nenhuma_exclusao_e_carregada_pelo_runtime():
    """
    A pergunta que faltava: o bundle sai sem algo que ele precisa?

    Roda num processo separado de propósito. Na sessão do pytest, `unittest` e
    `pytest` já estão em `sys.modules` por causa do próprio pytest — mediria a
    suíte, não o app.
    """
    excludes = _excludes_do_spec()
    programa = (
        "import sys\n"
        f"sys.path.insert(0, {str(RAIZ)!r})\n"
        + "".join(f"import {m}\n" for m in _IMPORTS_DE_RUNTIME)
        + "print('\\n'.join(sorted(sys.modules)))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", programa],
        capture_output=True, text=True, cwd=RAIZ,
    )
    assert proc.returncode == 0, (
        f"o runtime do app nem importa nesta máquina:\n{proc.stderr[-2000:]}"
    )
    carregados = set(proc.stdout.split())
    assert len(carregados) > 100, "medição vazia — o teste seria vacuoso"

    fatais = sorted(nome for nome in excludes if nome in carregados)
    assert not fatais, (
        "bp.spec exclui do bundle módulo(s) que o programa CARREGA em runtime:\n  - "
        + "\n  - ".join(fatais)
        + "\n\nO .exe sairia sem eles e morreria com "
        "\"No module named '<nome>'\" na primeira execução — foi exatamente o "
        "que aconteceu com pandas.plotting.\n"
        "Excluir só vale para o que a biblioteca NÃO puxa sozinha; "
        "nosso código não importar não basta."
    )


@pytest.mark.parametrize("modulo", ["pandas.plotting", "pandas.io.sql"])
def test_os_dois_que_quebraram_o_exe_nao_voltam(modulo):
    """
    Os dois nomes concretos, citados.

    `pandas.plotting` é o que o usuário viu na tela. `pandas.io.sql` era o
    próximo — estava na mesma lista e teria aparecido logo depois.
    """
    assert modulo not in _excludes_do_spec(), (
        f"{modulo} voltou para os excludes do bp.spec. `import pandas` carrega "
        f"esse módulo; excluí-lo quebra o pandas inteiro no .exe."
    )


# ============================================================================
# O autoteste que o build passa a exigir do binário
# ============================================================================


def test_autoteste_roda_o_pipeline_completo():
    """
    O mesmo autoteste que `build.py` roda no `.exe`, aqui sobre a fonte.

    Vale como não-vacuidade do portão: se ele reprovasse na árvore de código,
    reprovaria sempre no binário e o gate viraria ruído. E como ele exercita o
    motor de ponta a ponta — ler, casar, projetar, escrever —, também é o teste
    mais barato de "o programa ainda faz o que promete".
    """
    from src.bp.app.autoteste import executar

    passou, relatorio = executar()
    assert passou, relatorio
    assert "importar o motor" in relatorio and "gerar a entrega" in relatorio


def test_build_exige_o_autoteste_antes_de_entregar():
    """
    O portão existe no build, não só no código.

    Sem esta asserção, alguém remove a chamada de `main()` e o `.exe` volta a
    sair sem prova — que é exatamente o estado em que ele foi distribuído.
    """
    build = (RAIZ / "build.py").read_text(encoding="utf-8")
    assert "def autotestar()" in build, "build.py perdeu o passo de autoteste"
    corpo = re.search(r"def main\(\).*?(?=\n\n|\Z)", build, re.S)
    assert corpo and "autotestar()" in corpo.group(0), (
        "main() do build.py não chama autotestar() — o binário sairia sem "
        "prova de que roda"
    )


# ============================================================================
# O caminho de distribuição: Release, não commit do binário
# ============================================================================

WORKFLOW = RAIZ / ".github" / "workflows" / "release.yml"


def test_o_binario_nao_e_versionado():
    """
    55 MB por build, e o git guarda todos para sempre.

    O `.exe` chegou a ser commitado uma vez. O histórico não encolhe depois —
    a única defesa é não deixar entrar de novo.
    """
    rastreados = subprocess.run(
        ["git", "ls-files", "dist"], capture_output=True, text=True, cwd=RAIZ
    ).stdout.split()
    assert not rastreados, (
        "há arquivo(s) de `dist/` versionado(s): " + ", ".join(rastreados) +
        "\nO binário se distribui por GitHub Release, não pelo repositório."
    )

    ignorado = subprocess.run(
        ["git", "check-ignore", "dist/MAPA.exe"],
        capture_output=True, text=True, cwd=RAIZ,
    )
    assert ignorado.returncode == 0, (
        "`dist/` saiu do .gitignore — o próximo build entra no histórico"
    )


def test_o_workflow_de_release_existe_e_gateia_o_build():
    """
    O release é automático, e a automação tem de manter os portões.

    Publicar sem rodar `build.py` seria publicar sem auditoria e sem autoteste
    — que é o estado em que o binário com o pandas quebrado saiu. O teste não
    valida YAML: afirma as três coisas que, se sumirem, devolvem o problema.
    """
    assert WORKFLOW.exists(), f"workflow de release ausente: {WORKFLOW}"
    texto = WORKFLOW.read_text(encoding="utf-8")

    assert "windows-latest" in texto, (
        "o PyInstaller não faz cross-compile: um .exe Windows só sai de uma "
        "máquina Windows"
    )
    assert "python build.py" in texto, (
        "o workflow não chama build.py — publicaria sem auditoria nem autoteste"
    )
    assert "pytest" in texto, "o workflow não roda a suíte antes de publicar"
    assert 'tags: ["v*"]' in texto, "o gatilho por tag `v*` sumiu"
    assert "contents: write" in texto, (
        "sem essa permissão o job não consegue criar a Release"
    )


def test_o_autoteste_nunca_levanta():
    """
    Um portão que explode não reprova o binário — impede que ele seja avaliado.

    Aconteceu: a limpeza da pasta temporária falhou no Windows (`WinError 32`,
    arquivo em uso) DEPOIS de o pipeline ter passado inteiro. A exceção subiu,
    e o `build.py` recusou um `.exe` correto dizendo "NAO DISTRIBUA".

    Aqui o corpo é substituído por algo que estoura. O contrato é devolver
    ``(False, texto)`` — nunca propagar.
    """
    from src.bp.app import autoteste

    original = autoteste._executar
    try:
        def explodir():
            raise RuntimeError("pane no meio do autoteste")

        autoteste._executar = explodir
        passou, relatorio = autoteste.executar()
    finally:
        autoteste._executar = original

    assert passou is False
    assert "pane no meio do autoteste" in relatorio
    assert "defeito do próprio" in relatorio, (
        "o relatório precisa distinguir 'o teste quebrou' de 'o binário é ruim'"
    )


def test_ler_abas_nao_deixa_o_arquivo_aberto(tmp_path):
    """
    No Windows, handle não fechado é `WinError 32` — o arquivo fica preso.

    `pd.ExcelFile(...)` sem `with` mantinha o balancete do cliente aberto
    depois de processado: quem tentasse mover, renomear ou apagar o arquivo
    era barrado até fechar o programa.

    O teste é o mais direto que existe: processa e depois APAGA. No Windows,
    apagar arquivo aberto falha; no Linux passa sempre, então lá ele vale como
    não-regressão de leitura.
    """
    from openpyxl import Workbook

    from src.bp.parsers.abas import listar_abas
    from src.bp.parsers.dispatcher import ParseyCaller

    caminho = tmp_path / "duas abas.xlsx"
    wb = Workbook()
    for nome in ("Balancete 2024", "Balancete 2025"):
        ws = wb.create_sheet(nome)
        ws.append(["Conta", "Descrição", "Saldo"])
        for codigo, desc, saldo in (
            ("1", "ATIVO", 300.0), ("1.01", "CIRCULANTE", 300.0),
            ("1.01.01", "Caixa", 100.0), ("1.01.02", "Bancos", 200.0),
        ):
            ws.append([codigo, desc, saldo])
    del wb["Sheet"]
    wb.save(caminho)
    wb.close()

    listar_abas(str(caminho))
    ParseyCaller(str(caminho)).parse()

    caminho.unlink()
    assert not caminho.exists(), "o arquivo ficou preso por um handle aberto"
