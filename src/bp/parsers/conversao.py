"""
Conversão de planilha legada para ``.xlsx`` via LibreOffice headless.

Existe como módulo próprio porque dois consumidores precisam do mesmo passo
por motivos diferentes:

- :class:`~bp.parsers.xls_parser.XlsParser` converte para **interpretar** o
  arquivo (detecta cabeçalho, compacta células mescladas);
- :mod:`bp.output.origem` converte para **transcrever** o arquivo como ele é,
  sem interpretar nada.

Antes disso, a busca pelo ``soffice`` e a chamada do subprocesso viviam
dentro do parser. Copiá-las para o outro lado criaria duas verdades sobre
"onde está o LibreOffice" — exatamente o tipo de duplicação que esta revisão
vem eliminando (ver ``REVISAO_QUALIDADE.md`` §8).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

#: Onde procurar o executável. O caminho do Windows precisa ser testado com
#: ``Path.exists`` porque ``shutil.which`` não resolve caminho absoluto com
#: espaço no Windows de forma confiável.
_CANDIDATOS_SOFFICE = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "soffice",
    "libreoffice",
)

TIMEOUT_S = 30


def localizar_soffice() -> str | None:
    """Devolve o executável do LibreOffice, ou ``None`` se não houver."""
    for candidato in _CANDIDATOS_SOFFICE:
        if "\\" in candidato:
            if Path(candidato).exists():
                return candidato
        elif shutil.which(candidato):
            return candidato
    return None


@contextmanager
def convertido_para_xlsx(origem: str | Path) -> Iterator[Path | None]:
    """
    Converte ``origem`` para ``.xlsx`` num diretório temporário.

    Rende o caminho do arquivo convertido, ou ``None`` quando o LibreOffice
    não está disponível ou a conversão falha. O diretório temporário é
    removido na saída do contexto — quem usa precisa ler o arquivo dentro do
    ``with``.
    """
    origem = Path(origem)
    exe = localizar_soffice()
    if exe is None:
        yield None
        return

    temp_dir = tempfile.mkdtemp(prefix="bp-conv-")
    try:
        cmd = [
            exe,
            "--headless",
            "--convert-to",
            "xlsx",
            "--outdir",
            temp_dir,
            str(origem.absolute()),
        ]
        kwargs: dict = {"capture_output": True, "text": True, "timeout": TIMEOUT_S}
        if os.name == "nt":  # pragma: no cover - específico de Windows
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.run(cmd, **kwargs)

        esperado = Path(temp_dir) / (origem.stem + ".xlsx")
        if not esperado.exists():
            encontrados = list(Path(temp_dir).glob("*.xlsx"))
            if not encontrados:
                yield None
                return
            esperado = encontrados[0]
        yield esperado
    except (subprocess.TimeoutExpired, OSError):
        yield None
    finally:
        with contextlib.suppress(Exception):
            shutil.rmtree(temp_dir, ignore_errors=True)
