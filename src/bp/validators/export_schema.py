"""Export Schema Validator — BP System

Valida contas extraídas pelos parsers ANTES do export.
Garante que dados atendem ao contrato de exportação.

Baseado em: docs/EXPORT_CONTRACT_V2.md (19 colunas obrigatórias)
"""

from dataclasses import dataclass, field
from typing import Any

from ..utils.numero import parse_saldo


@dataclass
class ExportValidationResult:
    """Resultado de validação de contas para export"""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "✅ VÁLIDO" if self.valid else "❌ INVÁLIDO"
        msg = [f"Validação: {status}"]

        if self.errors:
            msg.append(f"\nErros ({len(self.errors)}):")
            for err in self.errors:
                msg.append(f"  ❌ {err}")

        if self.warnings:
            msg.append(f"\nWarnings ({len(self.warnings)}):")
            for warn in self.warnings:
                msg.append(f"  ⚠️  {warn}")

        if self.metrics:
            msg.append("\nMétricas:")
            for key, value in self.metrics.items():
                msg.append(f"  • {key}: {value}")

        return "\n".join(msg)


def validate_parsed_accounts(accounts: list[dict[str, Any]]) -> ExportValidationResult:
    """
    Valida contas extraídas do parser ANTES do matching/export.

    Esta é a primeira linha de defesa - garante que parsers
    extraíram dados minimamente válidos para processamento posterior.

    Validações Críticas (bloqueiam export):
    - Lista não vazia
    - Todas contas têm descrição
    - Todos saldos são numéricos

    Validações de Warning (não bloqueiam):
    - Nível válido (inteiro >= 1)
    - Código no formato esperado (se presente)

    Args:
        accounts: Lista de dicionários retornados por ParseyCaller.parse()

    Returns:
        ExportValidationResult com status, erros, warnings e métricas

    Example:
        >>> accounts = ParseyCaller(file_path).parse()
        >>> validation = validate_parsed_accounts(accounts)
        >>> if not validation.valid:
        >>>     raise ValueError(f"Parse failed: {validation.errors}")
    """
    errors = []
    warnings = []

    # ========================================
    # VALIDAÇÃO CRÍTICA 1: Lista não vazia
    # ========================================
    if not accounts:
        errors.append("No accounts extracted - parser returned empty list")
        return ExportValidationResult(
            valid=False, errors=errors, warnings=warnings, metrics={}
        )

    total_accounts = len(accounts)

    # ========================================
    # VALIDAÇÃO CRÍTICA 2: Todas contas têm descrição
    # ========================================
    empty_desc_indices = []
    for i, account in enumerate(accounts):
        descricao = account.get("descricao", "")
        if not descricao or not str(descricao).strip():
            empty_desc_indices.append(i)

    if empty_desc_indices:
        sample = empty_desc_indices[:5]  # Mostra até 5 exemplos
        errors.append(
            f"{len(empty_desc_indices)} accounts with empty description "
            f"(indices: {sample}{'...' if len(empty_desc_indices) > 5 else ''})"
        )

    # ========================================
    # VALIDAÇÃO CRÍTICA 3: Saldos numéricos válidos
    # ========================================
    # `float(saldo)` sozinho não serve como validação: NaN e Infinity
    # convertem sem levantar exceção, então passavam como "numéricos válidos"
    # e ainda envenenavam a métrica avg_saldo. `parse_saldo` devolve None para
    # tudo que não é um número finito. Ver REVISAO_QUALIDADE.md §2c.
    invalid_saldo_indices = [
        i
        for i, account in enumerate(accounts)
        if parse_saldo(account.get("saldo", 0)) is None
    ]

    if invalid_saldo_indices:
        sample = invalid_saldo_indices[:5]
        errors.append(
            f"{len(invalid_saldo_indices)} accounts with invalid saldo "
            f"(indices: {sample}{'...' if len(invalid_saldo_indices) > 5 else ''})"
        )

    # ========================================
    # WARNING 1: Nível válido
    # ========================================
    invalid_nivel_indices = []
    for i, account in enumerate(accounts):
        nivel = account.get("nivel")
        if not isinstance(nivel, int) or nivel < 1:
            invalid_nivel_indices.append(i)

    if invalid_nivel_indices:
        sample = invalid_nivel_indices[:5]
        warnings.append(
            f"{len(invalid_nivel_indices)} accounts with invalid nivel "
            f"(expected int >= 1, indices: {sample}{'...' if len(invalid_nivel_indices) > 5 else ''})"
        )

    # ========================================
    # WARNING 2: Código formato hierárquico (se presente)
    # ========================================
    import re

    invalid_codigo_indices = []
    for i, account in enumerate(accounts):
        codigo = account.get("codigo")
        if codigo and codigo is not None:
            # Se código existe, deve ser hierárquico (X.X.X) ou simples (X)
            if not re.match(r"^\d+(\.\d+)*$", str(codigo).strip()):
                invalid_codigo_indices.append(i)

    if invalid_codigo_indices:
        sample = invalid_codigo_indices[:3]
        warnings.append(
            f"{len(invalid_codigo_indices)} accounts with non-hierarchical codigo "
            f"(expected format: X.X.X, indices: {sample})"
        )

    # ========================================
    # Calcular Métricas
    # ========================================
    with_codigo = sum(
        1 for a in accounts if a.get("codigo") and str(a.get("codigo")).strip()
    )
    with_descricao = sum(
        1 for a in accounts if a.get("descricao") and str(a.get("descricao")).strip()
    )
    valid_saldo = total_accounts - len(invalid_saldo_indices)

    # Saldo médio (apenas dos válidos)
    saldos_validos = [
        parse_saldo(a.get("saldo", 0))
        for i, a in enumerate(accounts)
        if i not in invalid_saldo_indices
    ]
    avg_saldo = sum(saldos_validos) / len(saldos_validos) if saldos_validos else 0

    metrics = {
        "total_accounts": total_accounts,
        "with_codigo": with_codigo,
        "with_descricao": with_descricao,
        "valid_saldo": valid_saldo,
        "avg_saldo": round(avg_saldo, 2),
        "empty_descriptions": len(empty_desc_indices),
        "invalid_saldos": len(invalid_saldo_indices),
        "invalid_niveis": len(invalid_nivel_indices),
        "invalid_codigos": len(invalid_codigo_indices),
    }

    # ========================================
    # Retornar Resultado
    # ========================================
    return ExportValidationResult(
        valid=len(errors) == 0, errors=errors, warnings=warnings, metrics=metrics
    )


