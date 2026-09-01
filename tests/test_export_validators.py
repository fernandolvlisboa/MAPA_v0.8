"""Test Export Validators

Tests for export_schema.py validation functions.
"""

import pytest
from src.bp.validators import (
    validate_parsed_accounts,
    validate_matched_accounts,
    ExportValidationResult,
)


class TestValidateParsedAccounts:
    """Test validate_parsed_accounts() function"""

    def test_empty_list(self):
        """Empty list should fail validation"""
        result = validate_parsed_accounts([])
        assert not result.valid
        assert "empty list" in result.errors[0].lower()

    def test_valid_accounts(self):
        """Valid accounts should pass"""
        accounts = [
            {"descricao": "Ativo", "saldo": 1000.0, "nivel": 1, "codigo": "1"},
            {"descricao": "Passivo", "saldo": -500.5, "nivel": 1, "codigo": "2"},
        ]
        result = validate_parsed_accounts(accounts)
        assert result.valid
        assert len(result.errors) == 0
        assert result.metrics["total_accounts"] == 2
        assert result.metrics["valid_saldo"] == 2

    def test_empty_description(self):
        """Accounts with empty description should fail"""
        accounts = [
            {"descricao": "", "saldo": 100, "nivel": 1},
            {"descricao": "Valid", "saldo": 200, "nivel": 1},
        ]
        result = validate_parsed_accounts(accounts)
        assert not result.valid
        assert any("empty description" in e.lower() for e in result.errors)
        assert result.metrics["empty_descriptions"] == 1

    def test_invalid_saldo(self):
        """Accounts with non-numeric saldo should fail"""
        accounts = [
            {"descricao": "Test1", "saldo": "invalid", "nivel": 1},
            {"descricao": "Test2", "saldo": None, "nivel": 1},
            {"descricao": "Test3", "saldo": 100, "nivel": 1},
        ]
        result = validate_parsed_accounts(accounts)
        assert not result.valid
        assert any("invalid saldo" in e.lower() for e in result.errors)
        assert result.metrics["invalid_saldos"] == 2

    def test_invalid_nivel_warning(self):
        """Invalid nivel should generate warning, not error"""
        accounts = [
            {"descricao": "Test1", "saldo": 100, "nivel": 0},  # Invalid
            {"descricao": "Test2", "saldo": 200, "nivel": "abc"},  # Invalid
            {"descricao": "Test3", "saldo": 300, "nivel": 1},  # Valid
        ]
        result = validate_parsed_accounts(accounts)
        assert result.valid  # Nivel não bloqueia
        assert len(result.warnings) > 0
        assert any("invalid nivel" in w.lower() for w in result.warnings)

    def test_invalid_codigo_warning(self):
        """Non-hierarchical codigo should generate warning"""
        accounts = [
            {"descricao": "Test1", "saldo": 100, "nivel": 1, "codigo": "1.2.3"},  # OK
            {
                "descricao": "Test2",
                "saldo": 200,
                "nivel": 1,
                "codigo": "ABC",
            },  # Invalid
            {"descricao": "Test3", "saldo": 300, "nivel": 1},  # No codigo (OK)
        ]
        result = validate_parsed_accounts(accounts)
        assert result.valid
        assert any("non-hierarchical codigo" in w.lower() for w in result.warnings)

    def test_metrics_calculation(self):
        """Test that metrics are calculated correctly"""
        accounts = [
            {"descricao": "Test1", "saldo": 100, "nivel": 1, "codigo": "1"},
            {"descricao": "Test2", "saldo": 200, "nivel": 2, "codigo": "1.1"},
            {"descricao": "Test3", "saldo": 300, "nivel": 1},  # No codigo
        ]
        result = validate_parsed_accounts(accounts)
        assert result.valid
        assert result.metrics["total_accounts"] == 3
        assert result.metrics["with_codigo"] == 2
        assert result.metrics["with_descricao"] == 3
        assert result.metrics["valid_saldo"] == 3
        assert result.metrics["avg_saldo"] == 200.0


