# -*- mode: python ; coding: utf-8 -*-
"""
Spec do PyInstaller — MAPA.exe.

Regra de ouro: **lista de convite**, não lista negra. Só entra o que a janela
precisa para rodar; nada de globs largos como `--add-data src/bp;src/bp`. Um
`.exe` do PyInstaller é um zip disfarçado: qualquer pessoa que o receba abre
com `pyinstxtractor` e lê tudo que foi empacotado. Se `src/bp/training/DFS_Exemple/`
entrar aqui por descuido, todo balancete de cliente vai junto.

O teste `tests/test_build_seguranca.py` roda depois do build e falha se
qualquer arquivo dessa allowlist mudar para incluir dado de cliente — ele é
o cinto de segurança dessa regra.
"""

from pathlib import Path

RAIZ = Path(SPECPATH).resolve()

# --- ALLOWLIST DE RECURSOS -------------------------------------------------
# Cada entrada é (origem, destino_no_bundle).
#
# OBRIGATÓRIOS: sem eles a janela abre e falha na primeira execução; o build
# para de propósito — melhor errar aqui do que gerar um .exe quebrado e a
# pessoa descobrir no dia da entrega.
#
# OPCIONAIS: quando existem, entram; quando não, o build segue e avisa.
# `account_variations.json` é o aprendizado do matcher — mora só no repo
# privado (contém strings agregadas de balancetes reais e não pertence ao
# repo público). Compilando no privado o arquivo está lá e vai para o
# .exe; compilando no público o .exe sai sem aprendizado (o matcher opera
# só com fuzzy + sinônimos, aproveitamento fica menor até a próxima rodada
# de treino). Ver PLANO_J_INTERFACE.md §3.4 e PLANO_K_EMPACOTAMENTO.md §4.
_OBRIGATORIOS = [
    ("data/plano_referencial.json",                 "data"),
    ("data/plano_contas.json",                       "data"),
    ("data/accounting_synonyms.json",                "data"),
    ("templates/Template_GT_BP_Padrao_v3.xlsx",      "templates"),
]

_OPCIONAIS = [
    ("src/bp/training/account_variations.json",      "src/bp/training"),
]

datas = []
for origem, destino in _OBRIGATORIOS:
    caminho = RAIZ / origem
    if not caminho.exists():
        raise SystemExit(
            f"[bp.spec] recurso obrigatorio ausente: {origem}\n"
            f"O build parou de proposito. Gere o arquivo antes de compilar."
        )
    datas.append((str(caminho), destino))

for origem, destino in _OPCIONAIS:
    caminho = RAIZ / origem
    if caminho.exists():
        datas.append((str(caminho), destino))
    else:
        print(
            f"[bp.spec] AVISO: {origem} nao existe — o .exe sai sem esse "
            "recurso. Normal se voce esta compilando no repo publico; se "
            "esperava embarcar o aprendizado, compile no clone privado onde "
            "o arquivo mora."
        )

# --- A BIBLIOTECA NATIVA DO ARRASTAR-E-SOLTAR -----------------------------
#
# Este bloco existe porque o .exe da v0.8 saiu SEM arrastar-e-soltar.
#
# `tkinterdnd2` é dois pedaços: os .py (que o PyInstaller acha sozinho, por
# importação) e a extensão Tcl `tkdnd` — uma pasta com .dll e pkgIndex.tcl
# dentro do pacote. A segunda é DADO, não módulo: `hiddenimports` não a traz.
# Sem ela, em runtime:
#
#     TkinterDnD.Tk()
#       -> tkroot.tk.call('package', 'require', 'tkdnd')
#       -> TclError -> RuntimeError('Unable to load tkdnd library.')
#
# e `app/dnd.py` cai para o `tkinter.Tk` puro. A janela abre normalmente, a
# zona de soltar vira botão, e arrastar não traz nada — sem erro na tela,
# porque o build é `console=False`. Era exatamente o sintoma relatado.
#
# Depender do hook do `pyinstaller-hooks-contrib` foi o erro: ele existe, mas
# muda entre versões, e o comentário antigo aqui já admitia a dúvida ("o hook
# oficial cobre, mas..."). Declarar explicitamente custa ~2 MB e tira o
# resultado do jogo de versões.
#
# Entram TODAS as plataformas de propósito. `TkinterDnD._require()` escolhe a
# pasta em runtime por `platform.system()`, `PROCESSOR_ARCHITECTURE` e a
# versão do Tcl (`-tcl9` quando Tcl >= 9). Filtrar aqui pela máquina que
# compila é apostar que ela é igual à de quem recebe — e é a mesma classe de
# aposta que produziu este defeito.
# Localiza o pacote SEM importá-lo: `import tkinterdnd2` executa
# `import tkinter`, que falta em máquina sem Tk (um Linux de CI, por exemplo)
# e derrubaria o spec por um motivo que não tem a ver com o empacotamento.
# `find_spec` só resolve o caminho.
import importlib.util as _ilu

