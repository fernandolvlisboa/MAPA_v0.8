"""
AccountTrainer — Sistema de treinamento isolado e incremental

Sistema que processa balancetes de forma incremental, filtra contas analíticas,
aprende padrões e mantém tracking do que já foi processado.

Features:
- Tracking de arquivos processados (não reprocessa)
- Filtragem automática de níveis analíticos (fornecedor, c/c, etc.)
- Aprendizado incremental de variações de descrição
- Cache isolado do sistema principal
- Estatísticas acumuladas por sessão
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..generators.plano_contas import PlanodeContas
from ..matchers import ContaMatcher
from ..parsers.dispatcher import ParseyCaller
from ..utils.json_store import load_json, save_json
from ..utils.normalizer import normalize
from ..utils.synonyms import is_garbage_description


class AccountTrainer:
    """
    Sistema de treinamento isolado para aprendizado de padrões contábeis.

    Processa balancetes incrementalmente, filtrando apenas contas sintéticas
    (ignorando níveis analíticos como fornecedor específico, conta corrente).
    """

    def __init__(
        self,
        training_dir: str | Path = "src/bp/training",
        plano_path: str | Path = "data/plano_referencial.json",
        samples_dir: str | Path | None = None,
    ):
        """
        Args:
            training_dir: Diretório onde ficam os JSON de estado do treino
                (variações aprendidas, cache, estatísticas).
            plano_path: Caminho para o plano de contas ALVO do matching.
                Default: ``data/plano_referencial.json`` (Plano Referencial RFB
                PJ em Geral = L100A + L300A), esquema de código único e
                consistente. NÃO use o master ``plano_contas.json`` aqui: ele
                contém todos os blocos da ECF (financeiras L100B, seguradoras
                L100C, apuração fiscal M300/M350, ...) com esquemas de código
                incompatíveis, o que faz ~69% dos auto-matches caírem no
                namespace errado. Ver ``plano_referencial.py``.
            samples_dir: Onde estão os balancetes. Default: ``MAPA_SAMPLES_DIR``
                ou ``data/samples/`` (ver ``docs/DADOS_PRIVADOS.md``). Aceitar
                por parâmetro permite testes isolados apontarem para tmpdir.
        """
        from ..utils.paths import samples_dir as _samples_dir_default

        self.training_dir = Path(training_dir)
        self.dfs_dir = Path(samples_dir) if samples_dir else _samples_dir_default()

        # Garante que diretório existe
        self.dfs_dir.mkdir(parents=True, exist_ok=True)

        # Arquivos de controle
        self.processed_files_path = self.training_dir / "processed_files.json"
        self.training_cache_path = self.training_dir / "training_cache.json"
        self.learned_patterns_path = self.training_dir / "learned_patterns.json"
        self.variations_path = self.training_dir / "account_variations.json"
        self.stats_path = self.training_dir / "training_stats.json"
        self.ignore_path = self.training_dir / "training_ignore.json"

        # Load components
        self.plano = PlanodeContas(Path(plano_path))
        self.matcher = ContaMatcher(
            self.plano,
            cache_path=str(self.training_cache_path),
            auto_accept_threshold=0.85,
            requery_threshold=0.60,
        )

        # Tracking
        self.processed_files = self._load_processed_files()
        self.variations = self._load_variations()
        self.learned_patterns = self._load_learned_patterns()
        self.stats = self._load_stats()
        self.ignored_descriptions = self._load_ignore_list()

    # =========================================================================
    # Tracking de Arquivos
    # =========================================================================

    def _load_processed_files(self) -> set[str]:
        """Carrega lista de arquivos já processados."""
        return set(load_json(self.processed_files_path, {}).get("files", []))

    def _save_processed_files(self):
        """Salva lista de arquivos processados."""
        save_json(
            self.processed_files_path,
            {
                "files": sorted(self.processed_files),
                "last_update": datetime.now().isoformat(),
                "total_processed": len(self.processed_files),
            },
        )

    def get_new_files(self) -> list[Path]:
        """
        Retorna apenas arquivos NOVOS (não processados).

        Returns:
            Lista de Paths de arquivos CSV/Excel não processados
        """
        all_files = []

        # Extensões suportadas vêm do dispatcher (fonte única) — evita drift.
        for ext in ParseyCaller.SUPPORTED_EXTENSIONS:
            all_files.extend(self.dfs_dir.glob(f"*{ext}"))

        # Filtra apenas novos
        new_files = [f for f in all_files if f.name not in self.processed_files]

        return sorted(new_files)

    def list_processed_files(self) -> list[str]:
        """Retorna lista de arquivos já processados."""
        return sorted(self.processed_files)

    # =========================================================================
    # Detecção de Níveis Analítico vs Sintético
    # =========================================================================

    # Padrões de descrição analítica (compilados 1x no import).
    _ANALYTICAL_RE = re.compile(
        r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"       # CNPJ
        r"|LTDA\.?|S/A|S\.A\.|EIRELI|ME\b|EPP\b"  # Tipo societário
        r"|AG[ÊE]NCIA\s*\d+"                       # Agência bancária
        r"|C/C\s*\d+|CONTA\s*CORRENTE\s*\d+"       # Conta corrente
        r"|CPF\s*\d{3}\.\d{3}\.\d{3}-\d{2}"       # CPF
        r"|BANCO\s+\d{3}"                          # Código de banco
    )

    @staticmethod
    def _collect_parent_codes(all_accounts: list[dict[str, Any]]) -> set[str]:
        """
        Retorna o conjunto de códigos que aparecem como PAI de alguma outra
        conta (i.e., prefixo hierárquico presente no dataset). Base da
        classificação sintético/analítico em O(1) por conta.
        """
        parents: set[str] = set()
        for c in all_accounts:
            code = str(c.get("codigo", ""))
            # Sobe pela hierarquia adicionando todos os ancestrais possíveis.
            while "." in code:
                code = code.rsplit(".", 1)[0]
                parents.add(code)
        return parents

    def is_analytical_level(
        self,
        conta: dict[str, Any],
        all_accounts: list[dict[str, Any]],
        parent_codes: set[str] | None = None,
    ) -> bool:
        """
        Detecta se conta é nível analítico (muito detalhado).

        Níveis analíticos contêm detalhes específicos como razão social de
        fornecedor/cliente, C/C bancária, CNPJ/CPF, ou nível hierárquico > 5.

        Args:
            conta: Dicionário da conta.
            all_accounts: Lista completa de contas. Só é iterada quando
                ``parent_codes`` não é fornecido (fallback O(n²), preservado
                para não quebrar chamadores externos).
            parent_codes: Conjunto pré-computado dos códigos que são pais de
                outra conta (via ``_collect_parent_codes``). Torna a checagem
                de "tem filhos?" O(1). Sempre passe isto em loops sobre o
                dataset todo (``get_synthetic_accounts`` faz isso).

        Returns:
            True se é analítico (ignorar), False se é sintético (usar).
        """
        # 1. Tem filhos? -> sintético
        codigo = str(conta.get("codigo", ""))
        if parent_codes is None:
            # Backwards-compat: caminho O(n²) para chamadores externos.
            parent_codes = self._collect_parent_codes(all_accounts)
        if codigo in parent_codes:
            return False

        # 2. Padrões analíticos na descrição
        if self._ANALYTICAL_RE.search(conta.get("descricao", "").upper()):
            return True

        # 3. Nível muito profundo (> 5) ou código muito específico (> 6 partes)
        if conta.get("nivel", 0) > 5:
            return True
        if codigo and codigo.count(".") >= 6:
            return True

        return False

    def get_synthetic_accounts(
        self, all_accounts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Retorna apenas contas sintéticas (para treino).

        Args:
            all_accounts: Lista completa de contas.

        Returns:
            Lista filtrada de contas sintéticas.
        """
        # Pré-computa o conjunto de "códigos pais" (contas com filhos) UMA vez
        # e reusa a cada conta -> O(n) total (era O(n²) por 'any(...)' aninhado).
        parent_codes = self._collect_parent_codes(all_accounts)
        return [
            conta
            for conta in all_accounts
            if not self.is_analytical_level(conta, all_accounts, parent_codes)
        ]

    # =========================================================================
    # Processamento de Arquivos
    # =========================================================================

    def process_file(self, file_path: Path) -> dict[str, Any]:
        """
        Processa um arquivo de balancete.

        Args:
            file_path: Path para CSV ou Excel

        Returns:
            Dicionário com resultados do processamento
        """
        print(f"  Processando: {file_path.name}")

        # Parsing via dispatcher — retorna lista de contas extraídas
        try:
            accounts = ParseyCaller(file_path).parse()
        except Exception as e:
            print(f"    ❌ Erro ao parsear: {e}")
            return {
                "file": file_path.name,
                "error": str(e),
                "total_accounts": 0,
                "synthetic_accounts": 0,
                "matched": 0,
                "needs_review": 0,
                "results": [],
            }

        # Filtra apenas contas sintéticas
        synthetic = self.get_synthetic_accounts(accounts)

        print(
            f"    Total: {len(accounts)} | Sintéticas: {len(synthetic)} | "
            f"Analíticas filtradas: {len(accounts) - len(synthetic)}"
        )

        # Realiza matching
        results = []
        for conta in synthetic:
            descricao = conta.get("descricao", "")
            if not descricao:
                continue
            # Descarta linhas-lixo (descrições numéricas/vazias: totais e
            # colunas desalinhadas). Não entram no matching nem contam revisão.
            if is_garbage_description(descricao):
                continue
            # Ignora permanentemente se estiver na lista de ignorados
            if normalize(descricao) in self.ignored_descriptions:
                continue

            match_result = self.matcher.match(
                descricao, codigo_origem=conta.get("codigo")
            )

            results.append(
                {
                    "original": descricao,
                    "codigo_original": conta.get("codigo", ""),
                    "match_codigo": (
                        match_result.decision.codigo if match_result.decision else None
                    ),
                    "match_descricao": (
                        match_result.decision.descricao
                        if match_result.decision
                        else None
                    ),
                    "score": (
                        match_result.decision.score if match_result.decision else 0
                    ),
                    "source": (
                        match_result.decision.source if match_result.decision else None
                    ),
                    "needs_review": match_result.needs_review,
                }
            )

        return {
            "file": file_path.name,
            "total_accounts": len(accounts),
            "synthetic_accounts": len(synthetic),
            "analytical_filtered": len(accounts) - len(synthetic),
            "matched": sum(1 for r in results if r["match_codigo"]),
            "needs_review": sum(1 for r in results if r["needs_review"]),
            "results": results,
        }

    # =========================================================================
    # Aprendizado de Padrões
    # =========================================================================

    def _load_variations(self) -> dict[str, Any]:
        """Carrega variações aprendidas."""
        return load_json(self.variations_path, {})

    def _save_variations(self):
        """Salva variações aprendidas."""
        save_json(self.variations_path, self.variations)

    def _load_learned_patterns(self) -> dict[str, Any]:
        """Carrega padrões aprendidos."""
        return load_json(
            self.learned_patterns_path,
            {"synonyms": {}, "abbreviations": {}, "common_terms": []},
        )

    def _save_learned_patterns(self):
        """Salva padrões aprendidos."""
        save_json(self.learned_patterns_path, self.learned_patterns)

    def learn_from_results(self, results: list[dict[str, Any]]):
        """
        Aprende variações de descrição dos resultados.

        Args:
            results: Lista de resultados de matching
        """
        for item in results:
            if not item["match_codigo"] or item["needs_review"]:
                continue

            codigo = item["match_codigo"]
            descricao = item["original"]
            normalized = normalize(descricao)

            # Registra variação
            if codigo not in self.variations:
                self.variations[codigo] = {"variations": [], "frequency": 0}

            if normalized not in self.variations[codigo]["variations"]:
                self.variations[codigo]["variations"].append(normalized)

            self.variations[codigo]["frequency"] += 1

            # Aprende padrões de descrição
            self._learn_description_patterns(descricao, item["match_descricao"])

    def _learn_description_patterns(
        self, original: str, matched: str | None
    ) -> None:
        """
        Aprende padrões como sinônimos e abreviações.

        Args:
            original: Descrição original do balancete
            matched: Descrição mapeada do plano de contas
        """
        if not matched:
            return

        # Extrai termos
        original_terms = set(normalize(original).split())
        matched_terms = set(normalize(matched).split())

        # Identifica sinônimos potenciais (termos diferentes que mapeiam para mesma conta)
        # Ex: "banco" ↔ "bancos", "disponibilidade" ↔ "caixa"
        diff_terms = original_terms - matched_terms

        for term in diff_terms:
            if len(term) >= 4:  # Ignora termos muito curtos
                if term not in self.learned_patterns["synonyms"]:
                    self.learned_patterns["synonyms"][term] = []

                for matched_term in matched_terms:
                    if (
                        matched_term not in self.learned_patterns["synonyms"][term]
                        and len(matched_term) >= 4
                    ):
                        self.learned_patterns["synonyms"][term].append(matched_term)

    # =========================================================================
    # Estatísticas
    # =========================================================================

    def _load_stats(self) -> dict[str, Any]:
        """Carrega estatísticas."""
        return load_json(
            self.stats_path,
            {
                "total_files": 0,
                "total_accounts": 0,
                "total_synthetic": 0,
                "total_analytical_filtered": 0,
                "total_matched": 0,
                "total_needs_review": 0,
                "sessions": [],
                "total_ignored": 0,
            },
        )

    def _save_stats(self):
        """Salva estatísticas."""
        save_json(self.stats_path, self.stats)

    def get_stats_summary(self) -> dict[str, Any]:
        """Retorna resumo das estatísticas."""
        total_synthetic = self.stats.get("total_synthetic", 0)
        total_matched = self.stats.get("total_matched", 0)

        match_rate = (
            (total_matched / total_synthetic * 100) if total_synthetic > 0 else 0
        )

        return {
            "total_files": self.stats.get("total_files", 0),
            "total_accounts": self.stats.get("total_accounts", 0),
            "total_synthetic": total_synthetic,
            "total_analytical_filtered": self.stats.get("total_analytical_filtered", 0),
            "total_matched": total_matched,
            "total_needs_review": self.stats.get("total_needs_review", 0),
            "total_ignored": self.stats.get("total_ignored", 0),
            "match_rate": match_rate,
            "sessions_count": len(self.stats.get("sessions", [])),
            "learned_variations": len(self.variations),
        }

    # =========================================================================
    # Ignore list (descrições ruidosas que não devem entrar no dicionário)
    # =========================================================================

    def _load_ignore_list(self) -> set:
        return set(load_json(self.ignore_path, {}).get("ignored", []))

    def _save_ignore_list(self):
        save_json(
            self.ignore_path, {"ignored": sorted(self.ignored_descriptions)}
        )

    def add_to_ignore(self, descricao: str):
        norm = normalize(descricao)
        if norm not in self.ignored_descriptions:
            self.ignored_descriptions.add(norm)
            self._save_ignore_list()

    # =========================================================================
    # Treinamento Principal
    # =========================================================================

    def train(self, verbose: bool = True) -> dict[str, Any]:
        """
        Executa treinamento incremental.

        Processa apenas arquivos novos em data/samples/, aprende padrões
        e atualiza todos os arquivos de controle.

        Args:
            verbose: Se True, imprime progresso

        Returns:
            Dicionário com resultados do treinamento
        """
        if verbose:
            print("=" * 80)
            print("SISTEMA DE TREINAMENTO — Aprendizado de Padrões")
            print("=" * 80)

        # 1. Identifica arquivos novos
        new_files = self.get_new_files()

        if not new_files:
            if verbose:
                print("\n✓ Nenhum arquivo novo encontrado")
                print(f"  Total processados: {len(self.processed_files)}")
                print(f"  Adicione balancetes em: {self.dfs_dir}")
            return {
                "new_files": 0,
                "processed": 0,
                "message": "Nenhum arquivo novo",
            }

        if verbose:
            print(f"\n[1] Arquivos novos encontrados: {len(new_files)}")
            for f in new_files:
                print(f"  • {f.name}")

        # 2. Processa cada arquivo
        if verbose:
            print("\n[2] Processando arquivos...")

        session_results = []

        for file_path in new_files:
            try:
                result = self.process_file(file_path)

                if "error" not in result:
                    session_results.append(result)

                    # Aprende com resultados
                    self.learn_from_results(result["results"])

                    # Marca como processado
                    self.processed_files.add(file_path.name)

            except Exception as e:
                if verbose:
                    print(f"    ❌ Erro ao processar {file_path.name}: {e}")

        # 3. Atualiza estatísticas
        if verbose:
            print("\n[3] Atualizando estatísticas...")

        total_accounts = sum(r["total_accounts"] for r in session_results)
        total_synthetic = sum(r["synthetic_accounts"] for r in session_results)
        total_analytical = sum(r["analytical_filtered"] for r in session_results)
        total_matched = sum(r["matched"] for r in session_results)
        total_needs_review = sum(r["needs_review"] for r in session_results)

        self.stats["total_files"] += len(session_results)
        self.stats["total_accounts"] += total_accounts
        self.stats["total_synthetic"] += total_synthetic
        self.stats["total_analytical_filtered"] += total_analytical
        self.stats["total_matched"] += total_matched
        self.stats["total_needs_review"] += total_needs_review

        self.stats["sessions"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "files_processed": len(session_results),
                "accounts": total_accounts,
                "synthetic": total_synthetic,
                "analytical_filtered": total_analytical,
                "matched": total_matched,
                "needs_review": total_needs_review,
                "ignored": len(self.ignored_descriptions),
            }
        )

        # 4. Salva tudo
        if verbose:
            print("\n[4] Salvando resultados...")

        self._save_processed_files()
        self._save_variations()
        self._save_learned_patterns()
        self._save_stats()
        self.matcher.cache._save()  # Salva cache de treino

        # 5. Relatório
        if verbose:
            self._print_report(
                len(session_results),
                total_accounts,
                total_synthetic,
                total_analytical,
                total_matched,
                total_needs_review,
            )

        return {
            "new_files": len(new_files),
            "processed": len(session_results),
            "total_accounts": total_accounts,
            "synthetic_accounts": total_synthetic,
            "analytical_filtered": total_analytical,
            "matched": total_matched,
            "needs_review": total_needs_review,
            "match_rate": (
                (total_matched / total_synthetic * 100) if total_synthetic > 0 else 0
            ),
        }

    def _print_report(
        self,
        files_count: int,
        total_accounts: int,
        total_synthetic: int,
        total_analytical: int,
        total_matched: int,
        total_needs_review: int,
    ):
        """Imprime relatório formatado."""
        print("\n" + "=" * 80)
        print("RELATÓRIO DE TREINAMENTO")
        print("=" * 80)
        print(f"Arquivos processados: {files_count}")
        print(f"Contas totais: {total_accounts}")
        print(f"Contas sintéticas: {total_synthetic}")
        print(f"Contas analíticas filtradas: {total_analytical}")

        if total_synthetic > 0:
            match_pct = (total_matched / total_synthetic) * 100
            review_pct = (total_needs_review / total_synthetic) * 100
            print(f"Matched: {total_matched} ({match_pct:.1f}%)")
            print(f"Precisam revisão: {total_needs_review} ({review_pct:.1f}%)")
        if self.ignored_descriptions:
            print(f"Ignorados permanentes: {len(self.ignored_descriptions)} descrições")

        print(f"\nVariações aprendidas: {len(self.variations)} códigos")
        print(
            f"Sinônimos identificados: {len(self.learned_patterns.get('synonyms', {}))}"
        )
        print(f"Total acumulado: {self.stats['total_files']} arquivos processados")
        print("=" * 80)

    # =========================================================================
    # Utilitários
    # =========================================================================

    def export_report(self, output_path: str | Path) -> None:
        """
        Exporta relatório completo em Markdown.

        Args:
            output_path: Caminho para arquivo .md
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Relatório de Treinamento\n\n")

            # Estatísticas gerais
            stats = self.get_stats_summary()
            f.write("## Estatísticas Gerais\n\n")
            f.write(f"- **Total de arquivos:** {stats['total_files']}\n")
            f.write(f"- **Total de contas:** {stats['total_accounts']}\n")
            f.write(f"- **Contas sintéticas:** {stats['total_synthetic']}\n")
            f.write(
                f"- **Contas analíticas filtradas:** {stats['total_analytical_filtered']}\n"
            )
            f.write(f"- **Matched:** {stats['total_matched']}\n")
            f.write(f"- **Precisam revisão:** {stats['total_needs_review']}\n")
            f.write(f"- **Taxa de matching:** {stats['match_rate']:.1f}%\n")
            f.write(f"- **Sessões de treino:** {stats['sessions_count']}\n\n")

            # Variações aprendidas (top 20)
            f.write("## Top 20 Variações Aprendidas\n\n")
            f.write("| Código | Variações | Frequência |\n")
            f.write("|--------|-----------|------------|\n")

            sorted_vars = sorted(
                self.variations.items(),
                key=lambda x: x[1]["frequency"],
                reverse=True,
            )

            for codigo, data in sorted_vars[:20]:
                vars_str = ", ".join(data["variations"][:3])
                if len(data["variations"]) > 3:
                    vars_str += f" (+{len(data['variations']) - 3} mais)"
                f.write(f"| {codigo} | {vars_str} | {data['frequency']} |\n")

            f.write("\n")

            # Arquivos processados
            f.write("## Arquivos Processados\n\n")
            for filename in sorted(self.processed_files):
                f.write(f"- {filename}\n")

        print(f"✓ Relatório exportado: {output_path}")

    def reset(self):
        """
        Reseta todo o sistema de treinamento.

        CUIDADO: Remove todos os dados aprendidos!
        """
        # Limpa tracking
        self.processed_files.clear()
        self.variations.clear()
        self.learned_patterns = {
            "synonyms": {},
            "abbreviations": {},
            "common_terms": [],
        }
        self.stats = {
            "total_files": 0,
            "total_accounts": 0,
            "total_synthetic": 0,
            "total_analytical_filtered": 0,
            "total_matched": 0,
            "total_needs_review": 0,
            "sessions": [],
            "total_ignored": 0,
        }

        # Salva estado limpo
        self._save_processed_files()
        self._save_variations()
        self._save_learned_patterns()
        self._save_stats()

        # Limpa cache
        self.matcher.cache.clear()
        self.ignored_descriptions.clear()
        self._save_ignore_list()

        print("✓ Sistema de treinamento resetado")
