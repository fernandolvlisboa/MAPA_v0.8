"""
StatementDetector — Detector de Demonstrações Financeiras

Identifica e classifica páginas de PDF como:
- Balanço Patrimonial (BP)
- Demonstração de Resultados (DRE)
- Notas Explicativas
- Outras (ruído, auditoria, etc.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .patterns import (
    BP_PATTERNS,
    BP_STRONG_PATTERNS,
    DRE_PATTERNS,
    DRE_STRONG_PATTERNS,
    NOISE_PATTERNS,
    NOTES_PATTERNS,
    count_pattern_matches,
    extract_currency_info,
)


class StatementType(Enum):
    """Tipo de demonstração financeira."""

    BALANCE_SHEET = "balance_sheet"  # Balanço Patrimonial
    INCOME_STATEMENT = "income_statement"  # DRE
    NOTES = "notes"  # Notas Explicativas
    AUDIT_REPORT = "audit_report"  # Relatório de Auditoria
    OTHER = "other"  # Outros
    UNKNOWN = "unknown"  # Não identificado


@dataclass
class PageClassification:
    """Resultado da classificação de uma página."""

    page_number: int
    statement_type: StatementType
    confidence: float  # 0.0 a 1.0
    bp_score: float
    dre_score: float
    notes_score: float
    noise_score: float
    text_sample: str  # Primeiras linhas do texto


class StatementDetector:
    """
    Detector de demonstrações financeiras em PDFs.

    Usa padrões de keywords para identificar:
    - Balanço Patrimonial
    - DRE
    - Notas Explicativas
    """

    def __init__(
        self,
        min_confidence: float = 0.3,
        bp_weight: float = 1.0,
        dre_weight: float = 1.0,
        notes_weight: float = 0.5,
    ):
        """
        Args:
            min_confidence: Confiança mínima para classificação (0.0-1.0)
            bp_weight: Peso para detecção de BP
            dre_weight: Peso para detecção de DRE
            notes_weight: Peso para detecção de notas
        """
        self.min_confidence = min_confidence
        self.bp_weight = bp_weight
        self.dre_weight = dre_weight
        self.notes_weight = notes_weight

    def classify_page(
        self, page_number: int, text: str, max_sample_lines: int = 50
    ) -> PageClassification:
        """
        Classifica uma página de PDF.

        Args:
            page_number: Número da página (0-indexed)
            text: Texto extraído da página
            max_sample_lines: Máximo de linhas para amostra

        Returns:
            PageClassification com resultado
        """
        # Normaliza texto
        text_lower = text.lower()

        # Calcula scores
        bp_score = self._calculate_bp_score(text_lower)
        dre_score = self._calculate_dre_score(text_lower)
        notes_score = self._calculate_notes_score(text_lower)
        noise_score = self._calculate_noise_score(text_lower)

        # Determina tipo baseado nos scores
        statement_type, confidence = self._determine_type(
            bp_score, dre_score, notes_score, noise_score
        )

        # Extrai amostra do texto
        lines = text.split("\n")[:max_sample_lines]
        text_sample = "\n".join(lines)

        return PageClassification(
            page_number=page_number,
            statement_type=statement_type,
            confidence=confidence,
            bp_score=bp_score,
            dre_score=dre_score,
            notes_score=notes_score,
            noise_score=noise_score,
            text_sample=text_sample,
        )

    def classify_pages(self, pages_text: list[str]) -> list[PageClassification]:
        """
        Classifica múltiplas páginas.

        Args:
            pages_text: Lista de textos (um por página)

        Returns:
            Lista de PageClassification
        """
        return [self.classify_page(i, text) for i, text in enumerate(pages_text)]

    def find_balance_sheet_pages(self, pages_text: list[str]) -> list[int]:
        """
        Encontra páginas com Balanço Patrimonial.

        Args:
            pages_text: Lista de textos das páginas

        Returns:
            Lista de números de páginas com BP
        """
        classifications = self.classify_pages(pages_text)
        return [
            c.page_number
            for c in classifications
            if c.statement_type == StatementType.BALANCE_SHEET
            and c.confidence >= self.min_confidence
        ]

    def find_income_statement_pages(self, pages_text: list[str]) -> list[int]:
        """
        Encontra páginas com DRE.

        Args:
            pages_text: Lista de textos das páginas

        Returns:
            Lista de números de páginas com DRE
        """
        classifications = self.classify_pages(pages_text)
        return [
            c.page_number
            for c in classifications
            if c.statement_type == StatementType.INCOME_STATEMENT
            and c.confidence >= self.min_confidence
        ]

    def separate_statements(
        self, pages_text: list[str]
    ) -> dict[StatementType, list[int]]:
        """
        Separa páginas por tipo de demonstração.

        Args:
            pages_text: Lista de textos das páginas

        Returns:
            Dict mapeando tipo → lista de números de páginas
        """
        classifications = self.classify_pages(pages_text)

        result = {
            StatementType.BALANCE_SHEET: [],
            StatementType.INCOME_STATEMENT: [],
            StatementType.NOTES: [],
            StatementType.AUDIT_REPORT: [],
            StatementType.OTHER: [],
            StatementType.UNKNOWN: [],
        }

        for c in classifications:
            if c.confidence >= self.min_confidence:
                result[c.statement_type].append(c.page_number)

        return result

    def extract_metadata(self, text: str) -> dict[str, any]:
        """
        Extrai metadados do texto (empresa, período, moeda).

        Args:
            text: Texto para analisar

        Returns:
            Dict com metadados extraídos
        """
        metadata = {
            "company": self._extract_company_name(text),
            "period": self._extract_period(text),
            "currency": extract_currency_info(text),
            "cnpj": self._extract_cnpj(text),
        }

        return metadata

    # ========================================================================
    # MÉTODOS PRIVADOS
    # ========================================================================

    def _calculate_bp_score(self, text: str) -> float:
        """Calcula score de BP (0.0 a 1.0)."""
        # Palavras fortes valem mais
        strong_matches = count_pattern_matches(text, BP_STRONG_PATTERNS)
        normal_matches = count_pattern_matches(text, BP_PATTERNS)

        # Score ponderado
        score = (strong_matches * 3.0 + normal_matches) / 20.0
        return min(1.0, score * self.bp_weight)

    def _calculate_dre_score(self, text: str) -> float:
        """Calcula score de DRE (0.0 a 1.0)."""
        strong_matches = count_pattern_matches(text, DRE_STRONG_PATTERNS)
        normal_matches = count_pattern_matches(text, DRE_PATTERNS)

        score = (strong_matches * 3.0 + normal_matches) / 20.0
        return min(1.0, score * self.dre_weight)

    def _calculate_notes_score(self, text: str) -> float:
        """Calcula score de Notas Explicativas (0.0 a 1.0)."""
        matches = count_pattern_matches(text, NOTES_PATTERNS)
        score = matches / 5.0
        return min(1.0, score * self.notes_weight)

    def _calculate_noise_score(self, text: str) -> float:
        """Calcula score de ruído (0.0 a 1.0)."""
        matches = count_pattern_matches(text, NOISE_PATTERNS)
        score = matches / 5.0
        return min(1.0, score)

    def _determine_type(
        self,
        bp_score: float,
        dre_score: float,
        notes_score: float,
        noise_score: float,
    ) -> tuple[StatementType, float]:
        """
        Determina o tipo de demonstração baseado nos scores.

        Returns:
            (StatementType, confiança)
        """
        # Se for muito ruído, marca como OTHER
        if noise_score > 0.5:
            return StatementType.OTHER, noise_score

        # Encontra maior score
        scores = {
            StatementType.BALANCE_SHEET: bp_score,
            StatementType.INCOME_STATEMENT: dre_score,
            StatementType.NOTES: notes_score,
        }

        max_type = max(scores, key=scores.get)
        max_score = scores[max_type]

        # Se score muito baixo, marca como UNKNOWN
        if max_score < 0.2:
            return StatementType.UNKNOWN, 0.0

        return max_type, max_score

    def _extract_company_name(self, text: str) -> str | None:
        """Extrai nome da empresa do texto."""
        # Busca padrões comuns de nome de empresa
        patterns = [
            r"^([A-ZÀÂÃÁÉÊÍÓÔÕÚÇ\s\.]+(?:LTDA|S\.?A\.?|S/A)\.?)$",
            r"^([\w\s\.]+(?:LTDA|S\.?A\.?|S/A))",
        ]

        lines = text.split("\n")[:10]  # Primeiras 10 linhas

        for line in lines:
            line = line.strip()
            for pattern in patterns:
                match = re.search(pattern, line, re.IGNORECASE | re.MULTILINE)
                if match:
                    return match.group(1).strip()

        return None

    def _extract_period(self, text: str) -> str | None:
        """Extrai período/data do texto."""
        # Padrões de data
        patterns = [
            r"em\s+(\d{2}/\d{2}/\d{4})",
            r"(\d{2}/\d{2}/\d{4})",
            r"em\s+(\d{2}\s+de\s+\w+\s+de\s+\d{4})",
            r"exerc[íi]cio\s+de\s+(\d{4})",
            r"per[íi]odo\s+de\s+(\d{2}/\d{2}/\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_cnpj(self, text: str) -> str | None:
        """Extrai CNPJ do texto."""
        pattern = r"cnpj:?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

        # Tenta sem formatação
        pattern = r"cnpj:?\s*(\d{14})"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            cnpj = match.group(1)
            # Formata
            return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

        return None