_tkdnd_spec = _ilu.find_spec("tkinterdnd2")
if _tkdnd_spec is None or not _tkdnd_spec.origin:
    raise SystemExit(
        "[bp.spec] tkinterdnd2 nao esta instalado. Ele e dependencia de NUCLEO "
        "(pyproject.toml): sem ele o .exe sai sem arrastar-e-soltar, que foi o "
        "defeito da v0.8. Rode `uv sync` antes de compilar."
    )

_tkdnd_raiz = Path(_tkdnd_spec.origin).resolve().parent / "tkdnd"
if not _tkdnd_raiz.is_dir():
    raise SystemExit(
        f"[bp.spec] {_tkdnd_raiz} nao existe — o pacote tkinterdnd2 esta "
        "incompleto. Reinstale com `uv sync`."
    )

_tkdnd_datas = [
    (str(_arq), str(Path("tkinterdnd2/tkdnd") / _arq.parent.relative_to(_tkdnd_raiz)))
    for _arq in sorted(_tkdnd_raiz.rglob("*"))
    if _arq.is_file()
]
if not _tkdnd_datas:
    raise SystemExit(f"[bp.spec] {_tkdnd_raiz} esta vazia — nada a embarcar.")

print(f"[bp.spec] tkdnd: {len(_tkdnd_datas)} arquivo(s) embarcado(s)")
datas += _tkdnd_datas

# --- MÓDULOS QUE O PYINSTALLER NÃO ACHA POR IMPORTAÇÃO ESTÁTICA -----------
hiddenimports = [
    # Os .py do tkinterdnd2. A extensão Tcl vem pelo bloco acima — este nome
    # sozinho NÃO a traz, e foi a confusão que quebrou o .exe da v0.8.
    "tkinterdnd2",
    "tkinterdnd2.TkinterDnD",
    # openpyxl usa esses subpacotes só dinamicamente.
    "openpyxl.cell._writer",
]

# --- MÓDULOS PESADOS QUE NÃO SÃO USADOS PELO APP --------------------------
# Cada exclusão foi verificada: nenhum import de `src/bp/app`, `src/bp/output`,
# `src/bp/parsers`, `src/bp/matchers` toca esses módulos.
excludes = [
    "tkinter.test",
    "unittest",
    "pytest",
    "pydantic",              # extra `curation`, não usado em runtime
    "cv2", "fitz", "pdf2image", "pytesseract", "PIL.ImageTk",  # extra `ocr`
    "matplotlib", "IPython", "notebook", "ipykernel",
    "pandas.tests", "pandas.plotting", "pandas.io.sql",
    "numpy.tests",
]

# --- ANALISE ---------------------------------------------------------------
a = Analysis(
    [str(RAIZ / "app.py")],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# --- EXECUTAVEL ------------------------------------------------------------
# onefile + windowed: descompacta em %TEMP% do usuario (nao precisa admin) e
# nao abre janela de console em cima da janela do Tk.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="MAPA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
