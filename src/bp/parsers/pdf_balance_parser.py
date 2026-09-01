"""
PDFBalanceParser — extração de contas de balancetes/DFs em PDF nativo.

Estratégia por LINHA DE TEXTO com posição (x) das palavras, robusta a dois
casos comuns:
- Layout de coluna única (uma conta por linha: "Caixa .... 1.234,56")
- Layout lado-a-lado (Ativo à esquerda, Passivo à direita na MESMA linha:
  "Caixa 0 Fornecedores 14.766") — separado pela coordenada x.

Cada linha vira {codigo, descricao, saldo, nivel}. O código não existe em PDF,
então a descrição é usada como código (estratégia description-first, igual ao
dispatcher). PDFs escaneados (sem texto) retornam vazio — precisam de OCR.
"""

from __future__ import annotations

import re
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None


_HAS_ALPHA = re.compile(r"[A-Za-zÀ-ÿ]")

# "Valor real" (não referência de nota): tem separador de milhar/decimal, OU
# 3+ dígitos, OU é exatamente 0. Pode vir entre parênteses ou negativo.
_VALUE_RE = re.compile(r"^\(?-?(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+[.,]\d+|\d{3,}|0)\)?$")

# Compiladas 1x — parse() itera dezenas de milhares de tokens em DFs grandes.
_STRIP_NON_NUM_RE = re.compile(r"[^\d.,]")
_THOUSANDS_ONLY_RE = re.compile(r"\d{1,3}(\.\d{3})+")

# Linhas de ruído comuns em DFs (assinaturas, rodapés, cabeçalhos)
_NOISE = re.compile(
    r"cnpj|cpf|crc|tel\.?:|rua |avenida |www\.|http|"
    r"^em reais|^em milhares|^_+$|presidente|contador|diretor|"
    r"^p[aá]gina|^\d+/\d+$|notas explicativas|"
    r"de (janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)",
    re.IGNORECASE,
)


class PDFBalanceParser:
    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)

    def validate(self) -> bool:
        return (
            pdfplumber is not None
            and self.file_path.exists()
            and self.file_path.suffix.lower() == ".pdf"
        )

    def parse(self) -> list[dict[str, Any]]:
        if not self.validate():
            return []
        accounts: list[dict[str, Any]] = []
        seen = set()
        try:
            with pdfplumber.open(self.file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    try:
                        rows = self._parse_page(page)
                    except Exception as exc:
                        # Falha isolada de página: avisa (não fica silencioso
                        # como antes) e segue para as próximas páginas.
                        warnings.warn(
                            f"PDFBalanceParser: falha em {self.file_path.name} "
                            f"pág {page_num}: {exc}",
                            RuntimeWarning,
                            stacklevel=2,
                        )
                        continue
                    for descricao, saldo in rows:
                        key = (descricao.lower(), saldo)
                        if key in seen:
                            continue
                        seen.add(key)
                        accounts.append(
                            {
                                "codigo": descricao,
                                "descricao": descricao,
                                "saldo": saldo,
                                "nivel": 1,
                            }
                        )
        except Exception as exc:
            # Falha ao abrir/iterar o PDF: avisa e retorna o que conseguimos
            # extrair até aqui (nunca silencia como antes).
            warnings.warn(
                f"PDFBalanceParser: extração parcial de {self.file_path.name}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
        return accounts

    # ------------------------------------------------------------------
    def _parse_page(self, page) -> list[tuple[str, float]]:
        try:
            words = page.extract_words()
        except Exception:
            return []
        if not words:
            return []

        width = page.width or 600
        # Agrupa palavras em linhas por coordenada vertical (top), tolerância 3pt.
        lines: dict[int, list] = defaultdict(list)
        for w in words:
            lines[round(w["top"] / 3)].append(w)

        # Detecta se a página é lado-a-lado: há palavras dos dois lados do meio
        # em muitas linhas? Se sim, processa em 2 metades; senão, coluna única.
        two_col = self._is_two_column(lines, width)

        out: list[tuple[str, float]] = []
        for key in sorted(lines):
            ws = sorted(lines[key], key=lambda x: x["x0"])
            halves = (
                [[w for w in ws if w["x0"] < width / 2],
                 [w for w in ws if w["x0"] >= width / 2]]
                if two_col
                else [ws]
            )
            for hw in halves:
                if not hw:
                    continue
                text = " ".join(w["text"] for w in hw).strip()
                parsed = self._parse_line(text)
                if parsed:
                    out.append(parsed)
        return out

    @staticmethod
    def _is_two_column(lines: dict[int, list], width: float) -> bool:
        both = 0
        for ws in lines.values():
            has_left = any(w["x0"] < width * 0.45 for w in ws)
            has_right = any(w["x0"] > width * 0.55 for w in ws)
            if has_left and has_right:
                both += 1
        return both >= 3

    def _parse_line(self, text: str) -> tuple[str, float] | None:
        if not text or _NOISE.search(text):
            return None
        tokens = text.split()
        # Índice do primeiro token que é um VALOR real (não referência de nota).
        first_val = next(
            (i for i, t in enumerate(tokens) if _VALUE_RE.match(t)), None
        )
        if first_val is None or first_val == 0:
            return None  # sem valor, ou começa por número -> não é conta

        desc_tokens = tokens[:first_val]
        # Remove referência de nota pendurada no fim da descrição (um dígito
        # solto), mas apenas quando o token PRÉ-dígito já é uma palavra
        # completa (≥6 chars). Isso preserva identificadores curtos onde o
        # número faz parte do nome ("Loja 2", "CD 3") e limpa refs de nota
        # depois de substantivos ("Disponibilidades 1", "Fornecedores 2").
        if (
            len(desc_tokens) >= 2
            and desc_tokens[-1].isdigit()
            and len(desc_tokens[-1]) == 1
            and len(desc_tokens[-2]) >= 6
        ):
            desc_tokens = desc_tokens[:-1]

        descricao = " ".join(desc_tokens).strip(" .:-")
        if not _HAS_ALPHA.search(descricao) or len(descricao) < 3:
            return None
        saldo = self._to_float(tokens[first_val])
        if saldo is None:
            return None
        return descricao, saldo

    @staticmethod
    def _to_float(s: str) -> float | None:
        stripped = s.strip()
        neg = stripped.startswith("(") or stripped.startswith("-")
        digits = _STRIP_NON_NUM_RE.sub("", s)
        if not digits:
            return None
        # decide separador decimal: o último entre '.' e ',' é o decimal
        if "," in digits and "." in digits:
            if digits.rfind(",") > digits.rfind("."):
                digits = digits.replace(".", "").replace(",", ".")
            else:
                digits = digits.replace(",", "")
        elif "," in digits:
            digits = digits.replace(".", "").replace(",", ".")
        elif _THOUSANDS_ONLY_RE.fullmatch(digits):
            # só pontos e no formato 1.234 → separador de milhar
            digits = digits.replace(".", "")
        try:
            val = float(digits)
            return -val if neg else val
        except ValueError:
            return None
