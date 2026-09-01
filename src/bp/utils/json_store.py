"""
Leitura e escrita de estado em JSON — fonte única.

O padrão ``if path.exists(): open/json.load ... else: default`` estava repetido
em seis pares no ``AccountTrainer`` (arquivos processados, variações, padrões,
estatísticas, ignore list) mais o ``MatchCache``. A duplicação escondia uma
inconsistência real: **só um dos seis tratava ``JSONDecodeError``** — nos
outros cinco, um arquivo de estado truncado (queda de energia no meio de uma
gravação, edição manual errada) derrubava a rodada de treino inteira com
stack trace, em vez de recomeçar do default.

``load_json`` degrada para o default e avisa; ``save_json`` grava de forma
atômica, para que uma interrupção não deixe o arquivo pela metade.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["load_json", "save_json"]


def load_json[T](path: str | Path, default: T) -> T | Any:
    """
    Lê um JSON, devolvendo ``default`` se ele não existir ou estiver corrompido.

    O default é devolvido **como veio** — quem chama controla o tipo. Um
    arquivo ilegível não interrompe a execução: o estado recomeça vazio, que é
    sempre recuperável, enquanto uma exceção no meio do treino não é.
    """
    caminho = Path(path)
    if not caminho.exists():
        return default
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Aviso: {caminho} ilegível ({e}); usando o estado padrão.")
        return default


def save_json(path: str | Path, data: Any) -> None:
    """
    Grava um JSON de forma atômica (escreve ao lado, depois renomeia).

    ``os.replace`` é atômico no mesmo sistema de arquivos, então o arquivo de
    destino ou é a versão antiga íntegra ou a nova íntegra — nunca metade de
    cada. Os arquivos daqui são estado de treino acumulado ao longo de várias
    sessões; perdê-los por uma gravação interrompida custa caro.
    """
    caminho = Path(path)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    fd, temporario = tempfile.mkstemp(
        dir=caminho.parent, prefix=f".{caminho.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temporario, caminho)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise
