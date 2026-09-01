"""
PlanoContasGenerator

Classe responsável por carregar arquivos Excel (com várias abas), consolidar
contas em uma lista `contas_flat`, construir uma `contas_tree` hierárquica e
um `contas_index` para lookup rápido.

Este módulo é uma refatoração do script auxiliar existente e tem a intenção
ser reutilizável por outros componentes do sistema.
"""

import json
from pathlib import Path

import pandas as pd

from src.bp.models.conta import ContaModel
from src.bp.utils.normalizer import normalize

# Mapeamento de nomes de colunas candidatos (mesma lógica usada antes)
CANDIDATE_KEYS = {
    "codigo": ["codigo", "código", "cod", "conta", "code", "account_code"],
    "descricao": [
        "descricao",
        "descrição",
        "descr",
        "desc",
        "description",
        "account_desc",
    ],
    "tipo": ["tipo", "type", "account_type"],
    "natureza": ["natureza", "nature", "natu"],
    "nivel": ["nivel", "nível", "level"],
    "parent": ["parent", "parent_id", "conta_superior", "superior", "pai"],
    "formula": ["formula", "fórmula", "form"],
    "formato": ["formato", "format", "format"],
    "tipo_lanc": ["tipo lanç", "tipo de lancamento", "tipo lanc", "tipo_lanc"],
    "relacio": ["relacionamento", "relac"],
}


