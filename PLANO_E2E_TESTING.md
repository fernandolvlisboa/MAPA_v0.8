# 🎯 PLANO DE CORREÇÃO DO CICLO VICIOSO — End-to-End Testing

## 📊 DIAGNÓSTICO DO PROBLEMA

### **Ciclo Atual (VICIOSO):**
```
1. Desenvolver Parsers
2. Testar Parsers (unitário)
3. ✅ Testes passam
4. Desenvolver Export
5. ❌ Export falha/vazio
6. 🔄 Voltar ao passo 1 (LOOP)
```

### **Causa Raiz:**
- **Testes isolados não validam o objetivo final (export)**
- **Parsers testados com mocks, não com pipeline completo**
- **Nenhum teste end-to-end até o export**
- **Validação tardia (apenas no final do ciclo)**

---

## ✅ SOLUÇÃO: Test-Driven Development com End-to-End First

### **Novo Ciclo (VIRTUOSO):**
```
1. Definir CONTRACT do export (o que precisa sair)
2. Criar TESTE END-TO-END (parse → match → export)
3. ❌ Teste falha (red)
4. Implementar/corrigir parsers/matchers/exporters
5. ✅ Teste passa (green)
6. Refatorar (refactor)
7. Deploy com confiança
```

---

## 📋 PLANO DE IMPLEMENTAÇÃO

### **FASE 1: Definir Contratos de Saída (1 hora)**

#### 1.1. Documentar Estrutura Esperada do Export

**Arquivo:** `docs/EXPORT_CONTRACT.md`

```markdown
# Contrato de Exportação — BP System

## Estrutura Mínima Esperada

### Aba "Summary"
- Total Accounts > 0
- Synthetic (Mappable) > 0
- Match Rate % > 0

### Aba "Accounts"
Colunas obrigatórias:
- codigo_original (pode ser None para flat structures)
- descricao_original (NUNCA vazio)
- saldo (numérico)
- nivel (inteiro >= 1)
- match_codigo (String ou None)
- match_descricao (String ou None)
- match_score (0.0 a 1.0)

### Critérios de Sucesso
1. Pelo menos 1 conta extraída
2. Todas as descrições não vazias
3. Todos os saldos numéricos válidos
4. Pelo menos 50% das contas sintéticas matched (se houver plano)
5. Nenhuma exceção durante export
```

#### 1.2. Criar Schema de Validação

**Arquivo:** `src/bp/validators/export_schema.py`

```python
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class ExportValidationResult:
    valid: bool
    errors: List[str]
    warnings: List[str]
    metrics: Dict[str, Any]

def validate_parsed_accounts(accounts: List[Dict[str, Any]]) -> ExportValidationResult:
    """Valida contas extraídas do parser antes do export"""
    errors = []
    warnings = []
    
    # Validação 1: Lista não vazia
    if not accounts:
        errors.append("No accounts extracted")
        return ExportValidationResult(False, errors, warnings, {})
    
    # Validação 2: Todas contas têm descrição
    empty_desc = [i for i, a in enumerate(accounts) if not a.get('descricao', '').strip()]
    if empty_desc:
        errors.append(f"{len(empty_desc)} accounts with empty description: {empty_desc[:5]}")
    
    # Validação 3: Saldos numéricos
    invalid_saldo = []
    for i, a in enumerate(accounts):
        try:
            float(a.get('saldo', 0))
        except (ValueError, TypeError):
            invalid_saldo.append(i)
    if invalid_saldo:
        errors.append(f"{len(invalid_saldo)} accounts with invalid saldo: {invalid_saldo[:5]}")
    
    # Validação 4: Nível válido
    invalid_nivel = [i for i, a in enumerate(accounts) if not isinstance(a.get('nivel'), int) or a.get('nivel', 0) < 1]
    if invalid_nivel:
        warnings.append(f"{len(invalid_nivel)} accounts with invalid nivel: {invalid_nivel[:5]}")
    
    metrics = {
        'total_accounts': len(accounts),
        'with_codigo': sum(1 for a in accounts if a.get('codigo')),
        'with_descricao': sum(1 for a in accounts if a.get('descricao', '').strip()),
        'valid_saldo': len(accounts) - len(invalid_saldo),
        'avg_saldo': sum(float(a.get('saldo', 0)) for a in accounts) / len(accounts)
    }
    
    return ExportValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        metrics=metrics
    )
```

