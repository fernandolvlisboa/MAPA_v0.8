"""
conftest.py — Configuração global para pytest.

Além de colocar a raiz do projeto no ``sys.path``, este módulo resolve dois
problemas que faziam a suíte reportar "verde" sem validar nada:

1. **Fixtures de corpus ausentes.** Testes referenciavam arquivos que não
   existem no workspace. Como o pipeline engole erro de leitura
   (``ParseyCaller.read()`` → ``except Exception: return None``), o export
   produzia uma planilha vazia e as asserções passavam sobre zero linhas.
   ``require_corpus_file`` distingue os dois casos: *corpus inteiro ausente*
   (clone sem os dados de exemplo → skip legítimo) de *arquivo específico
   ausente dentro de um corpus presente* (→ falha dura, é bug de caminho).

2. **Vazamento de estado versionado.** ``ContaMatcher`` grava em
   ``data/match_cache.json`` quando nenhum ``cache_path`` é passado, e o
   trainer grava em ``src/bp/training/*.json``. Rodar a suíte sujava o
   working tree e tornava o resultado dependente da ordem dos testes. O
   fixture autouse ``_preserva_estado_versionado`` restaura esses arquivos ao
   fim da sessão.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Adiciona raiz do projeto ao path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Diretórios de corpus usados pelos testes de integração.
CORPUS_DIR = PROJECT_ROOT / "data" / "samples"
PDF_CORPUS_DIR = PROJECT_ROOT / "auxil" / "BP_PDF_ex"

# Arquivos de estado versionados que o código de produção escreve por default.
# Preservados entre sessões para a suíte ser idempotente.
_ESTADO_VERSIONADO = (
    PROJECT_ROOT / "data" / "match_cache.json",
    PROJECT_ROOT / "src" / "bp" / "training" / "account_variations.json",
    PROJECT_ROOT / "src" / "bp" / "training" / "training_cache.json",
    PROJECT_ROOT / "src" / "bp" / "training" / "training_stats.json",
    PROJECT_ROOT / "src" / "bp" / "training" / "training_ignore.json",
    PROJECT_ROOT / "src" / "bp" / "training" / "learned_patterns.json",
    PROJECT_ROOT / "src" / "bp" / "training" / "processed_files.json",
)


def require_corpus_file(relativo: str, *, base: Path = CORPUS_DIR) -> Path:
    """
    Resolve um arquivo do corpus, separando "ausente por design" de "bug".

    - ``base`` inexistente → ``pytest.skip``: o clone não trouxe os dados de
      exemplo, não há o que testar.
    - ``base`` existe mas o arquivo não → ``pytest.fail``: o caminho no teste
      está errado (foi exatamente esse caso que deixou 5 testes do exporter
      passando sobre uma planilha vazia e 6 do parser de DF pulando à toa).
    """
    if not base.exists():
        pytest.skip(f"Corpus ausente neste workspace: {base}")
    caminho = base / relativo
    if not caminho.exists():
        disponiveis = sorted(p.name for p in base.iterdir())[:10]
        pytest.fail(
            f"Fixture de corpus não encontrada: {caminho}\n"
            f"O corpus existe, então isso é caminho errado no teste — não um "
            f"workspace incompleto. Disponíveis (10 primeiros): {disponiveis}"
        )
    return caminho


@pytest.fixture(scope="session")
def balancete_xls() -> Path:
    """Balancete .xls real e estável (566 contas). Base dos testes de export."""
    return require_corpus_file("Balancete SPEZZIA TUBOS 01012024-31122024.xls")


@pytest.fixture(scope="session")
def balancete_xlsx() -> Path:
    """Balancete .xlsx real (126 contas)."""
    return require_corpus_file("Balancete Real Life.xlsx")


@pytest.fixture(scope="session")
def balancete_txt() -> Path:
    """Balancete .TXT de largura fixa (468 contas via TXTParser direto)."""
    return require_corpus_file("2019-01.TXT")


@pytest.fixture(scope="session")
def balancete_csv() -> Path:
    """Balancete .csv real (separador ';', com preâmbulo de cabeçalho)."""
    return require_corpus_file("1544 - BALANCETE 1222024.csv")


@pytest.fixture(autouse=True, scope="session")
def _preserva_estado_versionado():
    """
    Restaura os JSON de estado versionados ao fim da sessão.

    Sem isto, `pytest` deixa ``data/match_cache.json`` sujo (o default de
    ``ContaMatcher`` aponta para ele) e o resultado de um teste passa a
    depender de execuções anteriores.
    """
    backup_dir = Path(tempfile.mkdtemp(prefix="bp-estado-"))
    originais: dict[Path, Path | None] = {}
    for alvo in _ESTADO_VERSIONADO:
        if alvo.exists():
            copia = backup_dir / alvo.name
            shutil.copy2(alvo, copia)
            originais[alvo] = copia
        else:
            originais[alvo] = None

    yield

    for alvo, copia in originais.items():
        if copia is not None:
            shutil.copy2(copia, alvo)
        elif alvo.exists():
            # Foi criado pela suíte e não existia antes: remove.
            alvo.unlink()
    shutil.rmtree(backup_dir, ignore_errors=True)
