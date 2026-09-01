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
