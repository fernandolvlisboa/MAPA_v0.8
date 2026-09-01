"""
BaseParser — Interface abstrata para parsers de balanços

Define o contrato que todos os parsers devem seguir.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..utils.numero import parse_saldo_ou


class ParseResult:
    """Resultado do parsing de um arquivo."""

    def __init__(self, contas: list[dict[str, Any]], metadata: dict[str, Any] | None = None):
        """
        Args:
            contas: Lista de contas extraídas do arquivo
            metadata: Metadados opcionais (origem, data, empresa, etc)
        """
        self.contas = contas
        self.metadata = metadata or {}

    def __repr__(self):
        return f"<ParseResult: {len(self.contas)} contas>"


class BaseParser(ABC):
    """Classe base abstrata para parsers de balanços."""

    def __init__(self, file_path: Path):
        """
        Args:
            file_path: Caminho do arquivo a ser parseado
        """
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

    @abstractmethod
    def parse(self) -> ParseResult:
        """
        Parseia o arquivo e retorna lista de contas no formato intermediário.

        Formato esperado de cada conta:
        {
            "codigo": str,           # Código da conta (ex: "1.1.1")
            "descricao": str,        # Descrição (ex: "CAIXA")
            "saldo": float,          # Saldo/valor (opcional)
            "natureza": str,         # "Devedora" ou "Credora" (opcional)
            "tipo": str,             # "ATIVO", "PASSIVO", etc (opcional)
            "fonte": str             # Nome do arquivo de origem
        }

        Returns:
            ParseResult com lista de contas e metadata
        """
        pass

    @abstractmethod
    def validate(self) -> bool:
        """
        Valida se o arquivo está no formato esperado.

        Returns:
            True se válido, False caso contrário
        """
        pass

    def _normalize_saldo(self, value: Any) -> float:
        """
        Normaliza um valor para float, com ``0.0`` quando ilegível.

        Delega a ``utils.numero.parse_saldo`` — fonte única do projeto. A
        implementação própria que vivia aqui removia todo ponto como separador
        de milhar (``"1234.56"`` virava ``123456.0``) e não entendia
        parênteses de negativo.

        Prefira ``parse_saldo`` diretamente em código novo: ele distingue
        "ilegível" (``None``) de "conta zerada" (``0.0``), distinção que este
        método necessariamente perde.
        """
        return parse_saldo_ou(value, 0.0)

    def _extract_metadata(self) -> dict[str, Any]:
        """
        Extrai metadados do arquivo (nome, tamanho, data modificação).

        Returns:
            Dict com metadados
        """
        import os
        from datetime import datetime

        stat = os.stat(self.file_path)

        return {
            "fonte": self.file_path.name,
            "caminho": str(self.file_path),
            "tamanho_bytes": stat.st_size,
            "data_modificacao": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
