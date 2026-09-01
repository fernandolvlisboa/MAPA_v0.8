"""
Camada de sinônimos/abreviações contábeis (PT-BR).

Aproxima descrições de balancete do vocabulário do Plano Referencial ANTES do
fuzzy matching. Ataca a fraqueza medida do ``token_set_ratio`` puro: descrições
corretas com ZERO tokens em comum com o alvo (ex.: "BENS NUMERÁRIOS" vs
"CAIXA E EQUIVALENTES DE CAIXA").

Regra de ouro: a expansão é aplicada APENAS ao lado da CONSULTA (descrição de
origem). O plano-alvo permanece canônico e intocado.

Ordem de aplicação:
1. ``phrase``  — substituição de frase inteira (mais específica) por substring.
2. ``token``   — substituição palavra-a-palavra (abreviações de termo).
3. ``abbrev``  — abreviações simbólicas ("c/" -> "com", "s/" -> "sobre").

Também expõe ``is_garbage_description()`` para descartar linhas-lixo
(descrições numéricas/vazias — totais e colunas desalinhadas) antes do matching.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .normalizer import normalize

_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "accounting_synonyms.json"

# Regex compiladas 1x — expand_synonyms roda milhares de vezes por treino.
_CS_RE = re.compile(r"(?<![a-z0-9])c/")
_SS_RE = re.compile(r"(?<![a-z0-9])s/")
_PS_RE = re.compile(r"(?<![a-z0-9])p/")
_PUNCT_RE = re.compile(r"[./,;:()\\]")

# Cache do dicionário carregado. Chave "_phrase_sorted" guarda as frases já
# ordenadas por comprimento decrescente — pré-cálculo em load, para não
# reordenar a cada expand_synonyms (chamado milhares de vezes por treino).
_CACHE: dict[str, Any] | None = None


def _load(path: Path | None = None) -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None and path is None:
        return _CACHE
    p = Path(path) if path else _DEFAULT_PATH
    data: dict[str, Any] = {"phrase": {}, "token": {}, "abbrev": {}}
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            for key in ("phrase", "token", "abbrev"):
                data[key] = {normalize(k): v for k, v in (raw.get(key) or {}).items()}
            # Seções por idioma (phrase_en, phrase_es, token_en, ...) são
            # mescladas nas seções base: o vocabulário canônico-alvo é sempre PT.
            for section in raw:
                if "_" not in section or section.startswith("_"):
                    continue
                base, _, lang = section.partition("_")
                if base in ("phrase", "token", "abbrev") and lang in ("en", "es"):
                    for k, v in (raw.get(section) or {}).items():
                        data[base].setdefault(normalize(k), v)
            # Resolve cadeias no mapa de frases: se o valor de uma entrada é, ele
            # próprio, chave de outra (EN -> intermediário PT -> terminal), segue
            # até o terminal. Feito uma vez no load para o casamento em runtime
            # ser um único passe e nunca "crescer" por substring.
            data["phrase"] = _resolve_chains(data["phrase"])
        except (json.JSONDecodeError, OSError):
            pass
    # Pré-ordena frases por comprimento (uma vez), para expand_synonyms usar
    # em cada chamada sem re-sortear.
    data["_phrase_sorted"] = sorted(data["phrase"], key=len, reverse=True)
    if path is None:
        _CACHE = data
    return data


def _resolve_chains(phrase_map: dict[str, str], max_depth: int = 5) -> dict[str, str]:
    """
    Resolve cadeias de substituição: value que também é key vira o terminal.

    Ex.: {"cash...": "caixa e equivalentes de caixa",
          "caixa e equivalentes de caixa": "caixa"}
      -> {"cash...": "caixa", "caixa e equivalentes de caixa": "caixa"}

    Protege contra ciclos (para após max_depth ou ao repetir um valor).
    """
    resolved: dict[str, str] = {}
    for key, value in phrase_map.items():
        seen = {key}
        steps = 0
        while value in phrase_map and value not in seen and steps < max_depth:
            seen.add(value)
            value = phrase_map[value]
            steps += 1
        resolved[key] = value
    return resolved


def expand_synonyms(text: str, path: Path | None = None) -> str:
    """
    Expande uma descrição normalizada para o vocabulário canônico contábil.

    Args:
        text: descrição (será normalizada internamente).
        path: caminho alternativo do dicionário (para testes).

    Returns:
        Texto normalizado e expandido, pronto para fuzzy matching.
    """
    d = _load(path)
    s = normalize(text)
    if not s:
        return s

    # 1. Abreviações simbólicas com "/" que costumam vir GRUDADAS na próxima
    #    palavra (ex.: "banco c/aplicacoes", "pis s/faturamento"). Trata antes
    #    de transformar a pontuação em separador, senão o "/" viraria espaço e
    #    perderíamos o sentido de "com"/"sobre"/"para".
    s = _CS_RE.sub("com ", s)
    s = _SS_RE.sub("sobre ", s)
    s = _PS_RE.sub("para ", s)

    # 2. Pontuação que gruda tokens ("rec.recebidas", "forn/cred") vira espaço.
    s = _PUNCT_RE.sub(" ", s)

    # 3. Abreviações simbólicas isoladas restantes ("lp", "irrf", ...).
    if d["abbrev"]:
        tokens = [d["abbrev"].get(t, t) for t in s.split()]
        s = " ".join(tokens)

    # 4. Frases inteiras (substring), já pré-ordenadas por comprimento no _load.
    #    Cadeias EN -> intermediário PT -> canônico foram resolvidas no load;
    #    portanto um único passe basta e nunca cresce por substring.
    for phrase in d["_phrase_sorted"]:
        if phrase and phrase in s:
            s = s.replace(phrase, d["phrase"][phrase])

    # 5. Token-a-token (abreviações de termo). Colapsa espaços apenas ao final.
    if d["token"]:
        tokens = [d["token"].get(t, t) for t in s.split()]
        return " ".join(tokens)
    return " ".join(s.split())


_NUMERIC_RE = re.compile(r"^[\s\d.,\-()rR$%/]+$")


def is_garbage_description(descricao: str | None) -> bool:
    """
    Detecta descrições-lixo que não devem entrar no matching.

    Verdadeiro quando a descrição é vazia, puramente numérica/simbólica
    (ex.: "199687591.84", "-203123324.74", "0.0") ou curta demais para
    carregar significado contábil. São tipicamente linhas de total ou
    colunas de valor lidas como descrição por desalinhamento.
    """
    if descricao is None:
        return True
    s = str(descricao).strip()
    if not s:
        return True
    if _NUMERIC_RE.match(s):
        return True
    # precisa de ao menos 2 caracteres alfabéticos para ser uma conta
    letters = sum(1 for c in s if c.isalpha())
    return letters < 2


def reload_cache() -> None:
    """Força recarregar o dicionário (útil após edições)."""
    global _CACHE
    _CACHE = None
