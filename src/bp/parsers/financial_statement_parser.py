"""
FinancialStatementParser — Parser Completo de Demonstrações Financeiras (Fase 3.5)

Orquestra todo o pipeline de extração de BP e DRE de PDFs complexos.
Integra detecção, extração, validação e exportação em um único ponto de entrada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .pdf_utils import (
    StatementDetector,
    StatementTablePipeline,
    StatementType,
    TableValidator,
)
from .pdf_utils.detector import PDFTypeDetector


@dataclass
class FinancialStatementMetadata:
    """Metadados extraídos da demonstração financeira."""

    company: str | None = None
    cnpj: str | None = None
    period: str | None = None
    currency: str | None = None
    scale: str | None = None
    pdf_type: str = "unknown"  # 'native' ou 'scanned'
    pages_total: int = 0
    pages_bp: list[int] = field(default_factory=list)
    pages_dre: list[int] = field(default_factory=list)
    extraction_date: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


@dataclass
class StatementStructure:
    """Estrutura de uma demonstração (BP ou DRE)."""

    tipo: str  # 'BP' ou 'DRE'
    contas: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    validation_status: dict[str, Any] = field(default_factory=dict)


@dataclass
class FinancialStatementResult:
    """Resultado completo da extração de demonstrações financeiras."""

    balance_sheet: StatementStructure | None = None
    income_statement: StatementStructure | None = None
    metadata: FinancialStatementMetadata = field(
        default_factory=FinancialStatementMetadata
    )
    extraction_quality: dict[str, Any] = field(default_factory=dict)


class FinancialStatementParser:
    """
    Parser completo de Demonstrações Financeiras.

    Processa PDFs contendo BP e/ou DRE, detecta tipo, extrai estrutura,
    valida dados e exporta em formato padronizado.
    """

    def __init__(self, pdf_path: str | Path):
        """
        Args:
            pdf_path: Caminho para o PDF de demonstrações financeiras
        """
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF não encontrado: {self.pdf_path}")

        self.detector = StatementDetector()
        self.pipeline = StatementTablePipeline()
        self.validator = TableValidator()
        # PDFTypeDetector é instanciado sob demanda no analyze()

        self._analyzed = False
        self._analysis_result: dict[str, Any] | None = None

    # =========================================================================
    # Análise Inicial
    # =========================================================================

    def analyze(self) -> dict[str, Any]:
        """
        Analisa o PDF sem processar (rápido).

        Returns:
            Dict com informações: tipo, qualidade, páginas, demonstrações encontradas
        """
        if self._analyzed and self._analysis_result is not None:
            return self._analysis_result

        # Detecta tipo de PDF
        type_detector = PDFTypeDetector(self.pdf_path)
        detection = type_detector.detect_type()
        pdf_type = detection.get("type", "unknown")
        has_text = detection.get("has_text", False)

        # Extrai texto básico
        pages_text = self.pipeline.get_pages_text_hybrid(self.pdf_path)

        # Classifica e separa páginas por demonstração
        separated = self.detector.separate_statements(pages_text)

        # Metadados básicos da primeira página relevante
        metadata = {}
        for stmt_type in (StatementType.BALANCE_SHEET, StatementType.INCOME_STATEMENT):
            pages = separated.get(stmt_type, [])
            if pages:
                metadata = self.detector.extract_metadata(pages_text[pages[0]])
                break

        self._analysis_result = {
            "type": pdf_type,
            "has_text": has_text,
            "total_pages": len(pages_text),
            "statements": {
                "balance_sheet": [
                    i + 1 for i in separated.get(StatementType.BALANCE_SHEET, [])
                ],
                "income_statement": [
                    i + 1 for i in separated.get(StatementType.INCOME_STATEMENT, [])
                ],
                "notes": [i + 1 for i in separated.get(StatementType.NOTES, [])],
            },
            "metadata": metadata,
            "quality": "high" if has_text else "low",
        }
        self._analyzed = True
        return self._analysis_result

    # =========================================================================
    # Extração Individual
    # =========================================================================

    def extract_balance_sheet(self) -> StatementStructure:
        """
        Extrai apenas o Balanço Patrimonial.

        Returns:
            StatementStructure com BP
        """
        if not self._analyzed:
            self.analyze()

        result = self.pipeline.extract_structured_from_pdf(self.pdf_path)
        bp_pages = result.get("balance_sheet", [])

        # Mescla todas as páginas de BP
        all_rows = []
        for page in bp_pages:
            all_rows.extend(page.get("rows", []))

        # Valida estrutura
        validation = self._validate_statement(all_rows)

        metadata = result.get("metadata", {})

        return StatementStructure(
            tipo="BP",
            contas=all_rows,
            metadata=metadata,
            validation_status=validation,
        )

    def extract_income_statement(self) -> StatementStructure:
        """
        Extrai apenas a Demonstração do Resultado.

        Returns:
            StatementStructure com DRE
        """
        if not self._analyzed:
            self.analyze()

        result = self.pipeline.extract_structured_from_pdf(self.pdf_path)
        dre_pages = result.get("income_statement", [])

        # Mescla todas as páginas de DRE
        all_rows = []
        for page in dre_pages:
            all_rows.extend(page.get("rows", []))

        # Valida estrutura
        validation = self._validate_statement(all_rows)

        metadata = result.get("metadata", {})

        return StatementStructure(
            tipo="DRE",
            contas=all_rows,
            metadata=metadata,
            validation_status=validation,
        )

    # =========================================================================
    # Parsing Completo
    # =========================================================================

    def parse_complete(self) -> FinancialStatementResult:
        """
        Extrai BP e DRE completos do PDF.

        Returns:
            FinancialStatementResult com ambas demonstrações e metadados
        """
        # Análise inicial
        analysis = self.analyze()

        # Extração estruturada
        result = self.pipeline.extract_structured_from_pdf(self.pdf_path)

        # BP
        bp_pages = result.get("balance_sheet", [])
        bp_rows = []
        for page in bp_pages:
            bp_rows.extend(page.get("rows", []))

        bp_structure = None
        if bp_rows:
            bp_structure = StatementStructure(
                tipo="BP",
                contas=bp_rows,
                metadata=result.get("metadata", {}),
                validation_status=self._validate_statement(bp_rows),
            )

        # DRE
        dre_pages = result.get("income_statement", [])
        dre_rows = []
        for page in dre_pages:
            dre_rows.extend(page.get("rows", []))

        dre_structure = None
        if dre_rows:
            dre_structure = StatementStructure(
                tipo="DRE",
                contas=dre_rows,
                metadata=result.get("metadata", {}),
                validation_status=self._validate_statement(dre_rows),
            )

        # Metadados consolidados
        meta_dict = result.get("metadata", {})
        currency_info = meta_dict.get("currency", {})

        metadata = FinancialStatementMetadata(
            company=meta_dict.get("company"),
            cnpj=meta_dict.get("cnpj"),
            period=meta_dict.get("period"),
            currency=currency_info.get("currency"),
            scale=currency_info.get("scale"),
            pdf_type=analysis["type"],
            pages_total=analysis["total_pages"],
            pages_bp=list(analysis["statements"]["balance_sheet"]),
            pages_dre=list(analysis["statements"]["income_statement"]),
        )

        # Qualidade da extração
        quality = self._assess_extraction_quality(bp_structure, dre_structure)

        return FinancialStatementResult(
            balance_sheet=bp_structure,
            income_statement=dre_structure,
            metadata=metadata,
            extraction_quality=quality,
        )

    # =========================================================================
    # Mapeamento Inteligente
    # =========================================================================

    def map_balance_sheet_structure(
        self, bp: StatementStructure
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Mapeia estrutura hierárquica do BP (Ativo, Passivo, PL).

        Args:
            bp: Estrutura do BP

        Returns:
            Dict com 'ativo', 'passivo', 'patrimonio_liquido'
        """
        if not bp or not bp.contas:
            return {"ativo": [], "passivo": [], "patrimonio_liquido": []}

        ativo = []
        passivo = []
        pl = []

        current_section = None

        for conta in bp.contas:
            desc = (conta.get("descricao") or "").lower()

            # Detecta seção
            if any(k in desc for k in ["ativo", "asset"]):
                if (
                    any(k in desc for k in ["passivo", "liabilit"])
                    and not current_section
                ):
                    # linha "ATIVO | PASSIVO" no cabeçalho
                    continue
                current_section = "ativo"
            elif any(k in desc for k in ["passivo", "liabilit"]):
                current_section = "passivo"
            elif any(
                k in desc for k in ["patrimônio", "patrimonio", "equity", "capital"]
            ):
                current_section = "pl"

            # Adiciona à seção atual
            if current_section == "ativo":
                ativo.append(conta)
            elif current_section == "passivo":
                passivo.append(conta)
            elif current_section == "pl":
                pl.append(conta)

        return {"ativo": ativo, "passivo": passivo, "patrimonio_liquido": pl}

    def map_income_statement_structure(
        self, dre: StatementStructure
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Mapeia estrutura da DRE (receitas, custos, despesas, lucro).

        Args:
            dre: Estrutura da DRE

        Returns:
            Dict com categorias principais
        """
        if not dre or not dre.contas:
            return {}

        categories = {
            "receita": [],
            "custo": [],
            "despesa": [],
            "resultado": [],
        }

        for conta in dre.contas:
            desc = (conta.get("descricao") or "").lower()

            if any(k in desc for k in ["receita", "revenue", "vendas", "faturamento"]):
                categories["receita"].append(conta)
            elif any(k in desc for k in ["custo", "cost", "cpv", "cmv"]):
                categories["custo"].append(conta)
            elif any(k in desc for k in ["despesa", "expense"]):
                categories["despesa"].append(conta)
            elif any(
                k in desc for k in ["lucro", "prejuízo", "resultado", "profit", "loss"]
            ):
                categories["resultado"].append(conta)

        return categories

    # =========================================================================
    # Exportação
    # =========================================================================

    def export_to_standard_format(
        self, result: FinancialStatementResult
    ) -> dict[str, Any]:
        """
        Exporta resultado em formato JSON padronizado.

        Args:
            result: Resultado da extração

        Returns:
            Dict pronto para serialização JSON
        """
        output = {
            "metadata": {
                "company": result.metadata.company,
                "cnpj": result.metadata.cnpj,
                "period": result.metadata.period,
                "currency": result.metadata.currency,
                "scale": result.metadata.scale,
                "pdf_type": result.metadata.pdf_type,
                "extraction_date": result.metadata.extraction_date,
                "pages": {
                    "total": result.metadata.pages_total,
                    "balance_sheet": result.metadata.pages_bp,
                    "income_statement": result.metadata.pages_dre,
                },
            },
            "balance_sheet": None,
            "income_statement": None,
            "quality": result.extraction_quality,
        }

        if result.balance_sheet:
            bp_mapped = self.map_balance_sheet_structure(result.balance_sheet)
            output["balance_sheet"] = {
                "ativo": bp_mapped["ativo"],
                "passivo": bp_mapped["passivo"],
                "patrimonio_liquido": bp_mapped["patrimonio_liquido"],
                "validation": result.balance_sheet.validation_status,
            }

        if result.income_statement:
            dre_mapped = self.map_income_statement_structure(result.income_statement)
            output["income_statement"] = {
                "categories": dre_mapped,
                "validation": result.income_statement.validation_status,
            }

        return output

    def export_to_json(
        self, output_path: str | Path, result: FinancialStatementResult | None = None
    ) -> None:
        """
        Exporta resultado completo para arquivo JSON.

        Args:
            output_path: Caminho do arquivo de saída
            result: Resultado da extração (se None, executa parse_complete)
        """
        if result is None:
            result = self.parse_complete()

        standard = self.export_to_standard_format(result)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(standard, f, indent=2, ensure_ascii=False)

    def generate_report(self, result: FinancialStatementResult | None = None) -> str:
        """
        Gera relatório textual da extração.

        Args:
            result: Resultado da extração (se None, executa parse_complete)

        Returns:
            String com relatório formatado em Markdown
        """
        if result is None:
            result = self.parse_complete()

        lines = ["# Relatório de Extração de Demonstrações Financeiras", ""]
        lines.append(f"**PDF:** `{self.pdf_path.name}`")
        lines.append(f"**Data da Extração:** {result.metadata.extraction_date}")
        lines.append("")

        # Metadados
        lines.append("## Metadados")
        lines.append(f"- **Empresa:** {result.metadata.company or 'N/A'}")
        lines.append(f"- **CNPJ:** {result.metadata.cnpj or 'N/A'}")
        lines.append(f"- **Período:** {result.metadata.period or 'N/A'}")
        lines.append(f"- **Moeda:** {result.metadata.currency or 'N/A'}")
        lines.append(f"- **Escala:** {result.metadata.scale or 'N/A'}")
        lines.append(f"- **Tipo de PDF:** {result.metadata.pdf_type}")
        lines.append(f"- **Total de Páginas:** {result.metadata.pages_total}")
        lines.append(f"- **Páginas BP:** {result.metadata.pages_bp}")
        lines.append(f"- **Páginas DRE:** {result.metadata.pages_dre}")
        lines.append("")

        # Qualidade
        lines.append("## Qualidade da Extração")
        quality = result.extraction_quality
        lines.append(
            f"- **BP extraído:** {'✓' if quality.get('bp_extracted') else '✗'}"
        )
        lines.append(
            f"- **DRE extraído:** {'✓' if quality.get('dre_extracted') else '✗'}"
        )
        lines.append(f"- **Contas BP:** {quality.get('bp_accounts', 0)}")
        lines.append(f"- **Contas DRE:** {quality.get('dre_accounts', 0)}")
        lines.append(
            f"- **Valores extraídos (BP):** {quality.get('bp_values_count', 0)}/{quality.get('bp_accounts', 0)}"
        )
        lines.append(
            f"- **Valores extraídos (DRE):** {quality.get('dre_values_count', 0)}/{quality.get('dre_accounts', 0)}"
        )
        lines.append("")

        # BP
        if result.balance_sheet:
            lines.append("## Balanço Patrimonial")
            bp_mapped = self.map_balance_sheet_structure(result.balance_sheet)
            lines.append(f"- **Contas no Ativo:** {len(bp_mapped['ativo'])}")
            lines.append(f"- **Contas no Passivo:** {len(bp_mapped['passivo'])}")
            lines.append(f"- **Contas no PL:** {len(bp_mapped['patrimonio_liquido'])}")

            validation = result.balance_sheet.validation_status
            lines.append(
                f"- **Totais detectados:** {validation.get('totals_detected', 0)}"
            )
            lines.append(f"- **Totais válidos:** {validation.get('totals_valid', 0)}")
            lines.append("")

        # DRE
        if result.income_statement:
            lines.append("## Demonstração do Resultado")
            dre_mapped = self.map_income_statement_structure(result.income_statement)
            lines.append(
                f"- **Linhas de Receita:** {len(dre_mapped.get('receita', []))}"
            )
            lines.append(f"- **Linhas de Custo:** {len(dre_mapped.get('custo', []))}")
            lines.append(
                f"- **Linhas de Despesa:** {len(dre_mapped.get('despesa', []))}"
            )
            lines.append(
                f"- **Linhas de Resultado:** {len(dre_mapped.get('resultado', []))}"
            )

            validation = result.income_statement.validation_status
            lines.append(
                f"- **Totais detectados:** {validation.get('totals_detected', 0)}"
            )
            lines.append(f"- **Totais válidos:** {validation.get('totals_valid', 0)}")
            lines.append("")

        return "\n".join(lines)

    # =========================================================================
    # Helpers Internos
    # =========================================================================

    def _validate_statement(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Valida estrutura de uma demonstração."""
        totals_detected = sum(
            1 for r in rows if self.validator.is_total_line(r.get("descricao", ""))
        )
        totals_valid = 1 if self.validator.validate_block_sum(rows) else 0

        return {"totals_detected": totals_detected, "totals_valid": totals_valid}

    def _assess_extraction_quality(
        self,
        bp: StatementStructure | None,
        dre: StatementStructure | None,
    ) -> dict[str, Any]:
        """Avalia qualidade geral da extração."""
        quality = {
            "bp_extracted": bp is not None and len(bp.contas) > 0,
            "dre_extracted": dre is not None and len(dre.contas) > 0,
            "bp_accounts": len(bp.contas) if bp else 0,
            "dre_accounts": len(dre.contas) if dre else 0,
            "bp_values_count": 0,
            "dre_values_count": 0,
        }

        if bp:
            quality["bp_values_count"] = sum(
                1
                for c in bp.contas
                if isinstance(c.get("current"), (int, float))
                or isinstance(c.get("previous"), (int, float))
            )

        if dre:
            quality["dre_values_count"] = sum(
                1
                for c in dre.contas
                if isinstance(c.get("current"), (int, float))
                or isinstance(c.get("previous"), (int, float))
            )

        return quality
