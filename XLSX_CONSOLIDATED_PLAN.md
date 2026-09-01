# XLS/XLSX Parser - CONSOLIDATED PLAN v2.0

## Executive Summary
XLS/XLSX parsing is CRITICAL. Previous approach achieved 100% success with preprocessing strategy. Now we consolidate learnings about **merged cells** and **description-first matching** into a robust, self-contained parser.

## Key Learnings from RBM & Real Life Files

### 🔍 Problem Discovered
1. **XLS files are often corrupted** → Solution: Convert to XLSX first (preprocessing)
2. **Merged cells create Unnamed columns** → Solution: Automatic compaction (unmerge → delete blanks → shift left)
3. **Different files have different structures:**
   - **RBM:** Código=lines, Unnamed:1=codes (1.1.1), Classificação=descriptions
   - **Real Life:** Código=lines, Unnamed:1=descriptions directly (no hierarchical codes)
4. **Description is MORE important than code** → Codes vary by company, descriptions are standardized

### 🎯 Core Principle
**"Description-First Strategy"**
- Descriptions are the PRIMARY data (universal, standardized)
- Codes are SECONDARY (company-specific, variable)
- Matching to plano_master is done BY DESCRIPTION → generates standard code
- This mirrors PDF/TXT behavior where descriptions are extracted first

## Architecture: 4-Tier Strategy

### Tier 1: Preprocessing (XLS → XLSX Conversion)
**Status:** ✅ PRODUCTION READY (100% success on 7 files)

**Tool:** `convert_xls_to_xlsx.py`
- One-time batch conversion
- Excel COM with process isolation
- Skips already-converted files
- **Result:** Clean .xlsx files ready for parsing

**Why:** XLS files often corrupted, XLSX is more reliable

### Tier 2: DataFrame Loading (XLSX → DataFrame)
**Status:** ✅ COMPLETE (ExcelParser)

**Method:** `ExcelParser.read()` or `XlsParser.read()`
- Uses openpyxl for XLSX
- Multi-strategy for XLS (LibreOffice → COM → openpyxl)
- Header inference automatic
- **Result:** Raw DataFrame with merged cells

### Tier 3: Merged Cell Compaction ⭐ NEW
**Status:** ✅ IMPLEMENTED in XlsParser, needs generalization

**Process:** Simulates manual Excel cleanup
```
1. Unmerge all cells (forward fill already done by openpyxl)
2. For each row:
   - Collect non-null values
   - Shift left (remove gaps)
   - Pad with NaN to original width
3. Drop completely empty columns
4. Result: Clean tabular structure
```

**Why:** Merged cells create Unnamed columns that break column detection

**Implementation Location:** 
- Should be in **ExcelParser** (not dispatcher)
- Applied after header detection
- Makes parser self-contained

### Tier 4: Description-First Parsing ⭐ REDESIGN
**Status:** 🔄 NEEDS REFACTORING

**New Logic:**
```python
# PRIORITY 1: Find DESCRIPTION column
descricao_col = find_column([
    "descrição", "descricao", "nome da conta",
    "classificação", "classificacao",  # Common in merged files
    "conta",  # May be combined
    # Then try first text-heavy Unnamed column
])

# PRIORITY 2: Find SALDO column (for validation)
saldo_col = find_column(["saldo", "saldo atual", "saldo final"]) 
    or last_numeric_column

# PRIORITY 3: Find CODIGO column (OPTIONAL - may not exist!)
codigo_col = find_column([
    "código", "codigo", "cod"
    # Then check for hierarchical pattern in Unnamed (X.X.X)
]) or None  # OK to be None!

# Build accounts
for row in df:
    descricao = row[descricao_col]  # ALWAYS required
    codigo = row[codigo_col] if codigo_col else descricao  # Fallback to description
    saldo = row[saldo_col] if saldo_col else 0
    
    # Calculate nivel from codigo structure (1→1, 1.1→2, 1.1.1→3)
    nivel = codigo.count('.') + 1 if '.' in codigo else 1
    
    account = {
        'codigo': codigo,  # May be description if no real code
        'descricao': descricao,  # PRIMARY field
        'saldo': saldo,
        'nivel': nivel
    }
```

**Key Changes:**
1. **Description is found FIRST** (not dependent on code)
2. **Code is OPTIONAL** (may not exist or be meaningful)
3. **No special-casing** for specific files (RBM vs Real Life)
4. **Self-contained logic** in dispatcher.parse()

## Implementation Plan

### Phase 1: Consolidate Compaction ✅ DONE
- [x] Compaction logic in XlsParser._compact_merged_columns()
- [x] Tested on RBM (16→7 columns, 537 accounts extracted)
- [x] Tested on Real Life (18→6 columns, 127 accounts extracted)

### Phase 2: Generalize Compaction 📋 TODO
- [ ] Move compaction to ExcelParser (shared by XLS/XLSX)
- [ ] Make it a standard post-processing step
- [ ] Configuration flag: `compact_merged_cells=True` (default)
- [ ] Update all parsers to apply compaction consistently

### Phase 3: Refactor Description-First Logic 📋 TODO
- [ ] Rewrite dispatcher.parse() with description priority
- [ ] Remove special-casing for sequential numbering
- [ ] Simplify column detection (description → saldo → code)
- [ ] Handle missing code gracefully (use description)
- [ ] Calculate nivel from actual code structure

### Phase 4: Validation & Testing 📋 TODO
- [ ] Test on all 7 corpus files
- [ ] Verify accounts extracted correctly
- [ ] Check description quality
- [ ] Validate nivel calculation
- [ ] Ensure no regressions

### Phase 5: Documentation 📋 TODO
- [ ] Update xls_PLAN.md with new architecture
- [ ] Document merged cell handling
- [ ] Explain description-first philosophy
- [ ] Update Full_Workflow.md

