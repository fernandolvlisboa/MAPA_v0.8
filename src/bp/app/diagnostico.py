"""
O relatório que se pede a quem diz "não funciona".

Existe porque o `.exe` é `console=False`: quando algo falha nele, não há
terminal, não há log, não há traceback. Foi assim que o executável da v0.8
circulou sem arrastar-e-soltar — a janela abria, arrastar não trazia nada, e
não havia uma única linha de texto para explicar o motivo.

Este módulo produz um texto curto que responde, em ordem, as perguntas que
importam para o arrastar-e-soltar:

1. isto é o `.exe` ou a fonte? (``sys.frozen`` / ``_MEIPASS``)
2. o `tkinterdnd2` importa?
3. a extensão Tcl ``tkdnd`` foi empacotada, e onde?
4. qual pasta de plataforma o ``TkinterDnD._require()`` vai escolher aqui, e
   ela existe com ``pkgIndex.tcl`` e a biblioteca nativa?
5. criando a janela de verdade: funciona? se não, qual foi o erro exato?

Uso::

    MAPA.exe --diagnostico          # escreve MAPA_diagnostico.txt ao lado
    uv run python app.py --diagnostico
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

#: Nome do arquivo gerado ao lado do executável.
ARQUIVO = "MAPA_diagnostico.txt"


def _linha(rotulo: str, valor: object) -> str:
    return f"{rotulo:<34} {valor}"


def _onde_escrever() -> Path:
    """
    Ao lado do executável quando empacotado; no diretório atual quando fonte.

    ``sys.executable`` no bundle onefile é o próprio `.exe` — não o Python
    temporário do ``_MEIPASS`` —, então a pasta dele é onde a pessoa vai
    procurar o arquivo.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / ARQUIVO
    return Path.cwd() / ARQUIVO


def _elevado() -> str:
    """
    O processo está rodando como administrador? (Windows)

    Importa para o arrastar-e-soltar por um motivo que não é óbvio: o Windows
    bloqueia arrastar do Explorer (que roda como usuário comum) para uma janela
    de processo ELEVADO. É a UIPI — isolamento de privilégio de interface — e
    ela falha do mesmo jeito calado: o cursor recusa, nada acontece, nenhum
    erro. Se alguém abre o MAPA com "Executar como administrador", arrastar
    para de funcionar mesmo com o tkdnd perfeitamente empacotado.
    """
    if platform.system() != "Windows":
        return "(só se aplica a Windows)"
    try:
        import ctypes

        elevado = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as exc:
        return f"(não consegui verificar: {exc})"
    if elevado:
        return (
            "SIM — e isto SOZINHO mata o arrastar-e-soltar: o Windows nao "
            "deixa o Explorer soltar arquivo numa janela elevada (UIPI). "
            "Feche e abra o MAPA com duplo clique normal, sem 'executar como "
            "administrador'."
        )
    return "não (correto — arrastar do Explorer funciona)"


def _secao_ambiente() -> list[str]:
    congelado = getattr(sys, "frozen", False)
    meipass = getattr(sys, "_MEIPASS", "")
    return [
        "== AMBIENTE ==",
        _linha("executável", sys.executable),
        _linha("empacotado (frozen)", bool(congelado)),
        _linha("_MEIPASS", meipass or "(não aplicável — rodando da fonte)"),
        _linha("python", sys.version.split()[0]),
        _linha("sistema", f"{platform.system()} {platform.release()}"),
        _linha("platform.machine()", platform.machine()),
        _linha(
            "PROCESSOR_ARCHITECTURE",
            os.environ.get("PROCESSOR_ARCHITECTURE", "(não definida)"),
        ),
        _linha("BP_SEM_DND", os.environ.get("BP_SEM_DND", "(não definida)")),
        _linha("rodando como administrador", _elevado()),
    ]


def _plataforma_do_tkdnd() -> str:
    """
    A mesma escolha que ``TkinterDnD._require()`` faz — reproduzida aqui.

    Repetir a regra é de propósito: o relatório precisa dizer qual pasta ele
    ESPERA, mesmo quando o import do tkinterdnd2 falha antes de chegar lá.
    """
    sistema = platform.system()
    if sistema == "Windows":
        maquina = os.environ.get("PROCESSOR_ARCHITECTURE", platform.machine())
    else:
        maquina = platform.machine()
    tabela = {
        ("Darwin", "arm64"): "osx-arm64",
        ("Darwin", "x86_64"): "osx-x64",
        ("Linux", "aarch64"): "linux-arm64",
        ("Linux", "x86_64"): "linux-x64",
        ("Windows", "ARM64"): "win-arm64",
        ("Windows", "AMD64"): "win-x64",
        ("Windows", "x86"): "win-x86",
    }
    return tabela.get((sistema, maquina), f"(não mapeada: {sistema}/{maquina})")


