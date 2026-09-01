"""
Padrões e Keywords para Detecção de Demonstrações Financeiras.

Carrega padrões de data/patterns.json e fornece funções auxiliares.

NOTA: Os padrões são configuráveis via JSON para facilitar expansão
conforme processamos mais PDFs e aprendemos novos padrões.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ============================================================================
# CARREGAMENTO DE PADRÕES
# ============================================================================


def _get_patterns_file() -> Path:
    """Retorna o caminho do arquivo patterns.json."""
    # Assume que este arquivo está em src/bp/parsers/pdf_utils/
    # e patterns.json está em data/
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent.parent
    patterns_file = project_root / "data" / "patterns.json"
    return patterns_file


def load_patterns() -> dict:
    """
    Carrega padrões do arquivo JSON.

    Returns:
        Dict com todos os padrões configurados
    """
    patterns_file = _get_patterns_file()

    if not patterns_file.exists():
        raise FileNotFoundError(
            f"Arquivo de padrões não encontrado: {patterns_file}\n"
            "Crie o arquivo data/patterns.json com os padrões."
        )

    with open(patterns_file, encoding="utf-8") as f:
        return json.load(f)


def save_patterns(patterns: dict) -> None:
    """
    Salva padrões no arquivo JSON.

    Args:
        patterns: Dict com padrões a salvar
    """
    patterns_file = _get_patterns_file()
    patterns_file.parent.mkdir(parents=True, exist_ok=True)

    with open(patterns_file, "w", encoding="utf-8") as f:
        json.dump(patterns, f, indent=2, ensure_ascii=False)


def add_keyword(category: str, keyword: str, is_strong: bool = False) -> None:
    """
    Adiciona uma keyword aos padrões e salva.

    Args:
        category: Categoria ("balance_sheet", "income_statement", etc.)
        keyword: Keyword a adicionar
        is_strong: Se é keyword forte (maior peso)
    """
    patterns = load_patterns()

    if category not in patterns:
        patterns[category] = {"keywords": [], "strong_keywords": []}

    target_list = "strong_keywords" if is_strong else "keywords"

    if target_list not in patterns[category]:
        patterns[category][target_list] = []

    if keyword not in patterns[category][target_list]:
        patterns[category][target_list].append(keyword)
        save_patterns(patterns)


# ============================================================================
# PADRÕES GLOBAIS (carregados do JSON)
# ============================================================================

try:
    _PATTERNS = load_patterns()
except FileNotFoundError:
    # Se arquivo não existe, usa padrões mínimos
    _PATTERNS = {
        "balance_sheet": {"keywords": [], "strong_keywords": []},
        "income_statement": {"keywords": [], "strong_keywords": []},
        "notes": {"keywords": []},
        "noise": {"keywords": [], "patterns": []},
        "header_footer": {"patterns": []},
        "columns": {},
        "currency": {"patterns": []},
        "metadata": {},
        "settings": {"min_confidence": 0.3},
    }


# ============================================================================
# LISTAS DE KEYWORDS (extraídas do JSON)
# ============================================================================

BP_KEYWORDS = _PATTERNS.get("balance_sheet", {}).get("keywords", [])
BP_KEYWORDS_STRONG = _PATTERNS.get("balance_sheet", {}).get("strong_keywords", [])
DRE_KEYWORDS = _PATTERNS.get("income_statement", {}).get("keywords", [])
DRE_KEYWORDS_STRONG = _PATTERNS.get("income_statement", {}).get("strong_keywords", [])
NOTES_KEYWORDS = _PATTERNS.get("notes", {}).get("keywords", [])
NOISE_KEYWORDS = _PATTERNS.get("noise", {}).get("keywords", [])

# Padrões regex
NOISE_PATTERNS_LIST = _PATTERNS.get("noise", {}).get("patterns", [])
HEADER_FOOTER_PATTERNS = _PATTERNS.get("header_footer", {}).get("patterns", [])
CURRENCY_PATTERNS = _PATTERNS.get("currency", {}).get("patterns", [])

# Padrões de colunas
COLUMN_PATTERNS = _PATTERNS.get("columns", {})
SETTINGS = _PATTERNS.get("settings", {})


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================


def compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    """
    Compila lista de padrões regex.

    Args:
        patterns: Lista de strings regex

    Returns:
        Lista de padrões compilados
    """
    return [re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns]


def match_any_pattern(text: str, patterns: list[str | re.Pattern]) -> bool:
    """
    Verifica se o texto corresponde a algum padrão.

    Args:
        text: Texto para buscar
        patterns: Lista de padrões (strings ou compilados)

    Returns:
        True se encontrar alguma correspondência
    """
    for pattern in patterns:
        if isinstance(pattern, str):
            pattern = re.compile(pattern, re.IGNORECASE | re.UNICODE)
        if pattern.search(text):
            return True
    return False


def count_pattern_matches(text: str, patterns: list[str | re.Pattern]) -> int:
    """
    Conta quantos padrões correspondem ao texto.

    Args:
        text: Texto para buscar
        patterns: Lista de padrões

    Returns:
        Número de correspondências
    """
    count = 0
    for pattern in patterns:
        if isinstance(pattern, str):
            pattern = re.compile(pattern, re.IGNORECASE | re.UNICODE)
        if pattern.search(text):
            count += 1
    return count


def extract_currency_info(text: str) -> dict[str, str]:
    """
    Extrai informações de moeda do texto.

    Args:
        text: Texto para analisar

    Returns:
        Dict com currency, scale, etc.
    """
    info = {
        "currency": None,
        "scale": None,
        "unit": None,
    }

    # Detecta moeda
    if re.search(r"\br\$|reais?\b", text, re.IGNORECASE):
        info["currency"] = "BRL"
    elif re.search(r"\busd|\$|d[óo]lar", text, re.IGNORECASE):
        info["currency"] = "USD"
    elif re.search(r"\beur|euro", text, re.IGNORECASE):
        info["currency"] = "EUR"

    # Detecta escala usando configuração do JSON
    currency_config = _PATTERNS.get("currency", {})
    scales = currency_config.get("scales", {})

    for scale_name, scale_info in scales.items():
        keywords = scale_info.get("keywords", [])
        for keyword in keywords:
            if re.search(rf"\b{keyword}", text, re.IGNORECASE):
                info["scale"] = scale_name
                info["unit"] = scale_info.get("multiplier")
                break
        if info["scale"]:
            break

    return info


# ============================================================================
# PADRÕES PRÉ-COMPILADOS (para performance)
# ============================================================================

BP_PATTERNS = compile_patterns(BP_KEYWORDS)
BP_STRONG_PATTERNS = compile_patterns(BP_KEYWORDS_STRONG)
DRE_PATTERNS = compile_patterns(DRE_KEYWORDS)
DRE_STRONG_PATTERNS = compile_patterns(DRE_KEYWORDS_STRONG)
NOTES_PATTERNS = compile_patterns(NOTES_KEYWORDS)
NOISE_PATTERNS = compile_patterns(NOISE_KEYWORDS + NOISE_PATTERNS_LIST)
HEADER_FOOTER_COMPILED = compile_patterns(HEADER_FOOTER_PATTERNS)