def validate_matched_accounts(accounts: list[dict[str, Any]]) -> ExportValidationResult:
    """
    Valida contas APÓS matching, ANTES do export.

    Garante que processo de matching produziu dados consistentes.

    Validações Críticas:
    - Match scores entre 0.0 e 1.0
    - Consistência match_codigo <-> match_descricao
    - Contas analíticas NÃO estão matched

    Args:
        accounts: Lista de contas com campos de matching populados

    Returns:
        ExportValidationResult
    """
    errors = []
    warnings = []

    if not accounts:
        errors.append("No accounts to validate (empty list)")
        return ExportValidationResult(
            valid=False, errors=errors, warnings=warnings, metrics={}
        )

    # ========================================
    # VALIDAÇÃO 1: Match scores válidos
    # ========================================
    invalid_score_indices = []
    for i, account in enumerate(accounts):
        score = account.get("match_score", 0.0)
        try:
            score_float = float(score)
            if not (0.0 <= score_float <= 1.0):
                invalid_score_indices.append(i)
        except (ValueError, TypeError):
            invalid_score_indices.append(i)

    if invalid_score_indices:
        sample = invalid_score_indices[:5]
        errors.append(
            f"{len(invalid_score_indices)} accounts with invalid match_score "
            f"(expected 0.0-1.0, indices: {sample})"
        )

    # ========================================
    # VALIDAÇÃO 2: Consistência match_codigo <-> match_descricao
    # ========================================
    inconsistent_indices = []
    for i, account in enumerate(accounts):
        has_codigo = account.get("match_codigo") is not None
        has_desc = account.get("match_descricao") is not None

        # Se tem código, deve ter descrição (e vice-versa)
        if has_codigo != has_desc:
            inconsistent_indices.append(i)

    if inconsistent_indices:
        sample = inconsistent_indices[:5]
        errors.append(
            f"{len(inconsistent_indices)} accounts with inconsistent match data "
            f"(match_codigo exists but match_descricao doesn't, or vice-versa, indices: {sample})"
        )

    # ========================================
    # WARNING: Contas analíticas matched
    # ========================================
    analytical_matched_indices = []
    for i, account in enumerate(accounts):
        is_analytical = account.get("is_analytical", False)
        has_match = account.get("match_codigo") is not None

        if is_analytical and has_match:
            analytical_matched_indices.append(i)

    if analytical_matched_indices:
        sample = analytical_matched_indices[:5]
        warnings.append(
            f"{len(analytical_matched_indices)} analytical accounts were matched "
            f"(should have match_codigo=NULL, indices: {sample})"
        )

    # ========================================
    # Métricas
    # ========================================
    total = len(accounts)
    matched = sum(1 for a in accounts if a.get("match_codigo"))
    needs_review = sum(1 for a in accounts if a.get("needs_review", False))
    ignored = sum(1 for a in accounts if a.get("ignored", False))
    analytical = sum(1 for a in accounts if a.get("is_analytical", False))
    synthetic = total - analytical

    match_rate = (matched / synthetic * 100) if synthetic > 0 else 0

    metrics = {
        "total_accounts": total,
        "synthetic": synthetic,
        "analytical": analytical,
        "matched": matched,
        "match_rate_%": round(match_rate, 2),
        "needs_review": needs_review,
        "ignored": ignored,
        "invalid_scores": len(invalid_score_indices),
        "inconsistent_matches": len(inconsistent_indices),
        "analytical_matched": len(analytical_matched_indices),
    }

    return ExportValidationResult(
        valid=len(errors) == 0, errors=errors, warnings=warnings, metrics=metrics
    )


__all__ = [
    "ExportValidationResult",
    "validate_matched_accounts",
    "validate_parsed_accounts",
]
