"""
PlanodeContas — Classe para carregar e consultar plano de contas

Carrega o arquivo JSON gerado (plano_contas.json) e oferece métodos para:
- Busca por código (lookup O(1))
- Busca fuzzy por descrição
- Obter hierarquia completa de uma conta
- Listar contas por formulário/aba
- Cache em memória para performance
"""

import json
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from src.bp.utils.normalizer import normalize


class PlanodeContas:
    """Classe para carregar e consultar plano de contas consolidado."""

    def __init__(self, json_path: Path | None = None):
        """
        Inicializa carregando o JSON do plano de contas.

        Args:
            json_path: Caminho para plano_contas.json. Se None, usa padrão data/plano_contas.json
        """
        if json_path is None:
            json_path = (
                Path(__file__).parent.parent.parent.parent
                / "data"
                / "plano_contas.json"
            )

        self.json_path = Path(json_path)

        # Estruturas carregadas do JSON
        self.forms: dict[str, list[str]] = {}
        self.contas_flat: list[dict] = []
        self.contas_tree: list[dict] = []
        self.contas_index: dict[str, dict] = {}

        # Cache para buscas
        self._descricoes_normalizadas: dict[
            str, str
        ] = {}  # codigo -> descricao normalizada

        # Carrega tudo
        self._load()

    def _load(self):
        """Carrega o JSON e popula as estruturas em memória."""
        if not self.json_path.exists():
            raise FileNotFoundError(f"Plano de contas não encontrado: {self.json_path}")

        with open(self.json_path, encoding="utf-8") as f:
            data = json.load(f)

        self.forms = data.get("forms", {})
        self.contas_flat = data.get("contas_flat", [])
        self.contas_tree = data.get("contas_tree", [])
        self.contas_index = data.get("contas_index", {})

        # Popula cache de descrições normalizadas
        for codigo, conta in self.contas_index.items():
            descricao = conta.get("descricao", "")
            self._descricoes_normalizadas[codigo] = normalize(descricao)

    def buscar_por_codigo(self, codigo: str) -> dict[str, Any] | None:
        """
        Busca conta por código (lookup O(1)).

        Args:
            codigo: Código da conta (ex: "1.1.1")

        Returns:
            Dict com dados da conta ou None se não encontrado
        """
        return self.contas_index.get(codigo)

    def buscar_por_descricao(
        self, texto: str, threshold: float = 0.70, limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        Busca fuzzy por descrição usando rapidfuzz.

        Args:
            texto: Texto a buscar (ex: "caixa", "ativo circulante")
            threshold: Score mínimo (0.0 a 1.0) para considerar match
            limit: Número máximo de resultados

        Returns:
            Lista de dicts com 'codigo', 'descricao', 'score', 'conta' (dados completos)
            Ordenado por score decrescente
        """
        texto_norm = normalize(texto)

        # Usa rapidfuzz para buscar nas descrições normalizadas
        choices = list(
            self._descricoes_normalizadas.items()
        )  # [(codigo, descricao_norm), ...]

        # Extrai apenas as descrições para o process.extract
        descricoes = [desc for _, desc in choices]

        # Busca fuzzy
        results = process.extract(
            texto_norm,
            descricoes,
            scorer=fuzz.token_sort_ratio,
            limit=limit,
            score_cutoff=threshold * 100,  # rapidfuzz usa 0-100
        )

        # Mapeia resultados de volta aos códigos
        output = []
        for descricao_match, score, idx in results:
            codigo = choices[idx][0]
            conta = self.contas_index[codigo]
            output.append(
                {
                    "codigo": codigo,
                    "descricao": conta.get("descricao", ""),
                    "score": score / 100.0,  # normaliza para 0.0-1.0
                    "conta": conta,
                }
            )

        return output

    def obter_hierarquia(self, codigo: str) -> list[dict[str, Any]]:
        """
        Retorna caminho hierárquico completo até a raiz.

        Args:
            codigo: Código da conta (ex: "1.1.1.2.1.10.03")

        Returns:
            Lista de contas do nível raiz até a conta especificada
            Ex: [{"codigo": "1", ...}, {"codigo": "1.1", ...}, {"codigo": "1.1.1", ...}]
        """
        caminho = []
        conta_atual = self.contas_index.get(codigo)

        if not conta_atual:
            return []

        # Adiciona a conta atual
        caminho.insert(0, conta_atual.copy())

        # Sobe até a raiz
        while conta_atual and conta_atual.get("parent_id"):
            parent_id = conta_atual["parent_id"]
            conta_atual = self.contas_index.get(parent_id)
            if conta_atual:
                caminho.insert(0, conta_atual.copy())

        return caminho

    def listar_contas_por_form(self, form_name: str) -> list[dict[str, Any]]:
        """
        Lista todas as contas de um formulário/aba específico.

        Args:
            form_name: Nome do formulário (ex: "L100A", "L100B")

        Returns:
            Lista de contas que aparecem nesse formulário
        """
        codigos = self.forms.get(form_name, [])
        contas = []

        for codigo in codigos:
            conta = self.contas_index.get(codigo)
            if conta:
                contas.append(conta.copy())

        return contas

    def listar_forms(self) -> list[str]:
        """
        Lista todos os formulários/abas disponíveis.

        Returns:
            Lista com nomes dos formulários
        """
        return sorted(self.forms.keys())

    def get_filhos(self, codigo: str) -> list[dict[str, Any]]:
        """
        Retorna contas filhas diretas de uma conta.

        Args:
            codigo: Código da conta pai

        Returns:
            Lista de contas filhas (nível imediatamente abaixo)
        """
        filhos = []

        for cod, conta in self.contas_index.items():
            if conta.get("parent_id") == codigo:
                filhos.append(conta.copy())

        # Ordena por código
        filhos.sort(key=lambda x: x.get("codigo", ""))

        return filhos

    def estatisticas(self) -> dict[str, Any]:
        """
        Retorna estatísticas sobre o plano de contas.

        Returns:
            Dict com contagens e informações
        """
        niveis = {}
        tipos = {}
        naturezas = {}

        for conta in self.contas_index.values():
            # Conta por nível
            nivel = conta.get("nivel")
            if nivel:
                niveis[nivel] = niveis.get(nivel, 0) + 1

            # Conta por tipo
            tipo = conta.get("tipo", "").upper()
            if tipo:
                tipos[tipo] = tipos.get(tipo, 0) + 1

            # Conta por natureza
            natureza = conta.get("natureza", "").upper()
            if natureza:
                naturezas[natureza] = naturezas.get(natureza, 0) + 1

        return {
            "total_contas": len(self.contas_index),
            "total_forms": len(self.forms),
            "contas_por_nivel": niveis,
            "contas_por_tipo": tipos,
            "contas_por_natureza": naturezas,
            "nivel_maximo": max(niveis.keys()) if niveis else 0,
        }

    def __repr__(self):
        return (
            f"<PlanodeContas: {len(self.contas_index)} contas, {len(self.forms)} forms>"
        )


# Exemplo de uso
if __name__ == "__main__":
    plano = PlanodeContas()

    print(f"\n{plano}")
    print("\n📊 Estatísticas:")
    stats = plano.estatisticas()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n🔍 Busca por código '1':")
    conta = plano.buscar_por_codigo("1")
    if conta:
        print(f"  {conta['codigo']} - {conta.get('descricao')}")

    print("\n🔍 Busca fuzzy 'caixa':")
    results = plano.buscar_por_descricao("caixa", threshold=0.6, limit=5)
    for r in results:
        print(f"  [{r['score']:.2f}] {r['codigo']} - {r['descricao']}")

    print("\n📋 Formulários disponíveis:")
    forms = plano.listar_forms()
    print(f"  Total: {len(forms)}")
    print(f"  Primeiros 5: {forms[:5]}")
