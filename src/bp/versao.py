"""
A versão do MAPA e a impressão digital do que ele está usando.

Por que este módulo existe
--------------------------

"Em 31/08 às 09:57 o arquivo saiu certo. Agora está errado." Com o mesmo
balancete de entrada — mesmo SHA-256 — duas execuções deram 100% e 38% de
aproveitamento. Sem carimbo de versão não havia como responder à única
pergunta que importa: *o que mudou entre as duas?*

Não basta o número da versão. Duas máquinas na mesma versão do código dão
resultados diferentes se os **dados** diferirem — e o resultado depende de
três arquivos que evoluem sozinhos:

- ``data/plano_referencial.json`` — o alvo. Regenerar sem o arquivo de
  enriquecimento derruba 117 contas e o matching cai junto;
- ``src/bp/training/account_variations.json`` — o vocabulário aprendido. É o
  que faz "Servicos a receber" achar destino;
- ``data/template_projection.json`` — para onde vai cada código. Uma conta que
  casa mas não projeta some da entrega em silêncio.

Por isso a impressão digital carimba os três, não só a versão. Ela vai no
Sumário de toda entrega e na tela do programa: comparando dois arquivos de
saída, dá para ver em segundos se a diferença é de código ou de dado.

Como versionar
--------------

``VERSAO`` é a fonte única. A tag do git (``v0.8.2``) e o que aparece na
janela saem daqui — mudar em um lugar só. Suba o número ao publicar:
``0.8.2`` -> ``0.8.3`` para correção, ``0.9.0`` quando o comportamento muda.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

#: A versão publicada. Bata com a tag do git: `VERSAO = "0.8.2"` <-> `v0.8.2`.
VERSAO = "0.8.2"

#: Nome do produto como aparece para o usuário final.
PRODUTO = "MAPA"


def _raiz() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _resolver(relativo: str) -> Path:
    """
    Onde o arquivo está — na árvore de código ou dentro do ``.exe``.

    O PyInstaller descompacta os dados embarcados em ``sys._MEIPASS``; fora
    dele vale a raiz do repositório. Tentar os dois evita que a impressão
    digital fique vazia justamente no binário distribuído, que é onde ela mais
    importa.
    """
    import sys

    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidato = Path(base) / relativo
        if candidato.exists():
            return candidato
    return _raiz() / relativo


def _resumo_json(relativo: str, chave_contagem: str | None = None) -> str:
    """
    ``<n> itens / <hash>`` — quantos e qual conteúdo exato.

    A contagem responde "está completo?"; o hash responde "é o mesmo?". Só a
    contagem não basta: dois planos com 1.226 contas podem diferir, e foi
    exatamente uma troca silenciosa de conteúdo que motivou este módulo.
    """
    caminho = _resolver(relativo)
    if not caminho.exists():
        return "AUSENTE"
    try:
        bruto = caminho.read_bytes()
        digest = hashlib.sha256(bruto).hexdigest()[:8]
        dados = json.loads(bruto)
        if chave_contagem:
            dados = dados.get(chave_contagem, dados)
        return f"{len(dados)} / {digest}"
    except (OSError, ValueError):
        return "ILEGIVEL"


def impressao_digital() -> dict[str, str]:
    """
    O que esta execução está usando, em pares rótulo -> valor.

    Vai para o Sumário da entrega e para a janela. Comparar duas entregas é
    comparar estas linhas.
    """
    return {
        "Versão": VERSAO,
        "Plano referencial": _resumo_json(
            "data/plano_referencial.json", "contas_index"
        ),
        "Vocabulário aprendido": _resumo_json(
            "src/bp/training/account_variations.json"
        ),
        "Mapa do template": _resumo_json("data/template_projection.json", "mapa"),
    }


def linha_de_versao() -> str:
    """Uma linha curta para barra de título e rodapé: ``MAPA 0.8.2``."""
    return f"{PRODUTO} {VERSAO}"


def relatorio() -> str:
    """A impressão digital em texto, para o terminal e para o log."""
    return "\n".join(f"  {k:22} {v}" for k, v in impressao_digital().items())


def como_linhas() -> list[tuple[str, Any]]:
    """A impressão digital como linhas de planilha, para o Sumário."""
    return list(impressao_digital().items())


if __name__ == "__main__":
    print(linha_de_versao())
    print(relatorio())