## Target Architecture (After Refactoring)

### ExcelParser (XLSX)
```python
class ExcelParser:
    def read(self) -> pd.DataFrame:
        df = pd.read_excel(...)
        df = self._detect_header(df)
        df = self._compact_merged_cells(df)  # NEW: Always compact
        return df
    
    def _compact_merged_cells(self, df):
        """Remove blank cells, shift left (Excel cleanup simulation)"""
        # Same logic as current XlsParser._compact_merged_columns()
```

### XlsParser (XLS)
```python
class XlsParser:
    def read(self) -> pd.DataFrame:
        # Multi-strategy: LibreOffice → COM → openpyxl
        df = self._try_libreoffice() or self._try_com() or self._try_openpyxl()
        df = self._detect_header(df)
        df = self._compact_merged_cells(df)  # Reuse ExcelParser logic
        return df
```

### ParseyCaller (Dispatcher)
```python
class ParseyCaller:
    def parse(self) -> List[Dict]:
        df = self.read()  # Clean, compacted DataFrame
        
        # DESCRIPTION-FIRST detection
        desc_col = self._find_description(df)  # PRIORITY 1
        saldo_col = self._find_saldo(df)       # PRIORITY 2
        codigo_col = self._find_codigo(df)     # PRIORITY 3 (optional)
        
        accounts = []
        for row in df:
            descricao = row[desc_col]
            codigo = row[codigo_col] if codigo_col else descricao
            saldo = row[saldo_col] if saldo_col else 0
            nivel = self._calculate_nivel(codigo)
            
            accounts.append({
                'codigo': codigo,
                'descricao': descricao,  # PRIMARY for matching
                'saldo': saldo,
                'nivel': nivel
            })
        
        return accounts
```

## Expected Results

### File Coverage (All 7 Files)
```
✅ RBM.xlsx:           537 accounts (hierarchical codes 1.1.1.01)
✅ Real Life.xlsx:     127 accounts (description-only, no hierarchy)
✅ 202404_2024.xlsx:   ??? accounts (TBD)
✅ 042025.xlsx:        ??? accounts (TBD)
✅ ASP 2023.xlsx:      ??? accounts (TBD)
✅ SPEZZIA.xlsx:       ??? accounts (TBD)
✅ 2025-06.xlsx:       ??? accounts (TBD)
```

### Quality Metrics
- **Success Rate:** 100% (all files parse)
- **Description Quality:** ≥95% meaningful descriptions
- **Code Preservation:** Hierarchical codes when present
- **Nivel Accuracy:** 100% (calculated from code structure)
- **No Special-Casing:** Same logic for all files

## Integration with Matching

### Current Flow (After Parsing)
```
1. Parse → Extract accounts with descriptions
2. AccountTrainer → Learn patterns
3. ContaMatcher → Match description to plano_master
4. Generate standard code from plano_master
```

### Why Description-First Matters
- **Company codes vary:** Company A uses "1.1.01", Company B uses "101"
- **Descriptions are universal:** "CAIXA GERAL" is "CAIXA GERAL" everywhere
- **Matching reliability:** Description matching >90%, code matching <50%
- **Plano_master provides standard codes:** Final output has normalized codes

## Success Criteria

### Must Have (P0)
- [ ] All 7 files parse successfully (100% rate maintained)
- [ ] Merged cells handled automatically (no manual preprocessing)
- [ ] Description-first logic works for all structures
- [ ] No file-specific special cases in code
- [ ] Performance: p95 ≤ 1s (already achieved)

### Should Have (P1)
- [ ] Comprehensive tests for merged cell scenarios
- [ ] Validation that descriptions are meaningful
- [ ] Graceful handling of missing codes
- [ ] Clear error messages for unparseable files

### Nice to Have (P2)
- [ ] Auto-detection of merged cell regions
- [ ] Confidence scores for column detection
- [ ] Suggestions when description column unclear
- [ ] Multi-sheet handling

## Migration Path

### Step 1: Create Test Suite
```python
# Test both structures
test_rbm()       # Hierarchical codes
test_real_life() # Description-only
test_all_7()     # Corpus validation
```

### Step 2: Refactor Incrementally
```
1. Move compaction to ExcelParser (shared)
2. Update XlsParser to use shared compaction
3. Refactor dispatcher description-first logic
4. Remove special-case code (sequential detection)
5. Test on all files
```

### Step 3: Validate & Document
```
1. Confirm 100% success rate maintained
2. Verify description quality
3. Update documentation
4. Deploy to production
```

## Timeline

- **Phase 1:** ✅ COMPLETE (compaction proof-of-concept)
- **Phase 2:** 2 hours (generalize compaction)
- **Phase 3:** 4 hours (refactor description-first)
- **Phase 4:** 2 hours (validation & testing)
- **Phase 5:** 1 hour (documentation)

**Total:** ~1 day of focused work

## Next Immediate Actions

1. **Create comprehensive test suite** with all 7 files
2. **Move compaction logic** to shared location (ExcelParser)
3. **Refactor dispatcher** with description-first approach
4. **Test & validate** on complete corpus
5. **Update documentation** (xls_PLAN.md, Full_Workflow.md)

---

## Conclusion

This consolidated plan transforms the parser from "file-specific" to "universal" by:

1. ✅ **Preprocessing** solves XLS corruption (already proven)
2. ⭐ **Compaction** solves merged cells (generalize existing code)
3. ⭐ **Description-first** solves varying code structures (new philosophy)
4. 🎯 **Self-contained parsers** eliminate special-casing (clean architecture)

**Result:** One robust parser handles ALL Excel files, regardless of structure.