---

### **FASE 2: Testes End-to-End (2 horas)**

#### 2.1. Suite de Testes E2E por Arquivo

**Arquivo:** `tests/test_e2e_export.py`

```python
"""
End-to-End Tests: Parse → Match → Export

Valida o pipeline completo para cada arquivo do corpus.
Garante que parsers extraem dados exportáveis.
"""

import pytest
from pathlib import Path
from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.matchers import ContaMatcher
from src.bp.generators.plano_contas import PlanodeContas
from src.bp.exporters.xlsx_exporter import export_balance_sheet_to_xlsx
from src.bp.validators.export_schema import validate_parsed_accounts
import openpyxl

# Corpus de testes
CORPUS_FILES = [
    "Balancete Real Life.xlsx",  # Flat structure
    "Balancete 072022 122022 - RBM.xlsx",  # Hierarchical
    "202404_2024 - Balancete.xlsx",  # Standard
    "1544 - BALANCETE 1222024.csv",  # CSV
    "2019-01.TXT",  # TXT
]

@pytest.fixture
def plano():
    return PlanodeContas(Path("data/plano_contas.json"))

@pytest.fixture
def corpus_dir():
    return Path("src/bp/training/DFS_Exemple")

class TestEndToEndExport:
    """Testes que validam o pipeline completo até o export"""
    
    @pytest.mark.parametrize("filename", CORPUS_FILES)
    def test_parse_produces_exportable_accounts(self, filename, corpus_dir):
        """
        TESTE CRÍTICO 1: Parser extrai contas válidas para export
        
        Valida:
        - Contas não vazias
        - Descrições válidas
        - Saldos numéricos
        - Estrutura mínima para export
        """
        file_path = corpus_dir / filename
        
        # Parse
        accounts = ParseyCaller(file_path).parse()
        
        # Validação do schema
        validation = validate_parsed_accounts(accounts)
        
        # Assertions
        assert validation.valid, f"Validation failed: {validation.errors}"
        assert validation.metrics['total_accounts'] > 0, "No accounts extracted"
        assert validation.metrics['with_descricao'] == validation.metrics['total_accounts'], \
            "Some accounts have empty descriptions"
        
        # Warnings are OK, but log them
        if validation.warnings:
            print(f"\nWarnings for {filename}:")
            for w in validation.warnings:
                print(f"  - {w}")
    
    @pytest.mark.parametrize("filename", CORPUS_FILES)
    def test_parse_match_integration(self, filename, corpus_dir, plano):
        """
        TESTE CRÍTICO 2: Contas parseadas podem ser matched
        
        Valida:
        - Matching não falha
        - Scores válidos (0.0 a 1.0)
        - Pelo menos algumas contas matched (se sintéticas)
        """
        file_path = corpus_dir / filename
        
        # Parse
        accounts = ParseyCaller(file_path).parse()
        assert len(accounts) > 0, "No accounts to match"
        
        # Match
        matcher = ContaMatcher(
            plano,
            cache_path="tests/fixtures/test_cache.json",
            auto_accept_threshold=0.85
        )
        
        matched_count = 0
        for account in accounts:
            desc = account.get('descricao', '')
            if not desc:
                continue
                
            result = matcher.match(desc)
            
            # Validações
            assert result is not None, f"Matcher returned None for '{desc}'"
            assert 0.0 <= result.decision.score <= 1.0, f"Invalid score: {result.decision.score}"
            
            if result.decision.codigo:
                matched_count += 1
        
        # Pelo menos 10% matched (conservador)
        min_matched = len(accounts) * 0.1
        assert matched_count >= min_matched, \
            f"Only {matched_count}/{len(accounts)} matched (expected >{min_matched})"
    
    @pytest.mark.parametrize("filename", CORPUS_FILES)
    def test_full_export_pipeline(self, filename, corpus_dir, plano, tmp_path):
        """
        TESTE CRÍTICO 3: Pipeline completo Parse → Match → Export
        
        Valida:
        - Export não falha
        - Arquivo .xlsx gerado
        - Arquivo não vazio
        - Abas essenciais criadas
        - Métricas > 0
        """
        file_path = corpus_dir / filename
        output_path = tmp_path / f"export_{filename}.xlsx"
        
        # Export completo
        result_path = export_balance_sheet_to_xlsx(
            input_path=file_path,
            output_path=output_path,
            plano_path=Path("data/plano_contas.json"),
            training_dir=Path("src/bp/training")
        )
        
        # Validação 1: Arquivo criado
        assert result_path.exists(), f"Export file not created: {result_path}"
        assert result_path.stat().st_size > 10000, f"Export file too small: {result_path.stat().st_size} bytes"
        
        # Validação 2: Abas essenciais
        wb = openpyxl.load_workbook(result_path)
        required_sheets = ['Summary', 'Accounts', 'Hierarchy', 'Unmatched']
        for sheet in required_sheets:
            assert sheet in wb.sheetnames, f"Missing required sheet: {sheet}"
        
        # Validação 3: Summary tem métricas > 0
        summary = wb['Summary']
        total_accounts_cell = summary['B3']  # Row 3: Total Accounts
        total_accounts = total_accounts_cell.value
        assert total_accounts > 0, f"Total Accounts is 0 in Summary sheet"
        
        # Validação 4: Accounts tem dados
        accounts_sheet = wb['Accounts']
        # Pelo menos 2 rows (header + 1 conta)
        assert accounts_sheet.max_row >= 2, "Accounts sheet has no data rows"
        
        print(f"\n✅ {filename}: {total_accounts} accounts exported successfully")
    
    def test_export_handles_corrupted_file_gracefully(self, tmp_path):
        """
        TESTE CRÍTICO 4: Export falha graciosamente para arquivos corrompidos
        
        Valida:
        - Não trava indefinidamente
        - Retorna erro claro
        - Não gera arquivo vazio
        """
        # Cria arquivo corrompido
        bad_file = tmp_path / "corrupted.xls"
        bad_file.write_bytes(b"NOT A VALID XLS FILE")
        
        output_path = tmp_path / "should_not_exist.xlsx"
        
        # Deve falhar ou criar arquivo vazio detectável
        with pytest.raises(Exception) as exc_info:
            export_balance_sheet_to_xlsx(
                input_path=bad_file,
                output_path=output_path
            )
        
        # Se não lançou exceção, verifica se arquivo tem warning
        if output_path.exists():
            wb = openpyxl.load_workbook(output_path)
            summary = wb['Summary']
            total = summary['B3'].value
            assert total == 0, "Corrupted file should result in 0 accounts"
```

