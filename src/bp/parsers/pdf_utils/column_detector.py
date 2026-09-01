"""
ColumnDetector — Detector de Colunas em Demonstrações Financeiras

Identifica e separa colunas em demonstrações:
- Atual vs Anterior
- Consolidado vs Individual
- Múltiplas moedas
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .patterns import COLUMN_PATTERNS


class ColumnType(Enum):
    """Tipos de colunas identificadas."""

    CURRENT = "current"  # Período atual
    PREVIOUS = "previous"  # Período anterior
    CONSOLIDATED = "consolidated"  # Consolidado
    INDIVIDUAL = "individual"  # Individual/Controladora
    DESCRIPTION = "description"  # Descrição de conta
    CODE = "code"  # Código de conta
    UNKNOWN = "unknown"  # Não identificado


@dataclass
class ColumnInfo:
    """Informação sobre uma coluna."""

    index: int
    column_type: ColumnType
    header: str
    confidence: float  # 0.0 a 1.0
    period: str | None = None  # Ex: "12/2024"


@dataclass
class ColumnLayout:
    """Layout de colunas detectado."""

    columns: list[ColumnInfo]
    has_comparative: bool  # Tem coluna comparativa
    has_consolidated: bool  # Tem consolidado/individual
    description_column: int | None = None
    code_column: int | None = None
    current_column: int | None = None
    previous_column: int | None = None


class ColumnDetector:
    """
    Detector de colunas em demonstrações financeiras.

    Identifica estrutura de colunas baseado em headers e padrões.
    """

    def __init__(
        self,
        min_confidence: float = 0.5,
    ):
        """
        Args:
            min_confidence: Confiança mínima para detecção (0.0-1.0)
        """
        self.min_confidence = min_confidence

    def detect_columns(self, header_row: list[str]) -> ColumnLayout:
        """
        Detecta layout de colunas a partir do cabeçalho.

        Args:
            header_row: Lista de strings do cabeçalho

        Returns:
            ColumnLayout com informações das colunas
        """
        columns = []

        for idx, header in enumerate(header_row):
            if not header:
                continue

            header_clean = header.strip().lower()
            col_type, confidence, period = self._classify_column(header_clean)

            columns.append(
                ColumnInfo(
                    index=idx,
                    column_type=col_type,
                    header=header,
                    confidence=confidence,
                    period=period,
                )
            )

        # Analisa layout
        layout = self._analyze_layout(columns)
        return layout

    def extract_comparative_values(
        self, row: list[str], layout: ColumnLayout
    ) -> dict[str, float | None]:
        """
        Extrai valores atuais e anteriores de uma linha.

        Args:
            row: Lista de valores da linha
            layout: Layout das colunas

        Returns:
            Dict com 'current' e 'previous'
        """
        result = {
            "current": None,
            "previous": None,
        }

        if layout.current_column is not None and layout.current_column < len(row):
            result["current"] = self._parse_value(row[layout.current_column])

        if layout.previous_column is not None and layout.previous_column < len(row):
            result["previous"] = self._parse_value(row[layout.previous_column])

        return result

    def split_consolidated_individual(
        self, table: list[list[str]], layout: ColumnLayout
    ) -> tuple[list[list[str]], list[list[str]]]:
        """
        Separa tabela em consolidado e individual.

        Args:
            table: Tabela completa
            layout: Layout das colunas

        Returns:
            (tabela_consolidado, tabela_individual)
        """
        # TODO: Implementar separação quando temos colunas consolidado/individual
        # Por enquanto retorna tabela completa em ambos
        return table, table

    def detect_period_columns(self, header_row: list[str]) -> dict[str, int]:
        """
        Detecta colunas de período (datas).

        Args:
            header_row: Cabeçalho da tabela

        Returns:
            Dict mapeando período → índice da coluna
        """
        period_columns = {}

        for idx, header in enumerate(header_row):
            if not header:
                continue

            # Detecta padrões de data
            period = self._extract_period(header)
            if period:
                period_columns[period] = idx

        return period_columns

    def identify_description_column(self, header_row: list[str]) -> int | None:
        """
        Identifica a coluna de descrição de contas.

        Args:
            header_row: Cabeçalho da tabela

        Returns:
            Índice da coluna de descrição ou None
        """
        description_patterns = [
            r"descri[çc][ãa]o",
            r"conta",
            r"t[íi]tulo",
            r"nome",
            r"item",
            r"description",
        ]

        for idx, header in enumerate(header_row):
            if not header:
                continue

            header_lower = header.lower()
            for pattern in description_patterns:
                if re.search(pattern, header_lower):
                    return idx

        # Se não encontrou, assume primeira coluna não-numérica
        for idx, header in enumerate(header_row):
            if header and not self._is_numeric_header(header):
                return idx

        return 0  # Fallback: primeira coluna

    def identify_value_columns(self, header_row: list[str]) -> list[int]:
        """
        Identifica colunas que contêm valores numéricos.

        Args:
            header_row: Cabeçalho da tabela

        Returns:
            Lista de índices de colunas numéricas
        """
        value_columns = []

        for idx, header in enumerate(header_row):
            if not header:
                continue

            if self._is_numeric_header(header) or self._is_period_header(header):
                value_columns.append(idx)

        return value_columns

    # ========================================================================
    # MÉTODOS PRIVADOS
    # ========================================================================

    def _classify_column(self, header: str) -> tuple[ColumnType, float, str | None]:
        """
        Classifica tipo da coluna baseado no header.

        Returns:
            (tipo, confiança, período)
        """
        # Detecta descrição
        if re.search(r"descri[çc][ãa]o|conta|t[íi]tulo", header):
            return ColumnType.DESCRIPTION, 0.9, None

        # Detecta código
        if re.search(r"c[óo]digo|cod|code", header):
            return ColumnType.CODE, 0.9, None

        # Detecta período
        period = self._extract_period(header)
        if period:
            # Verifica se é atual ou anterior baseado em keywords
            if any(p in header for p in COLUMN_PATTERNS["current"]):
                return ColumnType.CURRENT, 0.8, period
            elif any(p in header for p in COLUMN_PATTERNS["previous"]):
                return ColumnType.PREVIOUS, 0.8, period
            else:
                return ColumnType.CURRENT, 0.6, period

        # Detecta consolidado/individual
        if any(p in header for p in COLUMN_PATTERNS["consolidated"]):
            return ColumnType.CONSOLIDATED, 0.8, None
        if any(p in header for p in COLUMN_PATTERNS["individual"]):
            return ColumnType.INDIVIDUAL, 0.8, None

        # Detecta atual/anterior sem período específico
        if any(p in header for p in COLUMN_PATTERNS["current"]):
            return ColumnType.CURRENT, 0.7, None
        if any(p in header for p in COLUMN_PATTERNS["previous"]):
            return ColumnType.PREVIOUS, 0.7, None

        # Se parece numérico mas não identificou, assume atual
        if self._is_numeric_header(header):
            return ColumnType.CURRENT, 0.5, None

        return ColumnType.UNKNOWN, 0.0, None

    def _analyze_layout(self, columns: list[ColumnInfo]) -> ColumnLayout:
        """Analisa layout das colunas."""
        layout = ColumnLayout(
            columns=columns,
            has_comparative=False,
            has_consolidated=False,
        )

        # Identifica colunas específicas
        for col in columns:
            if col.column_type == ColumnType.DESCRIPTION:
                layout.description_column = col.index
            elif col.column_type == ColumnType.CODE:
                layout.code_column = col.index
            elif (
                col.column_type == ColumnType.CURRENT and layout.current_column is None
            ):
                layout.current_column = col.index
            elif (
                col.column_type == ColumnType.PREVIOUS
                and layout.previous_column is None
            ):
                layout.previous_column = col.index

        # Se temos múltiplas colunas CURRENT com períodos, ajusta para current/previous
        current_cols = [
            c for c in columns if c.column_type == ColumnType.CURRENT and c.period
        ]
        if len(current_cols) >= 2:
            # Ordena por período (mais recente primeiro)
            current_cols_sorted = sorted(
                current_cols,
                key=lambda c: self._period_to_sortable(c.period),
                reverse=True,
            )

            # Mais recente = current, outros = previous
            layout.current_column = current_cols_sorted[0].index
            layout.previous_column = current_cols_sorted[1].index

        # Verifica se tem comparativo
        layout.has_comparative = (
            layout.current_column is not None and layout.previous_column is not None
        )

        # Verifica se tem consolidado/individual
        has_consolidated = any(
            c.column_type == ColumnType.CONSOLIDATED for c in columns
        )
        has_individual = any(c.column_type == ColumnType.INDIVIDUAL for c in columns)
        layout.has_consolidated = has_consolidated or has_individual

        return layout

    def _extract_period(self, header: str) -> str | None:
        """Extrai período/data do header."""
        # Padrão MM/YYYY
        match = re.search(r"(\d{2}/\d{4})", header)
        if match:
            return match.group(1)

        # Padrão YYYY
        match = re.search(r"\b(20\d{2})\b", header)
        if match:
            return match.group(1)

        # Padrão DD/MM/YYYY
        match = re.search(r"(\d{2}/\d{2}/\d{4})", header)
        if match:
            return match.group(1)

        return None

    def _is_numeric_header(self, header: str) -> bool:
        """Verifica se header indica coluna numérica."""
        # Tem números ou símbolos de moeda
        if re.search(r"\d|r\$|\$|€", header, re.IGNORECASE):
            return True

        # Keywords de valores
        value_keywords = [r"saldo", r"valor", r"montante", r"total"]
        return any(re.search(keyword, header, re.IGNORECASE) for keyword in value_keywords)

    def _is_period_header(self, header: str) -> bool:
        """Verifica se header contém período."""
        return self._extract_period(header) is not None

    def _period_to_sortable(self, period: str | None) -> int:
        """
        Converte período para número sortável.

        Args:
            period: String de período (ex: "12/2024", "2024", "31/12/2024")

        Returns:
            Número inteiro para ordenação (maior = mais recente)
        """
        if not period:
            return 0

        # MM/YYYY -> YYYYMM
        match = re.search(r"(\d{2})/(\d{4})", period)
        if match:
            month, year = match.groups()
            return int(year) * 100 + int(month)

        # DD/MM/YYYY -> YYYYMMDD
        match = re.search(r"(\d{2})/(\d{2})/(\d{4})", period)
        if match:
            day, month, year = match.groups()
            return int(year) * 10000 + int(month) * 100 + int(day)

        # YYYY -> YYYY00
        match = re.search(r"(20\d{2})", period)
        if match:
            year = match.group(1)
            return int(year) * 100

        return 0

    def _parse_value(self, value_str: str) -> float | None:
        """Converte string para float."""
        if not value_str or not isinstance(value_str, str):
            return None

        # Remove espaços e símbolos de moeda
        value_clean = value_str.strip()
        value_clean = re.sub(r"[R$€\s]", "", value_clean, flags=re.IGNORECASE)

        # Trata formato brasileiro (. para milhares, , para decimal)
        if "," in value_clean and "." in value_clean:
            # Formato: 1.234.567,89
            value_clean = value_clean.replace(".", "").replace(",", ".")
        elif "," in value_clean:
            # Formato: 1234,89
            value_clean = value_clean.replace(",", ".")

        # Trata parênteses (número negativo)
        is_negative = value_clean.startswith("(") and value_clean.endswith(")")
        if is_negative:
            value_clean = value_clean[1:-1]

        # Converte
        try:
            value = float(value_clean)
            return -value if is_negative else value
        except ValueError:
            return None
