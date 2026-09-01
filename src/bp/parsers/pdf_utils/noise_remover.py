"""
NoiseRemover — Removedor de Ruído de PDFs

Remove elementos indesejados de PDFs:
- Assinaturas e carimbos
- Cabeçalhos e rodapés repetitivos
- Elementos de auditoria
- Linhas vazias ou irrelevantes
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .patterns import (
    HEADER_FOOTER_COMPILED,
    NOISE_PATTERNS,
    match_any_pattern,
)


@dataclass
class CleanedText:
    """Resultado da limpeza de texto."""

    original_lines: int
    cleaned_lines: int
    removed_lines: int
    clean_text: str
    removed_text: list[str]
    noise_score: float  # 0.0 a 1.0


class NoiseRemover:
    """
    Remove ruído de texto extraído de PDFs.

    Identifica e remove:
    - Linhas de assinatura e aprovação
    - Cabeçalhos e rodapés repetitivos
    - Elementos de auditoria
    - Linhas muito curtas ou vazias
    """

    def __init__(
        self,
        min_line_length: int = 3,
        remove_duplicates: bool = True,
        remove_short_lines: bool = True,
        remove_headers_footers: bool = True,
    ):
        """
        Args:
            min_line_length: Comprimento mínimo de linha válida
            remove_duplicates: Remover linhas duplicadas
            remove_short_lines: Remover linhas muito curtas
            remove_headers_footers: Remover cabeçalhos e rodapés
        """
        self.min_line_length = min_line_length
        self.remove_duplicates = remove_duplicates
        self.remove_short_lines = remove_short_lines
        self.remove_headers_footers = remove_headers_footers

    def clean_text(self, text: str) -> CleanedText:
        """
        Remove ruído do texto.

        Args:
            text: Texto para limpar

        Returns:
            CleanedText com resultado
        """
        lines = text.split("\n")
        original_count = len(lines)

        removed_lines = []
        seen_lines = set() if self.remove_duplicates else None

        clean_lines = []

        for line in lines:
            line_stripped = line.strip()

            # Pula linhas vazias
            if not line_stripped:
                continue

            # Remove linhas muito curtas
            if self.remove_short_lines and len(line_stripped) < self.min_line_length:
                removed_lines.append(line)
                continue

            # Remove linhas de ruído
            if self._is_noise_line(line_stripped):
                removed_lines.append(line)
                continue

            # Remove cabeçalhos/rodapés
            if self.remove_headers_footers and self._is_header_footer(line_stripped):
                removed_lines.append(line)
                continue

            # Remove duplicatas
            if self.remove_duplicates:
                if line_stripped in seen_lines:
                    removed_lines.append(line)
                    continue
                seen_lines.add(line_stripped)

            # Linha válida
            clean_lines.append(line)

        clean_text = "\n".join(clean_lines)
        noise_score = len(removed_lines) / max(1, original_count)

        return CleanedText(
            original_lines=original_count,
            cleaned_lines=len(clean_lines),
            removed_lines=len(removed_lines),
            clean_text=clean_text,
            removed_text=removed_lines,
            noise_score=noise_score,
        )

    def remove_signature_areas(self, text: str) -> str:
        """
        Remove áreas de assinatura do texto.

        Args:
            text: Texto para processar

        Returns:
            Texto sem áreas de assinatura
        """
        # Padrões de início de área de assinatura
        signature_starts = [
            r"assinaturas?",
            r"aprovad[oa]",
            r"certificad[oa]",
            r"_+\s*$",  # Linhas de assinatura
        ]

        lines = text.split("\n")
        result_lines = []
        in_signature_area = False

        for line in lines:
            line_lower = line.lower().strip()

            # Detecta início de área de assinatura
            for pattern in signature_starts:
                if re.search(pattern, line_lower, re.IGNORECASE):
                    in_signature_area = True
                    break

            # Se não estiver em área de assinatura, mantém a linha
            if not in_signature_area:
                result_lines.append(line)

        return "\n".join(result_lines)

    def identify_repetitive_lines(
        self, pages_text: list[str], min_occurrences: int = 2
    ) -> set[str]:
        """
        Identifica linhas que se repetem em múltiplas páginas.

        Útil para detectar cabeçalhos e rodapés.

        Args:
            pages_text: Lista de textos das páginas
            min_occurrences: Mínimo de ocorrências para considerar repetitivo

        Returns:
            Set de linhas repetitivas
        """
        line_counts = {}

        for page_text in pages_text:
            lines = page_text.split("\n")
            unique_lines = {line.strip() for line in lines if line.strip()}

            for line in unique_lines:
                line_counts[line] = line_counts.get(line, 0) + 1

        # Retorna linhas que aparecem em múltiplas páginas
        repetitive = {
            line for line, count in line_counts.items() if count >= min_occurrences
        }

        return repetitive

    def remove_repetitive_lines(self, text: str, repetitive_lines: set[str]) -> str:
        """
        Remove linhas repetitivas do texto.

        Args:
            text: Texto para limpar
            repetitive_lines: Set de linhas a remover

        Returns:
            Texto limpo
        """
        lines = text.split("\n")
        clean_lines = [line for line in lines if line.strip() not in repetitive_lines]

        return "\n".join(clean_lines)

    def filter_page_numbers(self, text: str) -> str:
        """
        Remove linhas que são apenas números de página.

        Args:
            text: Texto para filtrar

        Returns:
            Texto sem números de página
        """
        page_number_patterns = [
            r"^\s*p[áa]g(?:ina)?\.?\s*\d+\s*$",
            r"^\s*\d+\s*/\s*\d+\s*$",
            r"^\s*\d+\s*$",  # Apenas número
        ]

        lines = text.split("\n")
        clean_lines = []

        for line in lines:
            is_page_number = False
            for pattern in page_number_patterns:
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    is_page_number = True
                    break

            if not is_page_number:
                clean_lines.append(line)

        return "\n".join(clean_lines)

    def extract_relevant_sections(
        self,
        text: str,
        start_keywords: list[str],
        end_keywords: list[str],
    ) -> list[str]:
        """
        Extrai seções relevantes entre keywords de início e fim.

        Args:
            text: Texto para processar
            start_keywords: Keywords que indicam início de seção
            end_keywords: Keywords que indicam fim de seção

        Returns:
            Lista de seções extraídas
        """
        sections = []
        lines = text.split("\n")

        in_section = False
        current_section = []

        for line in lines:
            line_lower = line.lower()

            # Detecta início de seção
            if not in_section:
                for keyword in start_keywords:
                    if keyword.lower() in line_lower:
                        in_section = True
                        current_section = [line]
                        break

            # Se estiver em seção, acumula linhas
            elif in_section:
                current_section.append(line)

                # Detecta fim de seção
                for keyword in end_keywords:
                    if keyword.lower() in line_lower:
                        sections.append("\n".join(current_section))
                        in_section = False
                        current_section = []
                        break

        # Se seção não fechou, adiciona mesmo assim
        if current_section:
            sections.append("\n".join(current_section))

        return sections

    # ========================================================================
    # MÉTODOS PRIVADOS
    # ========================================================================

    def _is_noise_line(self, line: str) -> bool:
        """Verifica se a linha contém ruído."""
        return match_any_pattern(line, NOISE_PATTERNS)

    def _is_header_footer(self, line: str) -> bool:
        """Verifica se a linha é cabeçalho ou rodapé."""
        # Linhas muito curtas geralmente são cabeçalhos
        if len(line) < 5:
            return True

        # Padrões de cabeçalho/rodapé
        return match_any_pattern(line, HEADER_FOOTER_COMPILED)

    def _contains_only_special_chars(self, line: str) -> bool:
        """Verifica se linha contém apenas caracteres especiais."""
        # Remove espaços
        line_clean = line.replace(" ", "")

        # Se ficou vazio, é só espaços
        if not line_clean:
            return True

        # Se tem apenas caracteres não-alfanuméricos
        return not any(c.isalnum() for c in line_clean)