def _secao_tkdnd() -> list[str]:
    import importlib.util

    saida = ["", "== A EXTENSÃO tkdnd (arrastar-e-soltar) =="]
    esperada = _plataforma_do_tkdnd()
    saida.append(_linha("pasta esperada nesta máquina", esperada))

    spec = importlib.util.find_spec("tkinterdnd2")
    if spec is None or not spec.origin:
        saida.append(_linha("tkinterdnd2", "NÃO ENCONTRADO — este é o defeito"))
        return saida

    pacote = Path(spec.origin).resolve().parent
    saida.append(_linha("tkinterdnd2 em", pacote))

    raiz = pacote / "tkdnd"
    saida.append(_linha("pasta tkdnd/", f"{raiz}  ->  existe={raiz.is_dir()}"))
    if not raiz.is_dir():
        saida.append(
            "  >>> A pasta tkdnd NÃO foi empacotada. Sem ela, "
            "TkinterDnD.Tk() levanta 'Unable to load tkdnd library.' e o "
            "arrastar-e-soltar fica morto. Conserto: bloco _tkdnd_datas do bp.spec."
        )
        return saida

    variantes = sorted(p.name for p in raiz.iterdir() if p.is_dir())
    saida.append(_linha("variantes embarcadas", ", ".join(variantes) or "(nenhuma)"))

    for nome in (esperada, f"{esperada}-tcl9"):
        pasta = raiz / nome
        if not pasta.is_dir():
            saida.append(_linha(f"  {nome}", "AUSENTE"))
            continue
        arquivos = sorted(p.name for p in pasta.iterdir() if p.is_file())
        nativas = [a for a in arquivos if a.endswith((".dll", ".so", ".dylib"))]
        saida.append(
            _linha(
                f"  {nome}",
                f"{len(arquivos)} arquivo(s) | pkgIndex.tcl="
                f"{'pkgIndex.tcl' in arquivos} | nativa={nativas or 'NENHUMA'}",
            )
        )
    return saida


def _secao_tentativa() -> list[str]:
    """A prova real: cria a janela e diz o que aconteceu."""
    saida = ["", "== TENTATIVA REAL =="]
    try:
        import tkinter as tk
    except Exception as exc:  # pragma: no cover - só em máquina sem Tk
        saida.append(_linha("tkinter", f"FALHOU: {type(exc).__name__}: {exc}"))
        return saida

    try:
        raiz = tk.Tk()
        raiz.withdraw()
        saida.append(_linha("Tcl/Tk", raiz.tk.call("info", "patchlevel")))
        raiz.destroy()
    except Exception as exc:
        saida.append(_linha("tkinter.Tk()", f"FALHOU: {type(exc).__name__}: {exc}"))
        return saida

    try:
        from tkinterdnd2 import TkinterDnD

        janela = TkinterDnD.Tk()
        janela.withdraw()
        saida.append(_linha("TkinterDnD.Tk()", "OK"))
        saida.append(_linha("versão do tkdnd", TkinterDnD.TkdndVersion))
        janela.destroy()
    except Exception as exc:
        saida.append(
            _linha("TkinterDnD.Tk()", f"FALHOU: {type(exc).__name__}: {exc}")
        )

    from . import dnd

    raiz2, backend = dnd.criar_root()
    try:
        saida.append(_linha("dnd.criar_root() backend", backend or "(nenhum)"))
        # Carregar a biblioteca e REGISTRAR o alvo são passos distintos. O
        # segundo é o que faz a janela realmente aceitar arquivo, e ele pode
        # falhar sozinho — foi o ponto cego da primeira versão deste relatório.
        recebidos: list = []
        zona = tk.Canvas(raiz2, width=10, height=10)
        registrou_zona = dnd.registrar_alvo(zona, backend, recebidos.append)
        registrou_raiz = dnd.registrar_alvo(raiz2, backend, recebidos.append)
        saida.append(_linha("registrar_alvo(Canvas)", "OK" if registrou_zona else "FALHOU"))
        saida.append(_linha("registrar_alvo(janela)", "OK" if registrou_raiz else "FALHOU"))
        saida.append(_linha("dnd.diagnostico()", dnd.diagnostico() or "(sem queixa)"))
    finally:
        raiz2.destroy()
    return saida


def _secao_bundle() -> list[str]:
    """O que o PyInstaller descompactou — só quando empacotado."""
    meipass = getattr(sys, "_MEIPASS", "")
    if not meipass:
        return []
    raiz = Path(meipass)
    entradas = sorted(p.name for p in raiz.iterdir())
    return [
        "",
        "== CONTEÚDO DO BUNDLE (primeiro nível) ==",
        _linha("_MEIPASS", raiz),
        "  " + ", ".join(entradas[:60]),
        _linha("total de entradas", len(entradas)),
    ]


def relatorio() -> str:
    partes: list[str] = ["RELATÓRIO DE DIAGNÓSTICO — MAPA", ""]
    partes += _secao_ambiente()
    partes += _secao_tkdnd()
    partes += _secao_tentativa()
    partes += _secao_bundle()
    partes += [
        "",
        # Sem citar as palavras que o teste anti-vazamento procura: o rodapé
        # do relatório não pode ser o único motivo de ele "conter" o termo.
        "Mande este arquivo inteiro para quem for analisar. Só há aqui "
        "caminhos de instalação e versões — nenhum dado de cliente.",
    ]
    return "\n".join(partes) + "\n"


def escrever() -> Path:
    """Gera o relatório, grava ao lado do executável e devolve o caminho."""
    destino = _onde_escrever()
    destino.write_text(relatorio(), encoding="utf-8")
    return destino
