"""
ContaMatcher — Matching inteligente de contas contábeis (Fase 4)

Sistema de matching em múltiplos estágios:
1. Fuzzy matching (RapidFuzz) com normalização
2. Heurísticas contábeis (palavras-chave, tipo, natureza)
3. Cache de decisões prévias
4. Fallback para IA (LLM) quando necessário

Thresholds:
- auto_accept_threshold (0.85): aceita automaticamente
- requery_threshold (0.60): solicita confirmação ou usa IA
- abaixo de 0.60: sem match confiável
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from rapidfuzz import fuzz, process

from ..generators.plano_contas import PlanodeContas

# Re-export: chamadores e testes importam `classe_from_codigo` daqui.
# Fonte única em utils/codigo.py.
from ..utils.codigo import classe_from_codigo
from ..utils.natureza import mapear_natureza
from ..utils.normalizer import normalize
from ..utils.prazo import prazo_do_codigo_referencial
from ..utils.synonyms import expand_synonyms, is_garbage_description
from .match_cache import MatchCache

# Separa a descrição do seu sufixo qualificador. Cobre hífen "-", travessão
# "–" (en dash) e "—" (em dash), sempre cercados por espaço.
_CORE_SPLIT_RE = re.compile(r"\s[-–—]\s")

#: Bônus (escala 0-100 do fuzzy) para candidato cuja natureza de resultado
#: bate com a da origem. Pequeno de propósito: desempata sem atropelar o texto.
_BONUS_NATUREZA = 5.0


@dataclass
class MatchCandidate:
    """Candidato de matching."""

    codigo: str
    descricao: str
    score: float
    tipo: str | None = None
    natureza: str | None = None
    nivel: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchDecision:
    """Decisão de matching."""

    codigo: str
    descricao: str
    score: float
    source: Literal["fuzzy", "heuristic", "ai", "cache"]
    confidence: float
    method: str = ""


@dataclass
class MatchResult:
    """Resultado completo de matching."""

    query: str
    decision: MatchDecision | None = None
    candidates: list[MatchCandidate] = field(default_factory=list)
    needs_review: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ContaMatcher:
    """
    Matcher inteligente de contas contábeis.

    Usa fuzzy matching + heurísticas + cache + IA para mapear descrições
    de balanços para o plano de contas padrão.
    """

    def __init__(
        self,
        plano_contas: PlanodeContas,
        cache_path: str | Path | None = None,
        auto_accept_threshold: float = 0.85,
        requery_threshold: float = 0.60,
        use_ai: bool = False,
        ai_classifier: Callable[[str, list[MatchCandidate], dict[str, Any] | None], MatchDecision | None] | None = None,
    ):
        """
        Args:
            plano_contas: Instância do plano de contas
            cache_path: Caminho para o arquivo de cache (default: data/match_cache.json)
            auto_accept_threshold: Score mínimo para aceitar automaticamente (0.85)
            requery_threshold: Score mínimo para considerar candidato (0.60)
            use_ai: Ativar fallback para IA (desempate) nos casos ambíguos.
            ai_classifier: Função de desempate injetável. Recebe
                ``(descricao, candidatos, contexto)`` e retorna um
                ``MatchDecision`` ou ``None``. Permite plugar um LLM
                (Claude/Ollama/etc.) sem acoplar o matcher a um provedor. Se
                ``None`` e ``use_ai=True``, cai no stub interno (retorna None).
        """
        self.plano = plano_contas
        self.auto_accept_threshold = auto_accept_threshold
        self.requery_threshold = requery_threshold
        self.use_ai = use_ai
        self.ai_classifier = ai_classifier

        # Cache
        if cache_path is None:
            cache_path = (
                Path(__file__).parent.parent.parent.parent / "data" / "match_cache.json"
            )
        self.cache = MatchCache(cache_path)

        # Carrega variações aprendidas do treinamento
        self.learned_variations = self._load_learned_variations()

        # Preparar dados para fuzzy matching
        self._prepare_fuzzy_data()

    def _load_learned_variations(self) -> dict[str, Any]:
        """Carrega variações aprendidas do treinamento."""
        variations_path = (
            Path(__file__).parent.parent / "training" / "account_variations.json"
        )

        if variations_path.exists():
            import json

            try:
                with open(variations_path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _prepare_fuzzy_data(self) -> None:
        """
        Monta o índice de busca: texto normalizado -> **todas** as contas que o
        usam.

        O índice era um ``dict[texto] = conta``. Descrições se repetem em ramos
        diferentes por natureza ("Outros" aparece em 56 códigos do plano real),
        então a última conta lida sobrescrevia as anteriores e **25,9% do plano
        ficava inalcançável** pelo matcher. Pior: era exatamente o conjunto que
        a restrição por classe (Plano C) existe para desambiguar — ela recebia
        candidatos de um índice que já havia colapsado os homônimos, de modo
        que conseguia *rejeitar* a conta errada mas nunca *achar* a certa.

        ``fuzzy_choices`` guarda os textos **distintos** (o que o RapidFuzz
        pesquisa) e ``entradas_por_texto`` expande cada acerto para todas as
        contas daquele texto, que então competem pelos filtros de classe, tipo
        e natureza. Ver REVISAO_QUALIDADE.md §4.
        """
        self.entradas_por_texto: dict[str, list[dict[str, Any]]] = {}

        # Natureza (RECEITA/DESPESA) de cada conta de resultado do referencial,
        # lida da árvore do próprio plano. Não dá para ler só da descrição:
        # "Serviços Prestados por Terceiros" nada declara, mas pende de
        # "3.90.02 Despesas Administrativas e Gerais". Era exatamente por essa
        # fresta que uma receita de serviços virava despesa.
        self.natureza_referencial: dict[str, str] = mapear_natureza(
            self.plano.contas_flat
        )

        for conta in self.plano.contas_flat:
            codigo = conta.get("codigo")
            descricao = conta.get("descricao", "")
            self._indexar(
                normalize(descricao),
                {
                    "codigo": codigo,
                    "descricao": descricao,
                    "tipo": conta.get("tipo"),
                    "natureza": conta.get("natureza"),
                    "nivel": conta.get("nivel"),
                    "classe": classe_from_codigo(codigo),
                    # RECEITA/DESPESA — o refinamento que o Plano C não tinha.
                    # A RFB marca dedução, custo e despesa com "(-)".
                    "natureza_resultado": self.natureza_referencial.get(codigo),
                    # CIRCULANTE/NÃO CIRCULANTE — o terceiro eixo. Sem ele,
                    # "Aplicação Financeira - CDB" do circulante casou com
                    # Imobilizado. Ver REVISAO_QUALIDADE.md §18.9.
                    "prazo": prazo_do_codigo_referencial(codigo),
                    "is_learned": False,
                },
            )

        # Variações aprendidas no treino, com boost por frequência.
        for codigo, variation_data in self.learned_variations.items():
            conta_original = self.plano.contas_index.get(codigo)
            if not conta_original:
                continue
            boost = min(variation_data.get("frequency", 1) / 10, 0.10)
            for variation in variation_data.get("variations", []):
                self._indexar(
                    variation,
                    {
                        "codigo": codigo,
                        "descricao": conta_original.get("descricao", ""),
                        "tipo": conta_original.get("tipo"),
                        "natureza": conta_original.get("natureza"),
                        "nivel": conta_original.get("nivel"),
                        "classe": classe_from_codigo(codigo),
                        "natureza_resultado": self.natureza_referencial.get(codigo),
                        "prazo": prazo_do_codigo_referencial(codigo),
                        "is_learned": True,
                        "boost": boost,
                    },
                )

        self.fuzzy_choices: list[str] = list(self.entradas_por_texto)

    @staticmethod
    def _chave_cache(
        query_normalizada: str,
        classe: str | None,
        natureza_resultado: str | None = None,
        prazo: str | None = None,
    ) -> str:
        """
        Chave do cache de decisões.

        Era só ``normalize(descricao)`` — mais pobre que os dados de que a
        decisão depende. Como a consulta ao cache é o **passo 1** de ``match()``,
        anterior a qualquer restrição de classe, uma decisão gravada num
        contexto (ATIVO) voltava com ``needs_review=False`` num contexto
        incompatível (PASSIVO), anulando o Plano C a partir da segunda chamada.
        Ver REVISAO_QUALIDADE.md §4c.

        A natureza de resultado entra pelo mesmo motivo, um nível abaixo:
        receita e despesa são ambas RESULTADO, então a chave por classe não as
        separava. O cache do projeto tinha gravado ``servicos prestados`` ->
        ``(-) Custo dos Serviços Prestados`` com score 1.0; qualquer receita de
        serviços herdava essa decisão e entrava na DRE como custo. Ver
        REVISAO_QUALIDADE.md §16.

        Consultas sem classe conhecida mantêm a chave antiga, preservando as
        decisões já gravadas em ``data/match_cache.json``.
        """
        if not classe:
            return query_normalizada
        refino = natureza_resultado or prazo
        if refino:
            return f"{query_normalizada}|{classe}|{refino}"
        return f"{query_normalizada}|{classe}"

    def _indexar(self, texto: str, entrada: dict[str, Any]) -> None:
        """Registra uma conta sob um texto de busca, sem sobrescrever homônimas."""
        entradas = self.entradas_por_texto.setdefault(texto, [])
        if any(e["codigo"] == entrada["codigo"] for e in entradas):
            return
        entradas.append(entrada)

    # =========================================================================
    # Match Principal
    # =========================================================================

    def match(
        self,
        descricao: str,
        tipo: str | None = None,
        natureza: str | None = None,
        saldo: float | None = None,
        context: dict[str, Any] | None = None,
        classe: str | None = None,
        codigo_origem: str | None = None,
        natureza_resultado: str | None = None,
        prazo: str | None = None,
    ) -> MatchResult:
        """
        Realiza matching de uma descrição de conta.

        Args:
            descricao: Descrição da conta a ser mapeada
            tipo: Tipo da conta (ATIVO, PASSIVO, etc.) para melhorar matching
            natureza: Natureza (Devedora/Credora)
            saldo: Valor do saldo (para heurísticas)
            context: Contexto adicional (empresa, período, etc.)
            classe: Classe contábil da conta de origem ("ATIVO"/"PASSIVO"/
                "RESULTADO"). Restringe o matching à mesma classe do alvo,
                evitando casar Ativo com Passivo (ex.: "Clientes" no ativo vs
                "Adiantamentos de Clientes" no passivo). Se None, tenta derivar
                de ``codigo_origem``.
            codigo_origem: Código da conta no balancete de origem. Usado só para
                derivar ``classe`` quando esta não é informada.
            natureza_resultado: "RECEITA" ou "DESPESA" da conta de origem,
                derivada da árvore do balancete (``utils.natureza``). Separa o
                que a classe não separa: dentro de RESULTADO, receita e despesa
                são homônimas com frequência ("Serviços prestados" existe dos
                dois lados) e têm sinais opostos. Sem isso, uma receita de
                R$ 4,9 milhões entrou como custo negativo.

        Returns:
            MatchResult com decisão e candidatos
        """
        if classe is None:
            classe = classe_from_codigo(codigo_origem)
        if not descricao or not descricao.strip():
            return MatchResult(query=descricao, needs_review=True)

        # Descarta linhas-lixo (descrições numéricas/vazias — totais e colunas
        # desalinhadas). Não entram no matching nem no aprendizado.
        if is_garbage_description(descricao):
            return MatchResult(
                query=descricao,
                needs_review=True,
                metadata={"reason": "garbage_description"},
            )

        query_normalized = normalize(descricao)
        # Consulta expandida para o vocabulário canônico contábil (sinônimos e
        # abreviações). Usada só no fuzzy/heurísticas; o cache mantém a forma
        # simples para preservar semântica e auditoria.
        query_expanded = expand_synonyms(descricao)

        # 1. Verifica cache
        chave_cache = self._chave_cache(
            query_normalized, classe, natureza_resultado, prazo
        )
        cached = self.cache.get(chave_cache)
        if cached:
            decision = MatchDecision(
                codigo=cached["codigo"],
                descricao=cached["descricao"],
                score=cached.get("score", 1.0),
                source="cache",
                confidence=cached.get("confidence", 1.0),
                method="cache_hit",
            )
            return MatchResult(
                query=descricao,
                decision=decision,
                needs_review=False,
                metadata={"cache_hit": True},
            )

        # 2. Fuzzy matching (usa consulta expandida por sinônimos)
        fuzzy_result = self._fuzzy_match(
            query_expanded, tipo, natureza, classe, natureza_resultado, prazo
        )

        if fuzzy_result and fuzzy_result.score >= self.auto_accept_threshold:
            # Auto-aceita
            decision = MatchDecision(
                codigo=fuzzy_result.codigo,
                descricao=fuzzy_result.descricao,
                score=fuzzy_result.score,
                source="fuzzy",
                confidence=fuzzy_result.score,
                method="fuzzy_auto_accept",
            )

            # Salva no cache
            self.cache.save(
                chave_cache,
                decision.codigo,
                decision.descricao,
                decision.score,
                decision.confidence,
            )

            return MatchResult(
                query=descricao,
                decision=decision,
                candidates=[fuzzy_result],
                needs_review=False,
            )

        # 3. Heurísticas para melhorar candidatos
        candidates = self._apply_heuristics(
            query_expanded, fuzzy_result, tipo, natureza, saldo, classe,
            natureza_resultado, prazo,
        )

        # 4. Verifica se melhor candidato após heurísticas está acima do threshold
        if candidates and candidates[0].score >= self.auto_accept_threshold:
            decision = MatchDecision(
                codigo=candidates[0].codigo,
                descricao=candidates[0].descricao,
                score=candidates[0].score,
                source="heuristic",
                confidence=candidates[0].score,
                method="heuristic_boost",
            )

            self.cache.save(
                chave_cache,
                decision.codigo,
                decision.descricao,
                decision.score,
                decision.confidence,
            )

            return MatchResult(
                query=descricao,
                decision=decision,
                candidates=candidates[:5],
                needs_review=False,
            )

        # 5. Fallback para IA se ativado
        if self.use_ai and candidates:
            ai_decision = self._classify_with_ai(descricao, candidates[:5], context)
            if ai_decision:
                self.cache.save(
                    chave_cache,
                    ai_decision.codigo,
                    ai_decision.descricao,
                    ai_decision.score,
                    ai_decision.confidence,
                )
                return MatchResult(
                    query=descricao,
                    decision=ai_decision,
                    candidates=candidates[:5],
                    needs_review=False,
                    metadata={"ai_used": True},
                )

        # 6. Retorna com necessidade de revisão
        return MatchResult(
            query=descricao,
            decision=None,
            candidates=candidates[:10] if candidates else [],
            needs_review=True,
            metadata={"reason": "below_threshold"},
        )

    # =========================================================================
    # Fuzzy Matching
    # =========================================================================

    def _fuzzy_match(
        self,
        query: str,
        tipo: str | None = None,
        natureza: str | None = None,
        classe: str | None = None,
        natureza_resultado: str | None = None,
        prazo: str | None = None,
    ) -> MatchCandidate | None:
        """Realiza fuzzy matching usando RapidFuzz."""
        if not query:
            return None

        # Busca os melhores matches. Limite alto de propósito: para queries
        # curtas/genéricas ("clientes", "fornecedores") dezenas de contas
        # empatam em token_set_ratio=100; um limite baixo descartaria a conta
        # certa ANTES do desempate por proximidade real (token_sort_ratio).
        results = process.extract(
            query,
            self.fuzzy_choices,
            scorer=fuzz.token_set_ratio,
            limit=40,
        )

        if not results:
            return None

        # Filtra por tipo/natureza se fornecido
        filtered = []
        for match_text, score_base, _ in results:
            for conta_info in self.entradas_por_texto.get(match_text, ()):
                score = score_base

                # Se tipo fornecido, prefere matches do mesmo tipo
                if tipo and conta_info.get("tipo") == tipo:
                    score += 5  # Boost por tipo compatível

                # Se natureza fornecida, prefere matches da mesma natureza
                if natureza and conta_info.get("natureza") == natureza:
                    score += 3  # Boost por natureza compatível

                # Se é variação aprendida, aplica boost adicional
                if conta_info.get("is_learned", False):
                    learned_boost = conta_info.get("boost", 0) * 100  # Converte para 0-100
                    score += learned_boost

                # Penalidade por classe cruzada (Plano C): se a conta de origem é de
                # uma classe (Ativo/Passivo/Resultado) e o candidato é de outra,
                # derruba o score para longe do auto-accept. Distingue casos que o
                # texto sozinho confunde ("Clientes" no ativo vs "Adiantamentos de
                # Clientes" no passivo). Só age quando ambas as classes são
                # conhecidas (código-raiz numérico). Classe já pré-computada em
                # _prepare_fuzzy_data — evita recomputar por candidato.
                if classe:
                    cand_classe = conta_info.get("classe")
                    if cand_classe and cand_classe != classe:
                        score *= 0.5

                # Penalidade por natureza de resultado cruzada. A penalidade de
                # classe acima não separa receita de despesa — as duas são
                # RESULTADO. É aqui que "Servicos prestados - mercado interno"
                # (receita) para de casar com "(-) Custo dos Serviços Prestados".
                # Mais dura que a de classe (0,3 contra 0,5) porque o erro é
                # pior: inverte o sinal da conta na DRE, contando duas vezes.
                if natureza_resultado:
                    cand_natureza = conta_info.get("natureza_resultado")
                    if cand_natureza and cand_natureza != natureza_resultado:
                        score *= 0.3
                    elif cand_natureza == natureza_resultado:
                        # O simétrico da penalidade, e ele é necessário: sem
                        # bônus, um candidato de natureza DESCONHECIDA escapa
                        # da penalidade e vence por meio ponto de texto.
                        # Medido: "Servicos prestados - mercado interno" (receita)
                        # dava 76,0 para "Receita da Prestação de Serviços no
                        # Mercado Interno" contra 76,5 de "Serviços Prestados
                        # por Terceiros", que nada declara.
                        score += _BONUS_NATUREZA

                # Mesma lógica no eixo do prazo, dentro de Ativo e Passivo.
                # Circulante e não circulante são homônimos com frequência
                # ("Aplicações financeiras", "Outros créditos") e vão para
                # blocos diferentes do Balanço — o total fecha e a repartição,
                # que é a leitura de liquidez, sai errada.
                if prazo:
                    cand_prazo = conta_info.get("prazo")
                    if cand_prazo and cand_prazo != prazo:
                        score *= 0.3
                    elif cand_prazo == prazo:
                        score += _BONUS_NATUREZA

                # "Core" da descrição: parte antes do primeiro sufixo qualificador
                # ("- no País", "– Circulante", etc.). Aceita hífen e travessão.
                core = _CORE_SPLIT_RE.split(match_text, maxsplit=1)[0].strip()

                # Desempate por proximidade real (token_sort_ratio no core) e, em
                # seguida, preferência por conta SINTÉTICA (linha genérica de
                # balancete mapeia melhor para o nível sintético que para a folha).
                tie = fuzz.token_sort_ratio(query, core)
                is_synthetic = 1 if str(conta_info.get("tipo", "")).upper() in ("S", "SINTETICA") else 0

                filtered.append((conta_info, min(score, 100.0), tie, is_synthetic))

        if not filtered:
            return None

        # Ordena: score primário; empate -> proximidade real; empate -> sintética.
        filtered.sort(key=lambda x: (x[1], x[2], x[3]), reverse=True)
        best_info, best_score, _, _ = filtered[0]

        return MatchCandidate(
            codigo=best_info["codigo"],
            descricao=best_info["descricao"],
            score=best_score / 100.0,  # Normaliza para 0-1
            tipo=best_info.get("tipo"),
            natureza=best_info.get("natureza"),
            nivel=best_info.get("nivel"),
        )

    # =========================================================================
    # Heurísticas
    # =========================================================================

    def _apply_heuristics(
        self,
        query: str,
        fuzzy_result: MatchCandidate | None,
        tipo: str | None,
        natureza: str | None,
        saldo: float | None,
        classe: str | None = None,
        natureza_resultado: str | None = None,
        prazo: str | None = None,
    ) -> list[MatchCandidate]:
        """
        Aplica heurísticas contábeis para melhorar matching.

        Heurísticas:
        - Palavras-chave contábeis (caixa, banco, estoque, etc.)
        - Sinônimos e abreviações
        - Tipo e natureza compatíveis
        - Classe contábil (Ativo/Passivo/Resultado) compatível
        - Saldo (positivo/negativo) compatível com natureza
        """
        candidates = []
        # Rastreia quais candidatos JÁ passaram pela penalidade de classe.
        # O fuzzy_result vem penalizado por _fuzzy_match; keyword-added, não.
        _already_penalized: set[str] = set()

        # Busca inicial via fuzzy (já traz penalidade de classe aplicada)
        if fuzzy_result:
            candidates.append(fuzzy_result)
            _already_penalized.add(fuzzy_result.codigo)

        # Busca por palavras-chave específicas
        keywords = self._extract_keywords(query)
        for keyword in keywords:
            keyword_matches = self._search_by_keyword(keyword, tipo, natureza)
            for match in keyword_matches:
                # Evita duplicatas
                if not any(c.codigo == match.codigo for c in candidates):
                    candidates.append(match)

        # Penalidade por classe cruzada (Plano C): SÓ em candidatos ainda não
        # penalizados (evita dupla penalidade no fuzzy_result que já veio
        # multiplicado por 0.5 em _fuzzy_match — antes caía para 0.25).
        if classe:
            for candidate in candidates:
                if candidate.codigo in _already_penalized:
                    continue
                cand_classe = classe_from_codigo(candidate.codigo)
                if cand_classe and cand_classe != classe:
                    candidate.score *= 0.5

        # Mesma lógica um nível abaixo: receita não pode virar despesa.
        if natureza_resultado:
            for candidate in candidates:
                if candidate.codigo in _already_penalized:
                    continue
                cand_natureza = self.natureza_referencial.get(candidate.codigo)
                if cand_natureza and cand_natureza != natureza_resultado:
                    candidate.score *= 0.3

        # E no eixo do prazo: circulante não pode virar não circulante.
        if prazo:
            for candidate in candidates:
                if candidate.codigo in _already_penalized:
                    continue
                cand_prazo = prazo_do_codigo_referencial(candidate.codigo)
                if cand_prazo and cand_prazo != prazo:
                    candidate.score *= 0.3

        # Boost baseado em saldo/natureza
        if saldo is not None and natureza:
            for candidate in candidates:
                if self._is_saldo_compatible(saldo, natureza, candidate.natureza):
                    candidate.score = min(candidate.score + 0.05, 1.0)

        # Ordena por score
        candidates.sort(key=lambda c: c.score, reverse=True)

        return candidates

    def _extract_keywords(self, text: str) -> list[str]:
        """Extrai palavras-chave contábeis do texto."""
        # Palavras-chave importantes no contexto contábil
        important_keywords = {
            "caixa",
            "banco",
            "estoque",
            "cliente",
            "fornecedor",
            "capital",
            "lucro",
            "prejuízo",
            "receita",
            "despesa",
            "ativo",
            "passivo",
            "investimento",
            "imobilizado",
            "intangível",
            "empréstimo",
            "financiamento",
        }

        words = text.lower().split()
        keywords = [w for w in words if w in important_keywords]

        return keywords

    def _search_by_keyword(
        self,
        keyword: str,
        tipo: str | None,
        natureza: str | None,
    ) -> list[MatchCandidate]:
        """Busca contas que contenham a palavra-chave."""
        matches = []

        # Cache lazy da lista [(descricao_normalizada, conta)] — antes esse
        # normalize() rodava por conta a cada query (7400+ * keywords vezes).
        if not hasattr(self, "_norm_contas_cache"):
            self._norm_contas_cache = [
                (normalize(conta.get("descricao", "")), conta)
                for conta in self.plano.contas_flat
            ]

        for descricao_norm, conta in self._norm_contas_cache:
            if keyword in descricao_norm:
                # Score base por keyword match
                score = 0.70

                # Boost por tipo
                if tipo and conta.get("tipo") == tipo:
                    score += 0.10

                # Boost por natureza
                if natureza and conta.get("natureza") == natureza:
                    score += 0.05

                matches.append(
                    MatchCandidate(
                        codigo=conta["codigo"],
                        descricao=conta["descricao"],
                        score=min(score, 1.0),
                        tipo=conta.get("tipo"),
                        natureza=conta.get("natureza"),
                        nivel=conta.get("nivel"),
                    )
                )

        return matches

    def _is_saldo_compatible(
        self,
        saldo: float,
        natureza_query: str | None,
        natureza_candidate: str | None,
    ) -> bool:
        """Verifica se o saldo é compatível com a natureza da conta."""
        if not natureza_query or not natureza_candidate:
            return True

        # Devedora: saldo positivo normal
        # Credora: saldo negativo ou credor normal
        if saldo > 0 and natureza_candidate == "Devedora":
            return True
        if saldo < 0 and natureza_candidate == "Credora":
            return True

        return False

    # =========================================================================
    # IA (Stub)
    # =========================================================================

    def _classify_with_ai(
        self,
        descricao: str,
        candidates: list[MatchCandidate],
        context: dict[str, Any] | None,
    ) -> MatchDecision | None:
        """
        Classifica usando IA (LLM).

        STUB: Implementação futura com Ollama/OpenAI/Claude.

        Args:
            descricao: Descrição original
            candidates: Top candidatos do fuzzy/heuristics
            context: Contexto adicional

        Returns:
            MatchDecision se IA conseguir decidir, None caso contrário
        """
        # Classificador injetável (LLM ou heurística externa). Mantém o matcher
        # desacoplado do provedor: o chamador injeta ai_classifier=... .
        if self.ai_classifier is not None:
            try:
                return self.ai_classifier(descricao, candidates, context)
            except Exception:
                # Falha do classificador nunca derruba o pipeline de matching.
                return None

        # Sem classificador injetado: stub (nenhuma decisão por IA).
        # TODO: Implementar integração com LLM
        # Exemplo de prompt:
        #
        # Você é um especialista em contabilidade brasileira.
        # Preciso que você mapeie a seguinte descrição de conta:
        # "{descricao}"
        #
        # Candidatos possíveis:
        # 1. {codigo1} - {descricao1} (score: {score1})
        # 2. {codigo2} - {descricao2} (score: {score2})
        # ...
        #
        # Contexto: {context}
        #
        # Retorne o número do candidato mais apropriado e sua confiança (0-1).
        # Formato: {"candidate": 1, "confidence": 0.95}

        # Por enquanto, retorna None (não implementado)
        return None

    # =========================================================================
    # Batch Processing
    # =========================================================================

    def match_batch(
        self,
        contas: list[dict[str, Any]],
    ) -> list[MatchResult]:
        """
        Processa lote de contas.

        Args:
            contas: Lista de dicts com {descricao, tipo?, natureza?, saldo?}

        Returns:
            Lista de MatchResults
        """
        results = []

        for conta in contas:
            result = self.match(
                descricao=conta.get("descricao", ""),
                tipo=conta.get("tipo"),
                natureza=conta.get("natureza"),
                saldo=conta.get("saldo"),
                context=conta.get("context"),
                classe=conta.get("classe"),
                codigo_origem=conta.get("codigo"),
            )
            results.append(result)

        return results

    # =========================================================================
    # Estatísticas
    # =========================================================================

    def get_stats(self, results: list[MatchResult]) -> dict[str, Any]:
        """Retorna estatísticas de um lote de resultados."""
        total = len(results)
        if total == 0:
            return {}

        auto_matched = sum(1 for r in results if r.decision and not r.needs_review)
        needs_review = sum(1 for r in results if r.needs_review)
        cache_hits = sum(
            1 for r in results if r.decision and r.decision.source == "cache"
        )
        ai_used = sum(1 for r in results if r.metadata.get("ai_used"))

        avg_confidence = 0.0
        if auto_matched > 0:
            avg_confidence = (
                sum(
                    r.decision.confidence
                    for r in results
                    if r.decision and not r.needs_review
                )
                / auto_matched
            )

        return {
            "total": total,
            "auto_matched": auto_matched,
            "auto_matched_pct": (auto_matched / total) * 100,
            "needs_review": needs_review,
            "needs_review_pct": (needs_review / total) * 100,
            "cache_hits": cache_hits,
            "cache_hit_rate": (cache_hits / total) * 100,
            "ai_used": ai_used,
            "avg_confidence": avg_confidence,
        }