class PlanoContasGenerator:
    def __init__(self, excel_path: Path | None = None):
        self.excel_path = Path(excel_path) if excel_path else None

    def find_column_map(self, columns: list[str]) -> dict[str, str]:
        norm_cols = {normalize(c): c for c in columns}
        mapping: dict[str, str] = {}
        for field, candidates in CANDIDATE_KEYS.items():
            for cand in candidates:
                if cand in norm_cols:
                    mapping[field] = norm_cols[cand]
                    break
        return mapping

    def infer_parent_from_code(self, code: str) -> str | None:
        if not isinstance(code, str):
            code = str(code)
        code = code.strip()
        if "." in code:
            return code.rsplit(".", 1)[0]
        if code.isdigit() and len(code) > 1:
            return code[:-1] if len(code) == 2 else code[:-2]
        return None

    def row_to_conta(
        self, row: pd.Series, mapping: dict[str, str], sheet_name: str
    ) -> dict | None:
        codigo = row.get(mapping.get("codigo")) if mapping.get("codigo") else None
        if pd.isna(codigo) or codigo is None:
            return None
        codigo = str(codigo).strip()

        descricao = (
            row.get(mapping.get("descricao")) if mapping.get("descricao") else ""
        )
        descricao = "" if pd.isna(descricao) else str(descricao).strip()

        tipo = row.get(mapping.get("tipo")) if mapping.get("tipo") else ""
        tipo = "" if pd.isna(tipo) else str(tipo).strip()

        natureza = row.get(mapping.get("natureza")) if mapping.get("natureza") else ""
        natureza = "" if pd.isna(natureza) else str(natureza).strip()

        formula = row.get(mapping.get("formula")) if mapping.get("formula") else ""
        formula = "" if pd.isna(formula) else str(formula).strip()

        formato = row.get(mapping.get("formato")) if mapping.get("formato") else ""
        formato = "" if pd.isna(formato) else str(formato).strip()

        tipo_lanc = (
            row.get(mapping.get("tipo_lanc")) if mapping.get("tipo_lanc") else ""
        )
        tipo_lanc = "" if pd.isna(tipo_lanc) else str(tipo_lanc).strip()

        relacio = row.get(mapping.get("relacio")) if mapping.get("relacio") else ""
        relacio = "" if pd.isna(relacio) else str(relacio).strip()

        nivel = row.get(mapping.get("nivel")) if mapping.get("nivel") else None
        try:
            nivel = int(nivel) if nivel not in (None, "", float("nan")) else None
        except Exception:
            nivel = None

        parent = None
        if mapping.get("parent"):
            parent = row.get(mapping.get("parent"))
            parent = None if pd.isna(parent) else str(parent).strip()
        if not parent:
            parent = self.infer_parent_from_code(codigo)

        # validação via Pydantic (não lança se inválido)
        conta_obj = ContaModel(
            codigo=codigo,
            descricao=descricao,
            tipo=tipo or None,
            natureza=natureza or None,
            nivel=nivel,
            parent_id=parent,
            forms=[sheet_name],
            formula=formula or None,
            formato=formato or None,
            tipo_do_lancamento=tipo_lanc or None,
            relacao=relacio or None,
        )

        return conta_obj.model_dump()

    def process_excel(
        self, path_in: Path | None = None
    ) -> tuple[list[dict], dict[str, list[str]]]:
        path = Path(path_in) if path_in else self.excel_path
        if not path or not path.exists():
            raise FileNotFoundError(f"Arquivo Excel não encontrado: {path}")

        xls = pd.read_excel(path, sheet_name=None, dtype=str)
        flat_by_code: dict[str, dict] = {}
        forms_map: dict[str, set] = {}

        for sheet_name, df in xls.items():
            if df is None or df.shape[0] == 0:
                continue
            mapping = self.find_column_map(df.columns)
            if "codigo" not in mapping and "descricao" not in mapping:
                cols = list(df.columns[:2])
                mapping = mapping.copy()
                if "codigo" not in mapping and len(cols) >= 1:
                    mapping["codigo"] = cols[0]
                if "descricao" not in mapping and len(cols) >= 2:
                    mapping["descricao"] = cols[1]

            forms_map.setdefault(sheet_name, set())

            for _, r in df.iterrows():
                conta = self.row_to_conta(r, mapping, sheet_name)
                if not conta:
                    continue
                codigo = conta["codigo"]
                forms_map[sheet_name].add(codigo)

                if codigo in flat_by_code:
                    existing = flat_by_code[codigo]
                    # merge simples: prefere descrições mais longas e junta forms
                    if not existing.get("descricao") or len(
                        conta.get("descricao", "")
                    ) > len(existing.get("descricao", "")):
                        existing["descricao"] = conta.get("descricao")
                    for k in (
                        "tipo",
                        "natureza",
                        "nivel",
                        "formula",
                        "formato",
                        "tipo_do_lancamento",
                        "relacao",
                    ):
                        if not existing.get(k) and conta.get(k):
                            existing[k] = conta[k]
                    if not existing.get("parent_id") and conta.get("parent_id"):
                        existing["parent_id"] = conta["parent_id"]
                    existing_forms = set(existing.get("forms", []))
                    existing_forms.update(conta.get("forms", []))
                    existing["forms"] = sorted(existing_forms)
                else:
                    flat_by_code[codigo] = conta

        flat_list = list(flat_by_code.values())
        flat_list.sort(key=lambda x: x.get("codigo", ""))
        forms_map = {k: sorted(v) for k, v in forms_map.items()}
        return flat_list, forms_map

    def build_tree_and_index(
        self, flat_list: list[dict]
    ) -> tuple[list[dict], dict[str, dict]]:
        nodes: dict[str, dict] = {}
        for acc in flat_list:
            code = acc["codigo"]
            nodes[code] = {
                "codigo": code,
                "descricao": acc.get("descricao", ""),
                "tipo": acc.get("tipo", ""),
                "natureza": acc.get("natureza", ""),
                "nivel": acc.get("nivel"),
                "parent_id": acc.get("parent_id"),
                "forms": list(acc.get("forms", [])),
                "children": [],
            }

        roots: list[dict] = []
        for code, node in nodes.items():
            parent_code = node.get("parent_id")
            if parent_code and parent_code in nodes:
                nodes[parent_code]["children"].append(node)
            elif parent_code:
                anc = parent_code
                found = False
                while anc:
                    if anc in nodes:
                        nodes[anc]["children"].append(node)
                        node["parent_id"] = anc
                        found = True
                        break
                    anc = self.infer_parent_from_code(anc)
                if not found:
                    roots.append(node)
            else:
                roots.append(node)

        index: dict[str, dict] = {}
        for code, node in nodes.items():
            index[code] = {
                "codigo": node["codigo"],
                "descricao": node["descricao"],
                "tipo": node["tipo"],
                "natureza": node["natureza"],
                "nivel": node["nivel"],
                "parent_id": node.get("parent_id"),
                "forms": node.get("forms", []),
            }

        def sort_children(n: dict):
            n["children"].sort(key=lambda x: x.get("codigo", ""))
            for c in n["children"]:
                sort_children(c)

        for r in roots:
            sort_children(r)

        return roots, index

    def save_json(
        self,
        flat_list: list[dict],
        forms_map: dict[str, list[str]],
        tree_roots: list[dict],
        index_map: dict[str, dict],
        path_out: Path,
    ):
        payload = {
            "forms": forms_map,
            "contas_flat": flat_list,
            "contas_tree": tree_roots,
            "contas_index": index_map,
        }
        path_out.parent.mkdir(parents=True, exist_ok=True)
        with open(path_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def gerar_completo(
        self, path_in: Path | None = None, path_out: Path | None = None
    ) -> bool:
        """Orquestra todo o processo: extrai flat, constrói tree/index, salva JSON.

        Retorna True se sucesso, False caso contrário.
        """
        try:
            flat_list, forms_map = self.process_excel(path_in)
            tree_roots, index_map = self.build_tree_and_index(flat_list)
            self.save_json(
                flat_list,
                forms_map,
                tree_roots,
                index_map,
                path_out or Path("data/plano_contas.json"),
            )
            return True
        except Exception as e:
            print(f"Erro: {e}")
            return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Gerar JSON do plano de contas a partir de XLSX (classe)"
    )
    parser.add_argument(
        "--input",
        "-i",
        help="Arquivo xlsx de entrada (ex: src/plano_master.xlsx). Se não informado, pede input interativo.",
    )
    parser.add_argument(
        "--output", "-o", default="data/plano_contas.json", help="Arquivo JSON de saída"
    )
    args = parser.parse_args()

    # Se não passou input, pede input
    if not args.input:
        from pathlib import Path

        src_dir = Path(__file__).parent.parent.parent / "src"
        xlsx_files = [f.name for f in src_dir.glob("*.xlsx")]
        if xlsx_files:
            print("\nArquivos encontrados em src/:")
            for idx, f in enumerate(xlsx_files, 1):
                print(f"  {idx}. {f}")
            escolha = int(input("Escolha (número): "))
            args.input = src_dir / xlsx_files[escolha - 1]
        else:
            print("Nenhum arquivo .xlsx encontrado em src/")
            exit(1)

    gen = PlanoContasGenerator(args.input)
    success = gen.gerar_completo(path_out=Path(args.output))
    if success:
        print(f"✅ JSON salvo em: {args.output}")
    else:
        print("❌ Erro ao gerar JSON")