#### 2.2. Teste de Regressão com Golden Files

**Arquivo:** `tests/test_export_regression.py`

```python
"""
Regression Tests: Compara exports atuais com golden files

Previne regressões após mudanças em parsers/matchers.
"""

import pytest
from pathlib import Path
import json
from src.bp.parsers.dispatcher import ParseyCaller

GOLDEN_DIR = Path("tests/golden")

def test_real_life_golden():
    """Valida que Real Life.xlsx ainda extrai as mesmas contas"""
    
    # Parse atual
    current = ParseyCaller(Path("src/bp/training/DFS_Exemple/Balancete Real Life.xlsx")).parse()
    
    # Carrega golden (esperado)
    golden_path = GOLDEN_DIR / "real_life_accounts.json"
    if not golden_path.exists():
        # Primeira execução: cria golden
        golden_path.parent.mkdir(exist_ok=True)
        golden = [
            {
                'codigo': a.get('codigo'),
                'descricao': a.get('descricao'),
                'saldo': float(a.get('saldo', 0)),
                'nivel': a.get('nivel')
            }
            for a in current
        ]
        with open(golden_path, 'w', encoding='utf-8') as f:
            json.dump(golden, f, indent=2, ensure_ascii=False)
        pytest.skip("Golden file created, re-run test")
    
    with open(golden_path, encoding='utf-8') as f:
        golden = json.load(f)
    
    # Comparação
    assert len(current) == len(golden), f"Account count mismatch: {len(current)} vs {len(golden)}"
    
    for i, (curr, gold) in enumerate(zip(current, golden)):
        assert curr.get('descricao') == gold['descricao'], \
            f"Account {i}: description mismatch"
        assert abs(float(curr.get('saldo', 0)) - gold['saldo']) < 0.01, \
            f"Account {i}: saldo mismatch"
```

