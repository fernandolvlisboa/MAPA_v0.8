"""
Auditoria do `.exe` gerado — o cinto de seguranca do empacotamento.

O `.exe` do PyInstaller e um zip disfarcado. Uma linha errada no `bp.spec`
(por exemplo trocar a allowlist explicita por um glob `src/bp/*`) traria
`src/bp/training/DFS_Exemple/` inteiro para dentro — todo balancete de
cliente vazado, e ninguem repararia porque o app continuaria funcionando.

Este teste roda depois do build e falha se qualquer arquivo com cara de dado
de cliente estiver dentro do binario. Ele so roda quando o `.exe` existe
(ver ``pytestmark`` abaixo): local sem PyInstaller a suite pula, num CI de
build o teste e obrigatorio.

A extracao usa ``pyinstxtractor-ng`` — a mesma ferramenta que um curioso mal
intencionado usaria. Se o teste passa aqui, passa la fora.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
EXE = RAIZ / "dist" / ("MAPA.exe" if sys.platform == "win32" else "MAPA")

# So faz sentido rodar depois de `python build.py`. Sem o binario, pula
# (nao e um bug — o dev que nao compilou nao precisa deste guard).
pytestmark = pytest.mark.skipif(
    not EXE.exists(),
    reason=f"binario ausente: {EXE.name}. Rode `python build.py` antes.",
)

# --- Regras de allowlist --------------------------------------------------
#
# Nada com cara de balancete de cliente pode estar no bundle. As regras sao
# escritas como *padroes que NAO podem aparecer* em nenhum caminho dentro do
# .exe. Padrao positivo (o que PODE entrar) esta no `bp.spec`; aqui o teste
# afirma o negativo, que e o que evita vazamento.

# Padroes que denunciam dado de cliente no bundle. `_txt` legitima nao entra
# aqui: numpy, pdfminer e cia. embarcam LICENSE.txt, README.txt e afins.
_PADRAO_CLIENTE = [
    re.compile(r"(^|[\\/])DFS_Exemple([\\/]|$)", re.IGNORECASE),
    re.compile(r"(^|[\\/])BP_PDF_ex([\\/]|$)", re.IGNORECASE),
    re.compile(r"balan(c|ç)o|balancete", re.IGNORECASE),
]

# Extensoes so poderiam entrar por dois caminhos: (a) recurso oficial no
# `bp.spec` — permitido, controlado pelo `_PERMITIDOS`; (b) fixture de teste
# ou amostra empacotada por descuido — proibido. Ignoramos ocorrencias
# dentro de pastas de metadata / testes de terceiros que sao ruido comum
# em bundles Python.
_EXT_PERIGO = re.compile(r"\.(xls|xlsx|csv|pdf)$", re.IGNORECASE)
_IGNORAR_EM = re.compile(
    r"(^|[\\/])(dist-info|egg-info|tests?|_pytest|__pycache__)([\\/]|$)",
    re.IGNORECASE,
)

_PERMITIDOS = {
    "template_gt_bp_padrao_v3.xlsx",  # o template da empresa
    "plano_referencial.json",
    "plano_contas.json",
    "accounting_synonyms.json",
    "account_variations.json",
    "elenco-de-contas-contabil.pdf",  # plano da RFB (publico)
}


def _extrair_exe(destino: Path) -> Path:
    """Descompacta o .exe usando pyinstxtractor-ng."""
    pytest.importorskip(
        "pyinstxtractor_ng",
        reason="pyinstxtractor-ng nao instalado (extra `packaging`)",
    )
    # A ferramenta nao aceita -o: extrai na CWD, criando `<nome>_extracted`.
    subprocess.run(
        [sys.executable, "-m", "pyinstxtractor_ng", str(EXE)],
        check=True,
        cwd=destino,
    )
    candidatos = list(destino.glob("*_extracted"))
    assert candidatos, (
        "pyinstxtractor-ng nao criou a pasta de extracao — o .exe pode nao "
        "ser um bundle PyInstaller ou pode estar corrompido."
    )
    return candidatos[0]


def _e_permitido(nome: str) -> bool:
    return nome.lower() in _PERMITIDOS


def test_exe_nao_carrega_dado_de_cliente(tmp_path: Path) -> None:
    """
    Varre o conteudo do .exe e falha se qualquer arquivo bater num padrao
    de dado de cliente. E o teste que sustenta a regra do PLANO_K.
    """
    raiz_extraida = _extrair_exe(tmp_path)

    vazamentos: list[str] = []
    for arquivo in raiz_extraida.rglob("*"):
        if not arquivo.is_file():
            continue
        nome = arquivo.name
        if _e_permitido(nome):
            continue
        rel = str(arquivo.relative_to(raiz_extraida))
        # (a) qualquer coisa com cara de balancete de cliente, em qualquer lugar
        if any(p.search(rel) for p in _PADRAO_CLIENTE):
            vazamentos.append(rel)
            continue
        # (b) extensoes perigosas fora de pastas de biblioteca-terceiro
        if _EXT_PERIGO.search(rel) and not _IGNORAR_EM.search(rel):
            vazamentos.append(rel)

    assert not vazamentos, (
        "O .exe carregou arquivos com cara de dado de cliente:\n  - "
        + "\n  - ".join(sorted(vazamentos))
        + "\n\nRevise `bp.spec`: alguma entrada em `datas` esta puxando material "
        "que deveria ficar fora. NUNCA distribua esse .exe."
    )


def test_recursos_esperados_estao_presentes(tmp_path: Path) -> None:
    """
    Espelho do teste anterior: o .exe PRECISA carregar o template GT e o
    plano referencial — sem eles a janela abre e falha na primeira execucao.
    """
    raiz_extraida = _extrair_exe(tmp_path)
    nomes = {p.name.lower() for p in raiz_extraida.rglob("*") if p.is_file()}
    obrigatorios = {"plano_referencial.json", "template_gt_bp_padrao_v3.xlsx"}
    faltando = obrigatorios - nomes
    assert not faltando, (
        f"Recursos obrigatorios ausentes do .exe: {sorted(faltando)}. "
        "O `bp.spec` esta desalinhado com a lista de recursos do PLANO_K."
    )


def test_exe_carrega_a_biblioteca_do_arrastar_e_soltar(tmp_path: Path) -> None:
    """
    O tkdnd tem de estar DENTRO do .exe — foi o defeito da v0.8.

    `tkinterdnd2` sao dois pedacos: os .py, que o PyInstaller acha por
    importacao, e a extensao Tcl `tkdnd` (uma pasta com .dll e pkgIndex.tcl),
    que e DADO e so entra se o spec mandar. O bp.spec antigo declarava so
    `hiddenimports = ["tkinterdnd2"]` e confiava no hook do
    pyinstaller-hooks-contrib.

    No .exe distribuido, o resultado foi:

        TkinterDnD.Tk() -> package require tkdnd -> TclError
                        -> RuntimeError('Unable to load tkdnd library.')

    `app/dnd.py` engolia a excecao, caia para o `tkinter.Tk` puro, e a janela
    abria com a zona de soltar virada em botao. Arrastar nao trazia nada, sem
    nenhuma mensagem — o build e `console=False`.

    Nenhum teste de comportamento pega isso: na maquina que compila, o pacote
    esta instalado e tudo funciona. So o conteudo do binario responde.
    """
    raiz_extraida = _extrair_exe(tmp_path)

    arquivos = [p for p in raiz_extraida.rglob("*") if p.is_file()]
    dentro_de_tkdnd = [
        p for p in arquivos
        if re.search(r"(^|[\\/])tkdnd([\\/]|$)", str(p.relative_to(raiz_extraida)))
    ]
    assert dentro_de_tkdnd, (
        "O .exe NAO carrega a pasta `tkdnd` do tkinterdnd2 — arrastar-e-soltar "
        "vai estar morto para quem receber este binario, e a janela nao vai "
        "dizer por que.\n"
        "Conserto: o bloco `_tkdnd_datas` do bp.spec. `hiddenimports` sozinho "
        "nao traz a extensao Tcl."
    )

    # Nao basta a pasta existir: precisa do indice que o `package require` le
    # e da biblioteca nativa da plataforma.
    nomes = {p.name.lower() for p in dentro_de_tkdnd}
    assert "pkgindex.tcl" in nomes, (
        "a pasta tkdnd foi embarcada sem `pkgIndex.tcl` — sem ele o Tcl nao "
        f"encontra o pacote. Presentes: {sorted(nomes)[:12]}"
    )
    nativas = [n for n in nomes if n.endswith((".dll", ".so", ".dylib"))]
    assert nativas, (
        "a pasta tkdnd foi embarcada so com os .tcl, sem a biblioteca nativa "
        f"(.dll/.so/.dylib). Presentes: {sorted(nomes)[:12]}"
    )

    # E a plataforma DESTE binario tem de estar entre as embarcadas.
    esperada = {"win32": "win-", "darwin": "osx-"}.get(sys.platform, "linux-")
    plataformas = {
        p.parent.name for p in dentro_de_tkdnd if p.name.lower() == "pkgindex.tcl"
    }
    assert any(nome.startswith(esperada) for nome in plataformas), (
        f"nenhuma variante `{esperada}*` do tkdnd no bundle — o .exe foi "
        f"compilado para {sys.platform} e nao leva a biblioteca dessa "
        f"plataforma. Embarcadas: {sorted(plataformas)}"
    )
