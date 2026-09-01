"""
TXTParser — Parser para arquivos de texto estruturado

Lê arquivos TXT com formatos estruturados (espaços fixos, tabulados, etc).
"""

from __future__ import annotations

import re
from pathlib import Path

from .base_parser import BaseParser, ParseResult


class TXTParser(BaseParser):
    """Parser para arquivos TXT de balanços."""

    def __init__(self, file_path: Path, encoding: str = "utf-8", min_columns: int = 2):
        """
        Args:
            file_path: Caminho do arquivo TXT
            encoding: Codificação do arquivo
            min_columns: Número mínimo de colunas esperadas
        """
        super().__init__(file_path)
        self.encoding = encoding
        self.min_columns = min_columns
        self.lines: list[str] = []
        self._detected_encoding: str | None = None

    def validate(self) -> bool:
        """
        Valida se o arquivo TXT é legível, tentando múltiplos encodings.

        Returns:
            True se válido, False caso contrário
        """
        # Ordem prioritária: latin-1 (Windows-1252) é mais comum em arquivos BR
        encodings_to_try = [
            "latin-1",
            "cp1252",
            "iso-8859-1",
            "windows-1252",
            "utf-8",
            self.encoding,
        ]
        for enc in encodings_to_try:
            try:
                with open(self.file_path, encoding=enc, errors="replace") as f:
                    f.read()
                self._detected_encoding = enc
                return True
            except Exception:
                continue
        return False

    def parse(self) -> ParseResult:
        """
        Parseia o arquivo TXT e extrai as contas.

        Estratégia:
        1. Lê o arquivo linha por linha
        2. Detecta o padrão de estrutura (tab, espaços múltiplos, etc)
        3. Extrai campos de cada linha
        4. Monta lista de contas

        Returns:
            ParseResult com contas extraídas
        """
        if not self.validate():
            raise ValueError(f"TXT inválido: {self.file_path}")

        # Carrega linhas com encoding detectado
        encoding_final = self._detected_encoding or self.encoding
        with open(self.file_path, encoding=encoding_final, errors="replace") as f:
            self.lines = [line.rstrip("\n\r") for line in f.readlines()]

        # Detecta o tipo de separador
        separator_type = self._detect_separator()

        # Extrai contas
        contas = self._extract_contas(separator_type)

        # Metadados
        metadata = self._extract_metadata()
        metadata["encoding"] = self._detected_encoding or self.encoding
        metadata["separator_type"] = separator_type
        metadata["total_linhas"] = len(self.lines)
        metadata["total_contas"] = len(contas)

        return ParseResult(contas=contas, metadata=metadata)

    def _detect_separator(self) -> str:
        """
        Detecta o tipo de separador usado no arquivo.

        Testa: tab, espaços múltiplos (2+), pipe (|), ponto-e-vírgula

        Returns:
            Tipo de separador ("tab", "spaces", "pipe", "semicolon")
        """
        # Pega uma amostra das linhas (ignora vazias)
        sample_lines = [line for line in self.lines[:50] if line.strip()]

        if not sample_lines:
            return "spaces"

        # Conta ocorrências de cada separador
        tab_count = sum(line.count("\t") for line in sample_lines)
        pipe_count = sum(line.count("|") for line in sample_lines)
        semicolon_count = sum(line.count(";") for line in sample_lines)

        # Conta linhas com espaços múltiplos (2+)
        spaces_count = sum(1 for line in sample_lines if "  " in line)

        # Escolhe o mais comum
        counts = {
            "tab": tab_count,
            "pipe": pipe_count,
            "semicolon": semicolon_count,
            "spaces": spaces_count,
        }

        return max(counts, key=counts.get)

    def _split_line(self, line: str, separator_type: str) -> list[str]:
        """
        Divide uma linha com base no tipo de separador.

        Args:
            line: Linha a dividir
            separator_type: Tipo de separador

        Returns:
            Lista de campos
        """
        if separator_type == "tab":
            return line.split("\t")
        elif separator_type == "pipe":
            return [field.strip() for field in line.split("|")]
        elif separator_type == "semicolon":
            return [field.strip() for field in line.split(";")]
        else:  # spaces
            # Divide por 2 ou mais espaços
            return [field.strip() for field in re.split(r"\s{2,}", line)]

    def _extract_contas(self, separator_type: str) -> list[dict[str, any]]:
        """
        Extrai contas do arquivo TXT.

        Args:
            separator_type: Tipo de separador detectado

        Returns:
            Lista de contas
        """
        contas = []
        header_found = False

        # Fallback: formato simples com header conhecido (Codigo\tDescricao\tSaldo\tNatureza)
        if self.lines:
            first = self._split_line(self.lines[0], separator_type)
            header_lower = [h.strip().lower() for h in first]
            if {"codigo", "descricao"}.issubset(set(header_lower)):
                for line in self.lines[1:]:
                    fields = self._split_line(line, separator_type)
                    if not fields or len(fields) < 2:
                        continue
                    conta = {"fonte": self.file_path.name}
                    if len(fields) > 0:
                        conta["codigo"] = fields[0].strip()
                    if len(fields) > 1:
                        conta["descricao"] = fields[1].strip()
                    if len(fields) > 2:
                        conta["saldo"] = self._normalize_saldo(fields[2].strip())
                    if len(fields) > 3:
                        conta["natureza"] = fields[3].strip()
                    if "descricao" in conta or "codigo" in conta:
                        if "descricao" not in conta and "codigo" in conta:
                            conta["descricao"] = conta["codigo"]
                        contas.append(conta)
                return contas

        for line_num, line in enumerate(self.lines):
            # Pula linhas vazias
            if not line.strip():
                continue

            # Pula linhas separadoras (só traços)
            if line.strip().replace("-", "").replace("=", "").strip() == "":
                continue

            # Divide a linha
            fields = self._split_line(line, separator_type)
            fields = [f.strip() for f in fields if f.strip()]  # Remove vazios

            # Procura header (linha com "Classificação" ou "Classifica")
            if not header_found:
                fields_lower = " ".join(fields).lower()
                if "classifica" in fields_lower or "classif" in fields_lower:
                    header_found = True
                    continue

            # Pula linhas até encontrar header
            if not header_found:
                continue

            # Precisa de pelo menos min_columns
            if len(fields) < self.min_columns:
                continue

            # Extrai conta da linha
            try:
                conta = self._extract_conta_from_data_fields(fields)
                if conta:
                    contas.append(conta)
            except Exception:
                # Log error but continue
                continue

        return contas

    def _extract_conta_from_data_fields(
        self, fields: list[str]
    ) -> dict[str, any] | None:
        """
        Extrai uma conta de uma lista de campos de dados.

        Estrutura esperada (7 campos):
        [0] Classificação (ex: "1.1.01.01.001")
        [1] Tp (ex: "A" ou "T")
        [2] Código + Nome (ex: "1 CAIXA" ou "1000 ATIVO")
        [3] Saldo Anterior
        [4] Débitos
        [5] Créditos
        [6] Saldo Atual

        Args:
            fields: Campos da linha de dados

        Returns:
            Dict com dados da conta ou None
        """
        # Precisa ter pelo menos 3 campos (classificação, tp, codigo+nome)
        if len(fields) < 3:
            return None

        conta = {"fonte": self.file_path.name}

        # Campo 0: Classificação (pode ser vazio ou conter ponto)
        classificacao = fields[0].strip()
        if (classificacao and "." in classificacao) or classificacao.isdigit():
            conta["classificacao"] = classificacao

        # Campo 1: Tipo (A=Analítica, T=Totalizadora)
        if len(fields) > 1:
            tp = fields[1].strip()
            if tp in ["A", "T"]:
                conta["tipo"] = tp

        # Campo 2: Código + Nome (precisa separar)
        if len(fields) > 2:
            codigo_nome = fields[2].strip()
            if codigo_nome:
                # Tenta separar código do nome
                # Padrão: "1234 NOME DA CONTA" ou "1 CAIXA"
                parts = codigo_nome.split(None, 1)  # Split no primeiro espaço
                if len(parts) == 2:
                    conta["codigo"] = parts[0]
                    conta["descricao"] = parts[1]
                elif len(parts) == 1:
                    # Só tem código ou só tem nome
                    if parts[0].isdigit():
                        conta["codigo"] = parts[0]
                    else:
                        conta["descricao"] = parts[0]

        # Campos 3-6: Valores financeiros
        if len(fields) > 3:
            saldo_ant = fields[3].strip()
            if saldo_ant:
                conta["saldo_anterior"] = self._normalize_saldo(saldo_ant)

        if len(fields) > 4:
            debitos = fields[4].strip()
            if debitos:
                conta["debitos"] = self._normalize_saldo(debitos)

        if len(fields) > 5:
            creditos = fields[5].strip()
            if creditos:
                conta["creditos"] = self._normalize_saldo(creditos)

        if len(fields) > 6:
            saldo_atual = fields[6].strip()
            if saldo_atual:
                conta["saldo_atual"] = self._normalize_saldo(saldo_atual)

        # Precisa ter pelo menos código ou descrição
        if "codigo" not in conta and "descricao" not in conta:
            return None

        # Se tem código mas não descrição, usa código como descrição
        if "codigo" in conta and "descricao" not in conta:
            conta["descricao"] = conta["codigo"]

        return conta
