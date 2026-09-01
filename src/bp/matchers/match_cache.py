"""
MatchCache — Cache persistente de decisões de matching (Fase 4)

Armazena decisões de matching em JSON para:
- Evitar re-processar mesmas queries
- Manter histórico de decisões
- Permitir auditoria e correções
- Acelerar matching repetitivo
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.json_store import load_json, save_json


class MatchCache:
    """
    Cache JSON de decisões de matching.

    Estrutura:
    {
        "query_normalized": {
            "codigo": "1.1.01.01.01",
            "descricao": "Caixa",
            "score": 0.95,
            "confidence": 0.95,
            "timestamp": "2024-01-15T10:30:00",
            "manual": false
        }
    }
    """

    def __init__(self, cache_path: str | Path):
        """
        Args:
            cache_path: Caminho para o arquivo JSON de cache
        """
        self.cache_path = Path(cache_path)
        self.cache: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self):
        """Carrega cache do disco."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache = load_json(self.cache_path, {})

    def _save(self):
        """Salva cache no disco (gravação atômica — ver utils/json_store)."""
        try:
            save_json(self.cache_path, self.cache)
        except OSError as e:
            print(f"Aviso: Erro ao salvar cache em {self.cache_path}: {e}")

    def get(self, query: str) -> dict[str, Any] | None:
        """
        Busca decisão no cache.

        Args:
            query: Query normalizada

        Returns:
            Dict com {codigo, descricao, score, confidence, timestamp, manual}
            ou None se não encontrado
        """
        return self.cache.get(query)

    def save(
        self,
        query: str,
        codigo: str,
        descricao: str,
        score: float,
        confidence: float,
        manual: bool = False,
    ):
        """
        Salva decisão no cache.

        Args:
            query: Query normalizada
            codigo: Código da conta mapeada
            descricao: Descrição da conta mapeada
            score: Score do matching
            confidence: Confiança na decisão
            manual: Se foi decisão manual do usuário
        """
        self.cache[query] = {
            "codigo": codigo,
            "descricao": descricao,
            "score": score,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
            "manual": manual,
        }
        self._save()

    def update(
        self,
        query: str,
        codigo: str,
        descricao: str,
        manual: bool = True,
    ):
        """
        Atualiza decisão existente (geralmente correção manual).

        Args:
            query: Query normalizada
            codigo: Novo código
            descricao: Nova descrição
            manual: Marca como decisão manual
        """
        self.save(query, codigo, descricao, score=1.0, confidence=1.0, manual=manual)

    def delete(self, query: str) -> bool:
        """
        Remove decisão do cache.

        Args:
            query: Query normalizada

        Returns:
            True se removido, False se não existia
        """
        if query in self.cache:
            del self.cache[query]
            self._save()
            return True
        return False

    def clear(self):
        """Limpa todo o cache."""
        self.cache = {}
        self._save()

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do cache."""
        total = len(self.cache)
        manual_count = sum(1 for v in self.cache.values() if v.get("manual", False))

        avg_score = 0.0
        if total > 0:
            avg_score = sum(v.get("score", 0) for v in self.cache.values()) / total

        return {
            "total_entries": total,
            "manual_entries": manual_count,
            "auto_entries": total - manual_count,
            "avg_score": avg_score,
        }

    def export_for_review(self, output_path: str | Path):
        """
        Exporta cache em formato legível para revisão.

        Args:
            output_path: Caminho para o arquivo de saída (JSON ou Markdown)
        """
        output_path = Path(output_path)

        if output_path.suffix == ".md":
            self._export_markdown(output_path)
        else:
            self._export_json(output_path)

    def _export_json(self, output_path: Path):
        """Exporta para JSON formatado."""
        save_json(output_path, self.cache)

    def _export_markdown(self, output_path: Path):
        """Exporta para Markdown com tabela."""
        lines = ["# Cache de Matching\n\n"]

        stats = self.get_stats()
        lines.append(f"**Total:** {stats['total_entries']} decisões\n")
        lines.append(f"**Automáticas:** {stats['auto_entries']}\n")
        lines.append(f"**Manuais:** {stats['manual_entries']}\n")
        lines.append(f"**Score médio:** {stats['avg_score']:.2f}\n\n")

        lines.append("| Query | Código | Descrição | Score | Manual | Timestamp |\n")
        lines.append("|-------|--------|-----------|-------|--------|------------|\n")

        for query, data in sorted(self.cache.items()):
            codigo = data.get("codigo", "")
            descricao = data.get("descricao", "")
            score = data.get("score", 0)
            manual = "Sim" if data.get("manual", False) else "Não"
            timestamp = data.get("timestamp", "")[:10]  # YYYY-MM-DD

            lines.append(
                f"| {query} | {codigo} | {descricao} | {score:.2f} | {manual} | {timestamp} |\n"
            )

        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