---

### **FASE 3: Integração no CI/CD (30 min)**

#### 3.1. Configurar pytest para rodar E2E

**Arquivo:** `pyproject.toml`

```toml
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests (fast, isolated)",
    "integration: Integration tests (slower, uses real files)",
    "e2e: End-to-end tests (slowest, full pipeline)",
]

# Rodar testes por categoria
# pytest -m unit  # Apenas unitários
# pytest -m "unit or integration"  # Unit + Integration
# pytest  # Todos (incluindo E2E)
```

#### 3.2. Marcar Testes

```python
# Em test_parsers.py
@pytest.mark.unit
def test_csv_parser_validate():
    ...

# Em test_e2e_export.py
@pytest.mark.e2e
def test_full_export_pipeline():
    ...
```

---

### **FASE 4: Melhorias no Export (1 hora)**

#### 4.1. Validação Preventiva no Export

```python
def export_balance_sheet_to_xlsx(
    input_path: Path,
    output_path: Path,
    ...
) -> Path:
    """Exporta com validação preventiva"""
    
    # Parse
    accounts = ParseyCaller(input_path).parse()
    
    # VALIDAÇÃO PREVENTIVA (NOVO)
    from src.bp.validators.export_schema import validate_parsed_accounts
    validation = validate_parsed_accounts(accounts)
    
    if not validation.valid:
        error_msg = f"Cannot export {input_path.name}: " + "; ".join(validation.errors)
        raise ValueError(error_msg)
    
    # Log warnings
    if validation.warnings:
        import warnings
        for w in validation.warnings:
            warnings.warn(w)
    
    # Continua export normalmente...
    ignored_set = _load_ignore(training_dir)
    _match_accounts(accounts, matcher, ignored_set)
    # ...
```

#### 4.2. Timeout Robusto no XlsParser

```python
def _try_libreoffice_conversion(self) -> Optional[pd.DataFrame]:
    """Com timeout e fallback mais robusto"""
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,  # 30s timeout
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        
        # NOVO: Verifica se conversão foi bem-sucedida
        if result.returncode != 0:
            warnings.warn(f"LibreOffice conversion failed with code {result.returncode}")
            return None
            
    except subprocess.TimeoutExpired:
        warnings.warn(f"LibreOffice conversion timeout (30s) for {self.file_path.name}")
        return None
    except Exception as e:
        warnings.warn(f"LibreOffice conversion error: {e}")
        return None
```

---

## 📅 CRONOGRAMA DE IMPLEMENTAÇÃO

