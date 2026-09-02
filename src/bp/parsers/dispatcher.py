from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..utils.numero import parse_saldo
from .csv_parser import CSVParser
from .excel_parser import ExcelParser
from .registro import normalizar_registros
from .result import ParserResult
from .xls_parser import XlsParser

try:
    from .txt_parser import TXTParser
except Exception:
    TXTParser = None  # type: ignore

try:
    from .pdf_balance_parser import PDFBalanceParser
except Exception:
    PDFBalanceParser = None  # type: ignore


class ParseyCaller:
    # Extensões que este dispatcher sabe rotear. Fonte única — o trainer
    # importa daqui para descobrir arquivos, evitando drift entre este arquivo
    # e a descoberta de balancetes.
    SUPPORTED_EXTENSIONS: tuple[str, ...] = (".csv", ".xlsx", ".xls", ".pdf", ".txt")

    def __init__(self, file_path: str | Path, aba: str | None = None):
        self.file_path = Path(file_path)
        self.df: pd.DataFrame | None = None  # Permite injetar DataFrame diretamente
        #: Aba a usar. ``None`` deixa a escolha automática agir; com nome
        #: explícito, a escolha é do analista e nada a sobrepõe — numa pasta
        #: de trabalho com vinte abas, só ele sabe qual é o balancete.
        self.aba = aba

    def read(self) -> pd.DataFrame | None:
        suffix = self.file_path.suffix.lower()
        try:
            # CSV v2.0 usa parser especializado; read() não aplicável
            if suffix == ".xls":
                # Use XlsParser for legacy .xls files (COM automation)
                return XlsParser(self.file_path).read()
            if suffix == ".xlsx":
                # Use ExcelParser for modern .xlsx files
                return ExcelParser(self.file_path).read()
            if suffix == ".txt" and TXTParser is not None:
                return TXTParser(self.file_path).read()
            # Fallbacks
            return ExcelParser(self.file_path).read()
        except Exception:
            return None

    def parse(
        self, job_id: str | None = None, correlation_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Parse file into list of account dictionaries.

        DESCRIPTION-FIRST STRATEGY:
        - Description is PRIMARY (universal, standardized across companies)
        - Code is SECONDARY (company-specific, may not exist)
        - Saldo is for validation

        This approach works for ALL file structures:
        - Hierarchical codes (RBM: 1.1.1.01)
        - Flat codes (Real Life: just descriptions)
        - Combined columns (Conta: code + description)
        """
        suffix = self.file_path.suffix.lower()

        # CSV: delega para CSVParser v2.0 e retorna contas diretamente
        if suffix == ".csv":
            try:
                csvp = CSVParser(self.file_path)
                if not csvp.validate():
                    return []
                contas = normalizar_registros(csvp.parse().contas)
            except Exception:
                return []
            # Fallback de CONTEÚDO: o CSVParser escolhe as colunas pelo NOME do
            # cabeçalho, e erra quando o balancete tem tanto "CONTA" (numeração
            # de linha) quanto "CLASSIFICAÇÃO" (o código de verdade): casa
            # "conta" e toma a numeração por código E descrição, com saldo
            # vazio. Quando o resultado não tem árvore, relê a grade e deixa o
            # extrator por conteúdo (o mesmo do Excel) escolher as colunas pelo
            # que elas contêm. Puro fallback: só quando não há árvore, e só se
            # a releitura melhorar. Ver §28.
            from ..validators.hierarquia import conferir_hierarquia

            if not conferir_hierarquia(contas).tem_hierarquia:
                alternativa = self._csv_por_conteudo()
                if alternativa is not None:
                    return alternativa
            return contas

        # PDF: extração por linha de texto (balancetes/DFs nativos). PDFs
        # escaneados (sem texto) retornam vazio — precisam de OCR.
        if suffix == ".pdf":
            if PDFBalanceParser is None:
                return []
            try:
                return normalizar_registros(PDFBalanceParser(self.file_path).parse())
            except Exception:
                return []

        # TXT: layout de largura fixa. Sem este desvio o .txt caía no caminho
        # genérico de DataFrame, que não acha coluna de descrição e devolvia
        # lista vazia — o TXTParser (que extrai 468 contas de um balancete
        # real) nunca era chamado em produção.
        if suffix == ".txt" and TXTParser is not None:
            try:
                return normalizar_registros(TXTParser(self.file_path).parse().contas)
            except Exception:
                return []

        # Usa DataFrame existente se já carregado, senão lê do arquivo
        df = self.df if self.df is not None else self.read()

        # Planilha de trabalho traz o balancete numa aba que não é a primeira.
        # `read()` devolve a primeira aba que passa no portão — e num arquivo
        # cuja aba 0 é "Output Modelo (BP)" isso rende zero conta, com nove
        # abas de balancete logo ao lado. Aqui a escolha passa a ser por
        # RESULTADO: vence a aba de que se extraem mais contas.
        escolhida = self._aba_escolhida(df)
        if escolhida is not None:
            df = escolhida

        if df is None or df.empty:
            return []

        # Um único extrator para todos os formatos tabulares. Antes havia duas
        # implementações (esta e `_parse_accounts_from_df`), com conversão
        # numérica própria cada uma: o trainer via 0.0 onde o exporter via
        # None, para o MESMO arquivo. Ver REVISAO_QUALIDADE.md §3a.
        contas = normalizar_registros(self._parse_accounts_from_df(df))

        # Fallback para balancete INDENTADO (a hierarquia está na coluna da
        # descrição, não num código). Só quando o caminho normal não achou
        # árvore, e só se a reconstrução FECHAR o rollup — pode melhorar, nunca
        # sobrepor uma leitura que já funciona. Ver §27.
        from ..validators.hierarquia import conferir_hierarquia

        if not conferir_hierarquia(contas).tem_hierarquia:
            indentado = self._tentar_indentado()
            if indentado is not None:
                return indentado
        return contas

    def _tentar_indentado(self) -> list[dict[str, Any]] | None:
        """
        Reconstrói um balancete indentado — mas só devolve se o rollup fechar.

        O rollup fechando é a prova de que a numeração por indentação acertou a
        árvore. Sem essa prova, devolve ``None`` e o caminho normal segue: é o
        que impede a heurística de inventar hierarquia onde não há.
        """
        if self.file_path.suffix.lower() not in (".xls", ".xlsx"):
            return None
        from ..validators.hierarquia import conferir_hierarquia
        from .indentado import reconstruir_de_grade

        bruto = self._grade_crua()
        if bruto is None:
            return None

        registros = reconstruir_de_grade(bruto)
        if not registros:
            return None
        registros = normalizar_registros(registros)
        relatorio = conferir_hierarquia(registros)
        if relatorio.rollup_integro:
            return registros
        return None

    def _csv_por_conteudo(self) -> list[dict[str, Any]] | None:
        """
        Relê o CSV como grade e extrai pelo CONTEÚDO das colunas.

        Só melhora: devolve a releitura apenas se ela achar árvore onde o
        CSVParser não achou. Encoding e delimitador vêm do próprio CSVParser,
        que já os detecta.
        """
        from ..validators.hierarquia import conferir_hierarquia

        try:
            csvp = CSVParser(self.file_path)
            csvp.validate()
            enc = csvp._detected_encoding or "utf-8"
            sep = csvp._detect_delimiter()
            bruto = pd.read_csv(
                self.file_path, sep=sep, encoding=enc, engine="python", dtype=str
            )
        except Exception:
            return None

        try:
            contas = normalizar_registros(self._parse_accounts_from_df(bruto))
        except Exception:
            return None
        if conferir_hierarquia(contas).tem_hierarquia:
            return contas
        return None

    def _grade_crua(self) -> pd.DataFrame | None:
        """
        A grade sem cabeçalho (``header=None``), com a indentação preservada.

        A leitura normal aplica um cabeçalho e colapsa a grade; a reconstrução
        por indentação precisa das colunas todas. Roteia por formato, e para
        ``.xls`` segue a MESMA ordem do ``XlsParser``: sibling ``.xlsx`` antes de
        tudo, depois a conversão via LibreOffice/Excel. Sem isso, um ``.xls``
        que é HTML disfarçado (comum nesses exports) não abre com
        ``pd.read_excel`` e o balancete indentado voltaria a cair em
        "SEM HIERARQUIA".
        """
        aba = self.aba or 0

        def _ler(caminho, engine=None) -> pd.DataFrame | None:
            try:
                return pd.read_excel(caminho, sheet_name=aba, header=None, engine=engine)
            except Exception:
                return None

        if self.file_path.suffix.lower() == ".xlsx":
            return _ler(self.file_path)

        # .xls: sibling .xlsx primeiro (rápido e o que os testes usam).
        irmao = self.file_path.with_suffix(".xlsx")
        if irmao.exists():
            grade = _ler(irmao, engine="openpyxl")
            if grade is not None:
                return grade

        # Depois a conversão real (LibreOffice/Excel), como o XlsParser faz.
        from .conversao import convertido_para_xlsx

        try:
            with convertido_para_xlsx(self.file_path) as convertido:
                if convertido is not None:
                    grade = _ler(convertido, engine="openpyxl")
                    if grade is not None:
                        return grade
        except Exception:
            pass

        # Último recurso: .xls que na verdade é xlsx com nome errado.
        return _ler(self.file_path)

    def parse_with_original(
        self, job_id: str | None = None, correlation_id: str | None = None
    ) -> tuple[list[dict[str, Any]], pd.DataFrame | None]:
        """Parse e retorna também o DataFrame original (Contrato V2).

        Não quebra compatibilidade com parse(); apenas adiciona uma API nova
        para suportar a aba "Original" do export.
        """
        df = self.df if self.df is not None else self.read()
        if df is None or df.empty:
            return [], None

        accounts = self._parse_accounts_from_df(df)
        return accounts, df

    def parse_with_result(
        self, job_id: str | None = None, correlation_id: str | None = None
    ) -> ParserResult:
        start = ParserResult.start_timer()
        file_type = self.file_path.suffix.lower().lstrip(".") or "unknown"
        result = ParserResult(
            file_type=file_type,
            success=False,
            metadata={
                "source_path": str(self.file_path),
                "job_id": job_id,
                "correlation_id": correlation_id,
            },
        )

        try:
            df = self.read()
            if df is None or df.empty:
                result.errors.append("No data parsed or unsupported format")
                return result

            accounts = self._parse_accounts_from_df(df)
            result.extracted_records = accounts
            result.rows_count = len(df)
            result.success = len(accounts) > 0

            # Basic warnings
            if not result.success:
                result.warnings.append(
                    "Parsed dataframe has no recognizable account records"
                )

        except Exception as e:
            result.errors.append(str(e))
            result.success = False
        finally:
            result.stop_timer(start)
            with contextlib.suppress(Exception):
                result.checksum = ParserResult.compute_checksum(self.file_path)

        return result

    def _find_description_column(self, df: pd.DataFrame) -> str | None:
        """
        Find description column - PRIORITY 1 (REQUIRED).
        Descriptions are universal/standardized across companies.
        Look for: classificação, descrição, nome da conta, conta.
        Reject columns with hierarchical codes (1.1.1) - those are CODE columns.
        Fallback: First Unnamed column with text content (not codes).
        """
        # Primary candidates: explicit description headers
        # IMPORTANT: Try each candidate individually and validate
        # Don't let _find_column return the first match - we need to validate each
        candidates = [
            "descrição da conta",
            "descricao da conta",
            "descrição",
            "descricao",
            "nome da conta contábil",
            "nome da conta contabil",
            "nome da conta",
            "nome",
            "classificação",  # Last - might have codes
            "classificacao",
            "conta",
            "desc",
        ]

        # Try each candidate and validate
        for candidate in candidates:
            found = self._find_column(df, [candidate])
            if found:
                # Validate: is it REALLY a description column, not a code column?
                # Reject if >50% values are hierarchical codes (1.1, 1.1.1)
                sample = df[found].dropna().astype(str).head(20)
                if len(sample) > 0:
                    hierarchical_count = sum(
                        1 for val in sample if re.match(r"^\d+\.\d+", val.strip())
                    )
                    if hierarchical_count / len(sample) > 0.5:
                        # This is actually a CODE column, not description - try next candidate
                        continue
                    else:
                        return found  # Valid description column

        # No explicit header found - try fallback
        # Fallback: First Unnamed column with predominantly text content
        for col in df.columns:
            if "unnamed" in col.lower():
                # Check if column has text (not numeric codes)
                sample = df[col].dropna().head(20)
                if len(sample) == 0:
                    continue

                # Check if values are text descriptions (not just codes)
                text_count = 0
                for val in sample:
                    val_str = str(val).strip()
                    # Skip hierarchical codes
                    if re.match(r"^\d+\.\d+", val_str):
                        continue
                    # Description: has spaces or length > 10 (not just codes like "1.1.1")
                    if " " in val_str or len(val_str) > 10:
                        text_count += 1

                if text_count / len(sample) > 0.5:  # >50% are text descriptions
                    return col

        return None

    def _find_saldo_column(self, df: pd.DataFrame) -> str | None:
        """
        Find saldo column - PRIORITY 2 (OPTIONAL).
        Look for: saldo anterior, saldo atual, saldo final, saldo, valor.
        Fallback: Last column with numeric values (not hierarchical codes).
        """
        candidates = ["saldo anterior", "saldo atual", "saldo final", "saldo", "valor"]

        found = self._find_column(df, candidates)
        if found:
            return found

        # Fallback: Find columns with numeric values (excluding hierarchical codes)
        def is_numeric_value(val: str) -> bool:
            """True if value is numeric (decimal), not a hierarchical code."""
            val = val.strip()
            # Try to convert to float
            try:
                _ = float(val.replace(",", "."))
                # Additional check: hierarchical codes like 1.1 would be very small
                # Saldo values are usually larger or have more decimal places
                parts = val.replace(",", ".").split(".")
                if len(parts) == 2:
                    # If both parts are <= 4 digits, might be code like 1.1
                    # If first part > 4 digits OR second part > 4 digits, it's a number
                    if len(parts[0]) > 4 or len(parts[1]) > 4:
                        return True
                    # Small values with 2 parts: ambiguous, but probably saldo
                    return True
                return True  # No dot or more than 2 parts: numeric
            except (ValueError, AttributeError):
                return False

        # Check all columns for numeric content
        numeric_columns = []
        for col in df.columns:
            sample = df[col].dropna().astype(str).head(20)
            if len(sample) == 0:
                continue

            numeric_count = sum(1 for val in sample if is_numeric_value(val))
            if numeric_count / len(sample) > 0.7:  # >70% numeric
                numeric_columns.append(col)

        uteis = [c for c in numeric_columns if self._coluna_informativa(df, c)]

        # Return last numeric column (usually the saldo)
        if uteis:
            return uteis[-1]
        if numeric_columns:
            return numeric_columns[-1]

        return None

    #: Fração mínima das linhas que uma coluna precisa preencher para ser saldo.
    #: A aba "Balancetes 2025" do SmartRio termina em duas colunas de sobra: uma
    #: vazia e outra com **3 valores em 825 linhas**. Como o critério era "a
    #: última coluna numérica", era essa que virava saldo — 821 das 824 contas
    #: chegavam com ``saldo=None``. Ver REVISAO_QUALIDADE.md §21.
    COBERTURA_MINIMA_DE_SALDO = 0.2

    @staticmethod
    def _coluna_informativa(df: pd.DataFrame, col: str) -> bool:
        """
        A coluna tem informação de saldo, ou é sobra de planilha?

        Duas formas de não ter: estar quase vazia (as colunas-fantasma à direita
        do último mês) ou ser constante (a aba "Balancetes 2021" do SmartRio
        traz uma coluna auxiliar com ``100`` em todas as linhas — que, sendo a
        última numérica, virava o saldo de **todas** as 513 contas).

        Nenhum balancete real tem um único saldo repetido centenas de vezes.
        """
        if len(df) == 0:
            return False
        valores = df[col].dropna()
        if len(valores) / len(df) < ParseyCaller.COBERTURA_MINIMA_DE_SALDO:
            return False
        if len(valores) >= 10 and valores.astype(str).nunique() <= 1:
            return False
        return True

    #: Código hierárquico com **três ou mais segmentos** ("1.1.1", "2.01.03.05").
    #: É o discriminante: um valor decimal jamais tem dois pontos, então esta
    #: forma separa coluna de código de coluna de saldo sem ambiguidade.
    #: Três ou mais segmentos numéricos separados por ponto. O teto de dígitos
    #: por segmento é alto porque balancete real usa segmento longo: o código
    #: "1.00.00.00.00000000" de três clientes tem um segmento de OITO dígitos,
    #: e com o teto antigo de 6 a coluna inteira deixava de ser reconhecida —
    #: os arquivos rendiam contas e caíam em "SEM HIERARQUIA".
    _TRES_SEGMENTOS_RE = re.compile(r"^\d{1,10}(\.\d{1,10}){2,}$")

    #: Proporção mínima de códigos de 3+ segmentos para uma coluna ser aceita
    #: como coluna de código. Baixa de propósito: em balancete com folhas de
    #: código plano (o "11111" do Trindade), a coluna certa tinha só 29% —
    #: enquanto TODAS as outras tinham 0%. O que decide é a distância entre a
    #: melhor e o resto, não um piso alto.
    _LIMIAR_CODIGO = 0.10

    def _find_codigo_column(self, df: pd.DataFrame) -> str | None:
        """
        Acha a coluna de código hierárquico deixando o **conteúdo** decidir.

        A versão anterior procurava por nome numa lista fixa
        (``["código", "codigo", "cod", "class"]``) e devolvia ``None`` para
        qualquer coisa fora dela. Um balancete real com a coluna chamada
        ``"Conta contábil"`` passava batido — e a consequência era grave, em
        cascata:

        1. sem código, ``codigo = descricao`` (fallback description-first);
        2. ``classe_from_codigo("ALUGUEIS")`` devolve ``None``, então o Plano C
           (restrição por classe contábil) fica **desligado**;
        3. ``conferir_hierarquia`` reporta "SEM HIERARQUIA" e nenhuma
           conferência de rollup acontece;
        4. o matching vira texto puro e casa "Aluguel e Condominio **a pagar**"
           (passivo) com "Condomínio" (despesa) — conta de resultado indo parar
           no balanço, com score 1.0.

        Nome de coluna é dica, não prova. Aqui o nome só ordena a busca; quem
        decide é a presença de códigos de 3+ segmentos, que nenhuma coluna de
        saldo tem. Medido: no balancete que expôs o defeito, a coluna certa
        marcou 29,4% e todas as outras 0,0%; nos balancetes do corpus, a coluna
        certa marca 95-97%.
        """

        def proporcao_hierarquica(col) -> float:
            amostra = df[col].dropna().astype(str).str.strip()
            if len(amostra) == 0:
                return 0.0
            casam = sum(1 for v in amostra if self._TRES_SEGMENTOS_RE.match(v))
            if casam:
                return casam / len(amostra)
            # Código plano de largura fixa ("1", "101", "10101", "10101001"):
            # a árvore está no prefixo, não no ponto. Sem isto, a coluna certa
            # marca 0,0 e o balancete inteiro cai em "SEM HIERARQUIA".
            from ..utils.codigo import detectar_niveis_planos

            if detectar_niveis_planos(list(amostra)):
                planos = sum(1 for v in amostra if v.isdigit())
                return planos / len(amostra)
            return 0.0

        descricao_col = self._find_description_column(df)

        # Ranqueia todas as colunas pelo conteúdo. A de descrição fica fora:
        # ela é o fallback, não pode ser a resposta.
        ranking = sorted(
            (
                (proporcao_hierarquica(col), str(col))
                for col in df.columns
                if col is not None and col != descricao_col
            ),
            reverse=True,
        )
        if not ranking:
            return None

        melhor_proporcao, melhor_nome = ranking[0]
        if melhor_proporcao < self._LIMIAR_CODIGO:
            return None  # nenhuma coluna tem cara de código -> description-first

        # Desempate por nome só quando duas colunas empatam no conteúdo.
        empatadas = [nome for prop, nome in ranking if prop == melhor_proporcao]
        if len(empatadas) > 1:
            for dica in ("classific", "conta", "código", "codigo", "cod", "cta"):
                for nome in empatadas:
                    if dica in nome.lower():
                        return self._coluna_original(df, nome)
        return self._coluna_original(df, melhor_nome)

    #: Código já hierárquico ("1", "1.1", "1.1.1.01.001").
    _E_HIERARQUICO_RE = re.compile(r"^\d+(\.\d+)*$")

    #: Código plano, sem pontos ("11111", "322271").
    _E_PLANO_RE = re.compile(r"^\d+$")

    @classmethod
    def _resolver_codigo_indentado(
        cls, codigo_bruto: str, ultimo_sintetico: str
    ) -> tuple[str, str]:
        """
        Resolve o código de uma linha que pode estar num esquema misto.

        Muito balancete alterna dois esquemas na MESMA coluna: as contas
        sintéticas trazem o código hierárquico alinhado à esquerda
        (``"1.1.1.01.001      "``) e as analíticas trazem um código interno
        plano, **indentado à direita** (``"             11111"``). A filiação
        está na posição, não no prefixo: a analítica pertence à sintética
        imediatamente acima dela.

        Sem esta leitura, cada analítica virava uma **raiz** própria — e como
        os sintéticos também eram raízes, todo valor entrava duas vezes na
        equação contábil. Medido num balancete real: 23,3 milhões de excesso,
        com 132 raízes onde deveria haver 4.

        Devolve ``(codigo_hierarquico, codigo_interno)``. O código interno é
        preservado para rastreio quando difere.
        """
        codigo = codigo_bruto.strip()

        if cls._E_HIERARQUICO_RE.fullmatch(codigo) and "." in codigo:
            return codigo, ""  # já é hierárquico de verdade

        indentado = codigo_bruto.startswith(" ") and codigo_bruto != codigo
        if indentado and cls._E_PLANO_RE.fullmatch(codigo) and ultimo_sintetico:
            # Folha do último sintético: pendura como filha dele.
            return f"{ultimo_sintetico}.{codigo}", codigo

        return codigo, ""

    @staticmethod
    def _coluna_original(df: pd.DataFrame, nome: str):
        """Devolve o rótulo real da coluna (pode não ser str)."""
        for col in df.columns:
            if str(col) == nome:
                return col
        return nome

    # Internal: extracted from previous parse() to keep logic reusable
    #: Acima disso a leitura normal já achou um balancete e a varredura de
    #: abas é desperdício. Balancete real tem centenas de contas; uma aba de
    #: modelo ou resumo rende dezenas.
    _CONTAS_SUFICIENTES = 60

    #: Teto de abas avaliadas. Pasta de trabalho real tem dezenas; ler todas
    #: custa segundos e não melhora a escolha.
    _MAX_ABAS = 12

    #: Linhas de cabeçalho testadas por aba. Balancete real põe empresa,
    #: período e emissão antes da tabela.
    _CABECALHOS_TESTADOS = (0, 1, 2, 3, 4, 5, 6, 7)

    def _aba_escolhida(self, df_atual: pd.DataFrame | None) -> pd.DataFrame | None:
        """
        Decide de qual aba as contas saem, em três degraus.

        1. **Escolha do analista** — ``aba`` explícita manda, e nada a
           sobrepõe. Numa pasta de trabalho de vinte abas, só ele sabe qual é
           o balancete.
        2. **Nome inequívoco** — uma aba chamada exatamente "Balancete" é uma
           declaração do próprio arquivo. Vale mais que qualquer contagem:
           numa pasta real, "Balancete" e "Balancete (2)" rendem 2.275 e 1.869
           contas, e o critério "a maior" escolheria a errada.
        3. **Varredura por resultado** — só quando a leitura normal foi pobre.
           Ler todas as abas custa segundos e o preço apareceria no app.
        """
        if self.aba is not None:
            return self._ler_aba(self.aba)

        nomeada = self._aba_por_nome()
        if nomeada is not None:
            return nomeada

        return self._melhor_aba(df_atual)

    def _aba_por_nome(self) -> pd.DataFrame | None:
        """A aba chamada exatamente "Balancete", quando existe uma só."""
        if self.file_path.suffix.lower() not in (".xlsx", ".xls"):
            return None
        try:
            # `with`: sem fechar, o handle do arquivo fica aberto ate o GC
            # passar. No Windows isso e WinError 32 — "o arquivo ja esta sendo
            # usado por outro processo" — e trava quem tentar mover, renomear
            # ou apagar o balancete depois de processado. Ver §25.
            with pd.ExcelFile(self.file_path) as livro:
                abas = livro.sheet_names
        except Exception:
            return None
        if len(abas) < 2:
            return None  # aba única: não há escolha a fazer
        exatas = [a for a in abas if self._prioridade_do_nome(a) == 3]
        if len(exatas) != 1:
            return None  # nenhuma, ou ambíguo: decide a varredura
        return self._ler_aba(exatas[0])

    def _recortes(self, bruto: pd.DataFrame):
        """Gera os candidatos de (cabeçalho, tabela) de uma aba já lida.

        Recortar em memória, em vez de reabrir o arquivo por linha de
        cabeçalho candidata, é o que torna a varredura de abas viável: um
        arquivo de vinte abas dá vinte leituras, não cento e sessenta.
        """
        for cabecalho in self._CABECALHOS_TESTADOS:
            if cabecalho >= len(bruto) - 1:
                return
            recorte = bruto.iloc[cabecalho + 1 :].reset_index(drop=True)
            recorte.columns = [str(c).strip() for c in bruto.iloc[cabecalho].tolist()]
            yield recorte

    def _contar(self, candidato: pd.DataFrame | None) -> int:
        if candidato is None or candidato.empty:
            return 0
        try:
            return len(self._parse_accounts_from_df(candidato))
        except Exception:
            return 0

    def _pontuar(self, candidato: pd.DataFrame | None) -> tuple[int, int]:
        """
        Quanto um recorte vale como balancete: ``(tem árvore, nº de contas)``.

        A árvore vem **antes** da contagem, e isso importa. Escolhendo só pela
        contagem, um recorte que perde a coluna de código pode vencer outro
        que a mantém — e o balancete inteiro cai em "SEM HIERARQUIA" por uma
        linha de cabeçalho. Aconteceu numa série histórica real: dos sete
        exercícios do mesmo arquivo, dois eram lidos com árvore e cinco sem,
        pela diferença de algumas dezenas de linhas.

        A árvore é a prova de que a leitura está certa (o rollup confere); a
        contagem só desempata entre recortes igualmente estruturados.
        """
        if candidato is None or candidato.empty:
            return (0, 0)
        try:
            contas = self._parse_accounts_from_df(candidato)
        except Exception:
            return (0, 0)
        if not contas:
            return (0, 0)
        from ..validators.hierarquia import conferir_hierarquia

        try:
            # Normalizar ANTES de conferir. É o que faltava: `parse()` só
            # aplica `normalizar_registros` no fim, então a pontuação — que
            # existe justamente para preferir o recorte com árvore — enxergava
            # os códigos crus. Num plano PLANO ("1", "101", "10101") não há
            # ponto nenhum antes da normalização, a árvore marcava 0, e cinco
            # dos sete exercícios de um arquivo de cliente eram rotulados "já
            # padronizado" tendo hierarquia completa. Ver §21.
            arvore = 1 if conferir_hierarquia(normalizar_registros(contas)).tem_hierarquia else 0
        except Exception:
            arvore = 0
        return (arvore, len(contas))

    def _ler_aba(self, nome: str) -> pd.DataFrame | None:
        """Lê uma aba pelo nome, escolhendo a melhor linha de cabeçalho dela."""
        try:
            bruto = pd.read_excel(self.file_path, sheet_name=nome, header=None)
        except Exception:
            return None
        if bruto.empty:
            return None
        melhor, melhor_pontos = None, (0, 0)
        for recorte in self._recortes(bruto):
            pontos = self._pontuar(recorte)
            if pontos > melhor_pontos:
                melhor, melhor_pontos = recorte, pontos
        return melhor

    def _melhor_aba(self, df_atual: pd.DataFrame | None) -> pd.DataFrame | None:
        """
        Entre as abas do arquivo, devolve a que rende mais contas.

        Só age quando há mais de uma aba **e** a leitura atual rende menos que
        outra. Arquivo de aba única — a maioria — sai por aqui na primeira
        linha, sem custo.

        O critério é o número de contas extraídas, não o nome da aba: "Output
        Modelo (BP)" e "Balancete mensal Jun-2026" são igualmente plausíveis
        pelo nome, e só a extração distingue as duas.
        """
        if self.file_path.suffix.lower() not in (".xlsx", ".xls"):
            return None

        # A varredura só vale quando a leitura normal foi pobre. Ler todas as
        # abas de todas as planilhas custa caro e não muda nada num arquivo que
        # já rendeu um balancete inteiro — e o preço apareceria no app do
        # analista, não só na suíte.
        base = self._contar(df_atual)
        if base >= self._CONTAS_SUFICIENTES:
            return None

        try:
            # `with`: sem fechar, o handle do arquivo fica aberto ate o GC
            # passar. No Windows isso e WinError 32 — "o arquivo ja esta sendo
            # usado por outro processo" — e trava quem tentar mover, renomear
            # ou apagar o balancete depois de processado. Ver §25.
            with pd.ExcelFile(self.file_path) as livro:
                abas = livro.sheet_names
        except Exception:
            return None
        if len(abas) < 2:
            return None

        melhor_df, melhor_pontos = df_atual, (0, 0, base)
        for aba in abas[: self._MAX_ABAS]:
            try:
                bruto = pd.read_excel(self.file_path, sheet_name=aba, header=None)
            except Exception:
                continue
            if bruto.empty:
                continue
            # O nome da aba entra como CRITÉRIO DE PRIMEIRA ORDEM. Numa pasta
            # com vinte abas, "Balancete" e "Balancete (2)" rendem 2.275 e
            # 1.869 contas — números próximos, e só o nome diz qual é o
            # balancete de verdade. Contagem sozinha escolheria pelo acaso do
            # tamanho; contagem desempata dentro da mesma prioridade de nome.
            prioridade = self._prioridade_do_nome(aba)
            for candidato in self._recortes(bruto):
                arvore, contas = self._pontuar(candidato)
                pontos = (prioridade, arvore, contas)
                if contas and pontos > melhor_pontos:
                    melhor_df, melhor_pontos = candidato, pontos
        return melhor_df if melhor_pontos > (0, 0, base) else None

    @staticmethod
    def _prioridade_do_nome(aba: str) -> int:
        """Quanto o nome da aba promete um balancete. Maior é melhor."""
        nome = str(aba).strip().lower()
        if nome == "balancete":
            return 3
        if nome.startswith("balancete"):
            return 2
        if "balancete" in nome or "balancetes" in nome:
            return 1
        return 0

    @staticmethod
    def _desduplicar_colunas(df: pd.DataFrame) -> pd.DataFrame:
        """
        Garante rótulos de coluna únicos.

        Todo o caminho tabular indexa por nome (``df[col]``). Com rótulo
        repetido, o pandas devolve um **DataFrame** no lugar de uma Series e a
        primeira operação de texto estoura::

            AttributeError: 'DataFrame' object has no attribute 'str'

        Foi assim que um balancete real derrubou o parser. Planilha de trabalho
        repete cabeçalho o tempo todo (colunas de meses com o mesmo rótulo,
        blocos colados lado a lado), então isto não é caso de borda.

        Renomeia as repetições para ``nome.1``, ``nome.2`` — mesma convenção do
        pandas — preservando a primeira ocorrência intacta, que é a que a
        detecção por nome procura.
        """
        nomes = [str(c) for c in df.columns]
        if len(set(nomes)) == len(nomes):
            return df
        vistos: dict[str, int] = {}
        novos: list[str] = []
        for nome in nomes:
            if nome in vistos:
                vistos[nome] += 1
                novos.append(f"{nome}.{vistos[nome]}")
            else:
                vistos[nome] = 0
                novos.append(nome)
        df = df.copy()
        df.columns = novos
        return df

    def _parse_accounts_from_df(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Extract accounts using description-first strategy:
        PRIORITY 1: Description (REQUIRED) - universal across companies
        PRIORITY 2: Saldo (OPTIONAL) - last numeric column
        PRIORITY 3: Codigo (OPTIONAL) - fallback to description if not found
        """
        df = self._desduplicar_colunas(df)

        # PRIORITY 1: Find description column (REQUIRED)
        descricao_col = self._find_description_column(df)
        if not descricao_col:
            return []  # Cannot parse without descriptions

        # PRIORITY 2: Find movement/saldo columns (OPTIONAL)
        saldo_col = self._find_saldo_column(df)

        # Movement columns (Contrato V2: saldo_anterior, credito, debito, saldo_atual)
        mov_saldo_anterior = self._find_column(df, ["saldo anterior", "saldo ant"])
        mov_credito = self._find_column(df, ["crédito", "credito"])
        mov_debito = self._find_column(df, ["débito", "debito"])
        mov_saldo_atual = self._find_column(df, ["saldo atual", "saldo final"])

        # PRIORITY 3: Find codigo column (OPTIONAL, fallback to description)
        codigo_col = self._find_codigo_column(df)
        if not codigo_col:
            codigo_col = descricao_col  # Fallback: derive codes from descriptions

        accounts: list[dict[str, Any]] = []
        #: Último código hierárquico visto. Balancete que mistura esquemas
        #: (sintéticas "1.1.1.01.001", analíticas "11111" indentadas) expressa
        #: a filiação pela POSIÇÃO, não pelo prefixo. Ver
        #: `_resolver_codigo_indentado`.
        ultimo_sintetico = ""

        for _, row in df.iterrows():
            codigo_interno = ""
            # Extract description (REQUIRED)
            descricao = (
                str(row[descricao_col]).strip() if pd.notna(row[descricao_col]) else ""
            )
            if not descricao:
                continue

            # Skip header rows
            if descricao.lower() in [
                "descricao",
                "descrição",
                "nome",
                "nome da conta",
                "classificação",
                "classificacao",
                "conta",
            ]:
                continue

            # Extract codigo (use description as fallback)
            if codigo_col == descricao_col:
                # Same column: try to extract code from description
                # Pattern: "1.1.1  Description text" or "1.1.1 Description"
                match = re.match(r"^(\d+(?:\.\d+)*)\s{2,}(.*)$", descricao)
                if match:
                    codigo = match.group(1).strip()
                    descricao = match.group(2).strip()
                else:
                    # Try single space split
                    parts = descricao.split(maxsplit=1)
                    if len(parts) >= 2 and re.match(r"^\d+(?:\.\d+)*$", parts[0]):
                        codigo = parts[0].strip()
                        descricao = parts[1].strip()
                    else:
                        # No code pattern: use description as code
                        codigo = descricao
            else:
                # Separate columns
                codigo_bruto = str(row[codigo_col]) if pd.notna(row[codigo_col]) else ""
                codigo = codigo_bruto.strip()
                if not codigo:
                    codigo = descricao  # Fallback
                else:
                    codigo, codigo_interno = self._resolver_codigo_indentado(
                        codigo_bruto, ultimo_sintetico
                    )
                    # Só um código que veio hierárquico DA ORIGEM vira o novo
                    # pai. Um código sintetizado (folha pendurada) não pode —
                    # senão cada folha vira mãe da seguinte e a árvore degenera
                    # numa lista encadeada.
                    if not codigo_interno and "." in codigo:
                        ultimo_sintetico = codigo

            # Skip invalid/header codes
            if codigo.lower() in [
                "débito",
                "debito",
                "crédito",
                "credito",
                "saldo",
                "saldo ant.",
                "codigo",
                "código",
                "conta",
                "classificação",
                "classificacao",
            ]:
                continue

            # Extract saldos (Contrato V2)
            saldo_anterior = (
                parse_saldo(row[mov_saldo_anterior]) if mov_saldo_anterior else None
            )
            credito = parse_saldo(row[mov_credito]) if mov_credito else None
            debito = parse_saldo(row[mov_debito]) if mov_debito else None
            saldo_atual = (
                parse_saldo(row[mov_saldo_atual]) if mov_saldo_atual else None
            )

            # Fallback single saldo
            saldo_single = parse_saldo(row[saldo_col]) if saldo_col else None

            # NIVEL: calculate from code
            nivel = self._calculate_nivel(codigo)

            account = {"codigo": codigo, "descricao": descricao, "nivel": nivel}
            if codigo_interno:
                account["codigo_interno"] = codigo_interno

            # Populate saldo fields according to availability
            if (
                saldo_atual is not None
                or saldo_anterior is not None
                or credito is not None
                or debito is not None
            ):
                # General movement structure
                if saldo_anterior is not None:
                    account["saldo_anterior"] = saldo_anterior
                if credito is not None:
                    account["credito"] = credito
                if debito is not None:
                    account["debito"] = debito
                if saldo_atual is not None:
                    account["saldo_atual"] = saldo_atual
                # Compatibility saldo field mirrors saldo_atual when present
                account["saldo"] = (
                    saldo_atual if saldo_atual is not None else saldo_single
                )
            else:
                # Only single saldo available
                account["saldo"] = saldo_single

            accounts.append(account)

        return accounts

    def _find_column(self, df: pd.DataFrame, patterns: list[str]) -> str | None:
        columns_lower = {
            str(col).strip().lower(): col for col in df.columns if col is not None
        }
        for pattern in patterns:
            p = pattern.strip().lower()
            if p in columns_lower:
                return columns_lower[p]
        for pattern in patterns:
            p = pattern.strip().lower()
            for col_lower, col_original in columns_lower.items():
                if p in col_lower:
                    return col_original
        return None

    def _calculate_nivel(self, codigo: str) -> int:
        codigo = codigo.strip()
        return codigo.count(".") + 1 if "." in codigo else 1