class TestValidateMatchedAccounts:
    """Test validate_matched_accounts() function"""

    def test_empty_list(self):
        """Empty list should fail"""
        result = validate_matched_accounts([])
        assert not result.valid
        assert "empty list" in result.errors[0].lower()

    def test_valid_matched_accounts(self):
        """Valid matched accounts should pass"""
        accounts = [
            {
                "descricao": "Ativo",
                "saldo": 1000,
                "match_score": 0.95,
                "match_codigo": "1",
                "match_descricao": "ATIVO",
                "is_analytical": False,
            },
            {
                "descricao": "Passivo",
                "saldo": -500,
                "match_score": 0.80,
                "match_codigo": "2",
                "match_descricao": "PASSIVO",
                "is_analytical": False,
            },
        ]
        result = validate_matched_accounts(accounts)
        assert result.valid
        assert result.metrics["matched"] == 2
        assert result.metrics["match_rate_%"] == 100.0

    def test_invalid_match_score(self):
        """Match scores outside 0.0-1.0 should fail"""
        accounts = [
            {"descricao": "Test", "saldo": 100, "match_score": 1.5},  # > 1.0
            {"descricao": "Test2", "saldo": 200, "match_score": -0.1},  # < 0.0
        ]
        result = validate_matched_accounts(accounts)
        assert not result.valid
        assert any("invalid match_score" in e.lower() for e in result.errors)

    def test_inconsistent_match_data(self):
        """match_codigo without match_descricao should fail"""
        accounts = [
            {
                "descricao": "Test",
                "saldo": 100,
                "match_score": 0.8,
                "match_codigo": "1",
                "match_descricao": None,  # Inconsistent
            }
        ]
        result = validate_matched_accounts(accounts)
        assert not result.valid
        assert any("inconsistent match" in e.lower() for e in result.errors)

    def test_analytical_matched_warning(self):
        """Analytical accounts with matches should generate warning"""
        accounts = [
            {
                "descricao": "Analytical",
                "saldo": 100,
                "match_score": 0.9,
                "match_codigo": "1.1.1",
                "match_descricao": "CONTA ANALITICA",
                "is_analytical": True,  # Should not be matched
            },
            {
                "descricao": "Synthetic",
                "saldo": 100,
                "match_score": 0.9,
                "match_codigo": "1",
                "match_descricao": "ATIVO",
                "is_analytical": False,
            },
        ]
        result = validate_matched_accounts(accounts)
        assert result.valid  # Warning, não error
        assert any(
            "analytical accounts were matched" in w.lower() for w in result.warnings
        )

    def test_match_rate_calculation(self):
        """Test match rate calculation excludes analytical"""
        accounts = [
            {
                "descricao": "Synthetic1",
                "saldo": 100,
                "match_codigo": "1",
                "match_descricao": "ATIVO",
                "is_analytical": False,
            },
            {
                "descricao": "Synthetic2",
                "saldo": 200,
                "match_codigo": None,  # Unmatched
                "match_descricao": None,
                "is_analytical": False,
            },
            {
                "descricao": "Analytical",
                "saldo": 50,
                "match_codigo": None,
                "match_descricao": None,
                "is_analytical": True,  # Should NOT count in match_rate
            },
        ]
        result = validate_matched_accounts(accounts)
        assert result.valid
        assert result.metrics["synthetic"] == 2
        assert result.metrics["analytical"] == 1
        assert result.metrics["matched"] == 1
        assert result.metrics["match_rate_%"] == 50.0  # 1/2 synthetic = 50%


class TestExportValidationResult:
    """Test ExportValidationResult dataclass"""

    def test_string_representation_valid(self):
        """Test __str__ for valid result"""
        result = ExportValidationResult(
            valid=True, errors=[], warnings=[], metrics={"total": 10, "matched": 8}
        )
        output = str(result)
        assert "✅ VÁLIDO" in output
        assert "total: 10" in output
        assert "matched: 8" in output

    def test_string_representation_invalid(self):
        """Test __str__ for invalid result with errors"""
        result = ExportValidationResult(
            valid=False,
            errors=["Empty list", "Invalid saldo"],
            warnings=["Missing codigo"],
            metrics={"total": 0},
        )
        output = str(result)
        assert "❌ INVÁLIDO" in output
        assert "Empty list" in output
        assert "Invalid saldo" in output
        assert "Missing codigo" in output