| Fase | Tarefas | Tempo | Bloqueante? |
|------|---------|-------|-------------|
| **FASE 1** | Criar EXPORT_CONTRACT.md | 20min | ✅ Sim |
| | Criar export_schema.py | 40min | ✅ Sim |
| **FASE 2** | Criar test_e2e_export.py | 90min | ✅ Sim |
| | Criar test_export_regression.py | 30min | 🟡 Não |
| **FASE 3** | Configurar markers pytest | 10min | 🟡 Não |
| | Marcar testes existentes | 20min | 🟡 Não |
| **FASE 4** | Adicionar validação no export | 30min | ✅ Sim |
| | Melhorar timeout XlsParser | 30min | ✅ Sim |

**Total Crítico:** ~3h30min  
**Total Completo:** ~4h20min

---

## 🎯 CRITÉRIOS DE SUCESSO

### Objetivos Imediatos
- [ ] Todos os arquivos do CORPUS passam em `test_parse_produces_exportable_accounts`
- [ ] Todos os arquivos do CORPUS passam em `test_full_export_pipeline`
- [ ] Nenhum export gera arquivo vazio sem erro
- [ ] XlsParser não trava mais de 30s

### Objetivos de Longo Prazo
- [ ] Golden files criados para todos os arquivos principais
- [ ] CI/CD roda E2E tests em todo commit
- [ ] Coverage E2E > 80%
- [ ] Zero regressões em exports após mudanças

---

## 🔄 NOVO WORKFLOW DE DESENVOLVIMENTO

```
┌─────────────────────────────────────────────────┐
│ 1. ESCREVER TESTE E2E PRIMEIRO                  │
│    test_full_export_pipeline(novo_arquivo)      │
│    ❌ FALHA (red)                               │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 2. IMPLEMENTAR/CORRIGIR PARSER                  │
│    Ajustar detector de colunas, validações, etc │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 3. RODAR TESTE E2E                              │
│    pytest tests/test_e2e_export.py -v           │
│    ✅ PASSA (green)                             │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 4. VALIDAR EXPORT MANUALMENTE (opcional)        │
│    Abrir .xlsx e verificar visualmente          │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 5. COMMIT COM CONFIANÇA                         │
│    git commit -m "feat: suporte para X"         │
│    CI/CD roda todos testes E2E                  │
└─────────────────────────────────────────────────┘
```

---

## 🚀 PRÓXIMOS PASSOS

### Implementação Imediata (Fase 1 + 2)
1. Criar `docs/EXPORT_CONTRACT.md`
2. Criar `src/bp/validators/__init__.py` e `export_schema.py`
3. Criar `tests/test_e2e_export.py`
4. Rodar testes E2E: `pytest tests/test_e2e_export.py -v`
5. Corrigir falhas até todos passarem

### Melhorias (Fase 3 + 4)
6. Configurar pytest markers em `pyproject.toml`
7. Adicionar validação preventiva em `xlsx_exporter.py`
8. Melhorar timeout em `xls_parser.py`
9. Criar `tests/test_export_regression.py`
10. Gerar golden files para regressão

---

## 📝 NOTAS DE IMPLEMENTAÇÃO

### Arquivos Problemáticos Conhecidos
- `Balancete Real Life.xls` - Formato corrompido, usar `.xlsx`
- Arquivos com LibreOffice timeout - Fallback para Excel COM ou openpyxl

### Decisões de Design
- **Validação preventiva**: Melhor falhar rápido com erro claro que gerar arquivo vazio
- **Timeout de 30s**: Equilíbrio entre arquivos grandes legítimos e conversões travadas
- **Golden files**: Opcionais mas recomendados para prevenir regressões
- **Markers pytest**: Permite rodar subsets (unit/integration/e2e) durante desenvolvimento

### Métricas de Qualidade
- **Parse success rate**: >95% dos arquivos corpus
- **Export completeness**: 100% dos arquivos parseados exportam sem erro
- **Match rate**: >50% para arquivos com plano de contas
- **Test coverage**: >80% E2E
