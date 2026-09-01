"""
Testes para os parsers de balanços.
"""

import pytest
from pathlib import Path

from src.bp.parsers.base_parser import BaseParser, ParseResult
from src.bp.parsers.csv_parser import CSVParser
from src.bp.parsers.txt_parser import TXTParser
from src.bp.parsers.xls_parser import XlsParser
from src.bp.parsers.dispatcher import ParseyCaller


# Fixtures para arquivos de exemplo
@pytest.fixture
def sample_files_dir():
    """Diretório com arquivos de exemplo."""
    return Path(__file__).parent.parent / "data" / "examples"


@pytest.fixture
def sample_excel(sample_files_dir):
    """Arquivo Excel de exemplo."""
    return sample_files_dir / "balanco_exemplo.xlsx"


@pytest.fixture
def sample_csv(sample_files_dir):
    """Arquivo CSV de exemplo."""
    return sample_files_dir / "balanco_exemplo.csv"


@pytest.fixture
def sample_txt(sample_files_dir):
    """Arquivo TXT de exemplo."""
    return sample_files_dir / "balanco_exemplo.txt"


# Testes do BaseParser
class TestParseResult:
    """Testes da classe ParseResult."""

    def test_create_result(self):
        """Testa criação de ParseResult."""
        contas = [{"descricao": "CAIXA", "saldo": 1000.0}]
        result = ParseResult(contas=contas)

        assert len(result.contas) == 1
        assert result.contas[0]["descricao"] == "CAIXA"
        assert result.metadata == {}

    def test_create_result_with_metadata(self):
        """Testa criação com metadados."""
        contas = [{"descricao": "CAIXA"}]
        metadata = {"fonte": "test.xlsx", "total": 1}
        result = ParseResult(contas=contas, metadata=metadata)

        assert result.metadata["fonte"] == "test.xlsx"
        assert result.metadata["total"] == 1

    def test_repr(self):
        """Testa representação string."""
        contas = [{"a": 1}, {"b": 2}]
        result = ParseResult(contas=contas)

        assert "2 contas" in repr(result)


class TestBaseParser:
    """Testes da classe BaseParser."""

    def test_normalize_saldo_float(self):
        """Testa normalização de saldo com float."""
        # Cria parser com arquivo temporário
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            temp_path = Path(f.name)

        # Cria uma subclasse concreta para testar
        class DummyParser(BaseParser):
            def parse(self):
                return ParseResult(contas=[])

            def validate(self):
                return True

        parser = DummyParser(temp_path)

        assert parser._normalize_saldo(1234.56) == 1234.56
        assert parser._normalize_saldo(0) == 0.0

        # Cleanup
        temp_path.unlink()

    def test_normalize_saldo_string(self):
        """Testa normalização de saldo com string."""
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            temp_path = Path(f.name)

        class DummyParser(BaseParser):
            def parse(self):
                return ParseResult(contas=[])

            def validate(self):
                return True

        parser = DummyParser(temp_path)

        # Formatos brasileiros (ponto=milhar, vírgula=decimal)
        assert parser._normalize_saldo("1.234,56") == 1234.56
        assert parser._normalize_saldo("R$ 1.000,00") == 1000.0
        assert parser._normalize_saldo("10.000,50") == 10000.50

        # Valores inválidos
        assert parser._normalize_saldo("abc") == 0.0
        assert parser._normalize_saldo("") == 0.0
        assert parser._normalize_saldo(None) == 0.0

        temp_path.unlink()


# Testes do dispatcher (ParseyCaller)
class TestParseCaller:
    """Testes do dispatcher de parsers."""

    def test_parse_excel_via_dispatcher(self, sample_excel):
        """Testa parsing de arquivo Excel via dispatcher."""
        if not sample_excel.exists():
            pytest.skip("Arquivo de exemplo não encontrado")

        caller = ParseyCaller(sample_excel)
        accounts = caller.parse()

        assert isinstance(accounts, list)
        assert len(accounts) > 0

        # Verifica primeira conta
        primeira = accounts[0]
        assert "descricao" in primeira
        assert "codigo" in primeira

    def test_read_excel_returns_dataframe(self, sample_excel):
        """Testa que .read() retorna DataFrame."""
        if not sample_excel.exists():
            pytest.skip("Arquivo de exemplo não encontrado")

        caller = ParseyCaller(sample_excel)
        df = caller.read()

        assert df is not None
        assert len(df) > 0


# Testes do CSVParser
class TestCSVParser:
    """Testes do parser CSV."""

    def test_validate_valid_file(self, sample_csv):
        """Testa validação de arquivo CSV válido."""
        if not sample_csv.exists():
            pytest.skip("Arquivo de exemplo não encontrado")

        parser = CSVParser(sample_csv)
        assert parser.validate() is True

    def test_parse_csv(self, sample_csv):
        """Testa parsing de arquivo CSV."""
        if not sample_csv.exists():
            pytest.skip("Arquivo de exemplo não encontrado")

        parser = CSVParser(sample_csv)
        result = parser.parse()

        assert isinstance(result, ParseResult)
        assert len(result.contas) > 0

        # Verifica metadados
        assert "delimiter" in result.metadata
        assert "encoding" in result.metadata

    def test_detect_delimiter(self, sample_csv):
        """Testa detecção de delimitador."""
        if not sample_csv.exists():
            pytest.skip("Arquivo de exemplo não encontrado")

        parser = CSVParser(sample_csv)
        delimiter = parser._detect_delimiter()

        assert delimiter in [",", ";", "\t", "|"]


# Testes do TXTParser
class TestTXTParser:
    """Testes do parser TXT."""

    def test_validate_valid_file(self, sample_txt):
        """Testa validação de arquivo TXT válido."""
        if not sample_txt.exists():
            pytest.skip("Arquivo de exemplo não encontrado")

        parser = TXTParser(sample_txt)
        assert parser.validate() is True

    def test_parse_txt(self, sample_txt):
        """Testa parsing de arquivo TXT."""
        if not sample_txt.exists():
            pytest.skip("Arquivo de exemplo não encontrado")

        parser = TXTParser(sample_txt)
        result = parser.parse()

        assert isinstance(result, ParseResult)
        assert len(result.contas) > 0

        # Verifica metadados
        assert "separator_type" in result.metadata
        assert "encoding" in result.metadata

    def test_detect_separator(self, sample_txt):
        """Testa detecção de separador."""
        if not sample_txt.exists():
            pytest.skip("Arquivo de exemplo não encontrado")

        parser = TXTParser(sample_txt)

        # Carrega linhas
        with open(sample_txt, "r", encoding="utf-8") as f:
            parser.lines = [line.rstrip("\n\r") for line in f.readlines()]

        separator = parser._detect_separator()
        assert separator in ["tab", "spaces", "pipe", "semicolon"]


# Testes de integração - removidos pois parsers têm interfaces diferentes
# (dispatcher retorna lista, BaseParser subclasses retornam ParseResult)
