"""Export Validators — BP System

Valida dados em cada etapa do pipeline antes do export.

Stages:
    1. validate_parsed_accounts()  — Após parse, antes match
    2. validate_matched_accounts() — Após match, antes export
    3. validate_exported_file()    — Após export (TODO)

Usage:
    >>> from bp.validators import validate_parsed_accounts, validate_matched_accounts
    >>> accounts = ParseyCaller(file_path).parse()
    >>> validation = validate_parsed_accounts(accounts)
    >>> if not validation.valid:
    >>>     raise ValueError(f"Parse failed: {validation}")
"""

from .export_schema import (
    ExportValidationResult,
    validate_matched_accounts,
    validate_parsed_accounts,
)

__all__ = [
    "ExportValidationResult",
    "validate_matched_accounts",
    "validate_parsed_accounts",
]
