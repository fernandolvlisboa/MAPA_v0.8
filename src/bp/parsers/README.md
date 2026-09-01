# Parsers — Módulo de Leitura de Balanços

Implementação completa de parsers para ler balanços patrimoniais em múltiplos formatos.

## 📦 Parsers Disponíveis

### 1. **ExcelParser** (`.xlsx`, `.xls`)
Parser para arquivos Excel com detecção automática de colunas.

**Características:**
- ✅ Detecção automática de abas
- ✅ Mapeamento inteligente de colunas (código, descrição, saldo, natureza)
- ✅ Suporte para múltiplas abas
- ✅ Tratamento de valores numéricos brasileiros (1.234,56)

**Exemplo:**
```python
from src.bp.parsers import ExcelParser

parser = ExcelParser("balanco.xlsx")
resultado = parser.parse()

print(f"Total de contas: {len(resultado.contas)}")
for conta in resultado.contas:
    print(f"{conta['codigo']} - {conta['descricao']}: R$ {conta['saldo']}")
```

### 2. **CSVParser** (`.csv`)
Parser para arquivos CSV com auto-detecção de delimitador.

**Características:**
- ✅ Auto-detecção de delimitador (`,`, `;`, `|`, tab)
- ✅ Suporte para múltiplas codificações (UTF-8, Latin1, etc)
- ✅ Mapeamento inteligente de colunas
- ✅ Tratamento robusto de valores

**Exemplo:**
```python
from src.bp.parsers import CSVParser

parser = CSVParser("balanco.csv")  # Auto-detecta delimitador
resultado = parser.parse()

print(f"Delimitador: {resultado.metadata['delimiter']}")
print(f"Total de contas: {len(resultado.contas)}")
```

### 3. **PDFParser** (`.pdf`)
Parser para arquivos PDF usando extração de tabelas.

**Características:**
- ✅ Extração de tabelas com pdfplumber
- ✅ Processamento de múltiplas páginas
- ✅ Detecção automática de cabeçalhos
- ✅ Suporte para páginas específicas

**Exemplo:**
```python
from src.bp.parsers import PDFParser

# Processar todas as páginas
parser = PDFParser("balanco.pdf")

# Ou páginas específicas
parser = PDFParser("balanco.pdf", page_numbers=[0, 1, 2])

resultado = parser.parse()
print(f"Páginas processadas: {resultado.metadata['total_paginas']}")
```

### 4. **TXTParser** (`.txt`)
Parser para arquivos texto estruturados.

**Características:**
- ✅ Auto-detecção de separador (tab, espaços, pipe, ponto-e-vírgula)
- ✅ Suporte para colunas de largura fixa
- ✅ Detecção automática de cabeçalhos
- ✅ Robusto contra linhas mal formatadas

**Exemplo:**
```python
from src.bp.parsers import TXTParser

parser = TXTParser("balanco.txt")
resultado = parser.parse()

print(f"Tipo de separador: {resultado.metadata['separator_type']}")
print(f"Total de contas: {len(resultado.contas)}")
```

## 🏗️ Arquitetura

Todos os parsers herdam de `BaseParser` e implementam:

- `validate()`: Valida se o arquivo é legível
- `parse()`: Extrai contas e retorna `ParseResult`

### Formato de Saída Padronizado

Todos os parsers retornam objetos `ParseResult` com:

```python
{
    "contas": [
        {
            "codigo": str,        # Código da conta (opcional)
            "descricao": str,     # Descrição (obrigatório)
            "saldo": float,       # Saldo/valor (opcional)
            "natureza": str,      # "Devedora" ou "Credora" (opcional)
            "tipo": str,          # "ATIVO", "PASSIVO", etc (opcional)
            "fonte": str          # Nome do arquivo de origem
        }
    ],
    "metadata": {
        "fonte": str,
        "caminho": str,
        "tamanho_bytes": int,
        "data_modificacao": str,
        # ... metadados específicos de cada parser
    }
}
```

## 🧪 Testes

Todos os parsers possuem testes completos:

```bash
# Executar testes dos parsers
uv run pytest tests/test_parsers.py -v

# Executar todos os testes
uv run pytest tests/ -v
```

**Cobertura de Testes:**
- ✅ 15 testes para parsers
- ✅ Validação de arquivos
- ✅ Parsing de contas
- ✅ Detecção de delimitadores/separadores
- ✅ Normalização de valores
- ✅ Testes de integração

## 📊 Demonstração

Execute o script de demonstração para ver todos os parsers em ação:

```bash
uv run python auxil/demo_parsers.py
```

## 🔧 Funcionalidades Comuns

### Normalização de Saldos

Todos os parsers normalizam valores automaticamente:

```python
# Formatos brasileiros
"1.234,56"     → 1234.56
"R$ 1.000,00"  → 1000.0
"10.000,50"    → 10000.5

# Valores numéricos
1234.56        → 1234.56
0              → 0.0

# Valores inválidos
"abc"          → 0.0
None           → 0.0
""             → 0.0
```

### Detecção Inteligente de Colunas

Os parsers detectam automaticamente as colunas usando padrões:

| Tipo | Palavras-chave |
|------|----------------|
| **Código** | codigo, código, conta, cod, code |
| **Descrição** | descricao, descrição, description, nome, name, titulo |
| **Saldo** | saldo, valor, value, montante, total |
| **Natureza** | natureza, tipo, d/c, dc |

### Extração de Metadados

Todos os parsers extraem automaticamente:
- Nome do arquivo fonte
- Caminho completo
- Tamanho em bytes
- Data de modificação

## 🚀 Próximos Passos

**Fase 4 (Próxima):** Matching + AI
- Implementar FuzzyMatcher usando rapidfuzz
- Integrar com PlanodeContas para classificação
- Implementar fallback para API de AI
- Sistema de confiança (auto_accept > 0.85, requery < 0.60)

**Fase 5:** CLI + Exporters + Validators
- Interface de linha de comando
- Exportadores (Excel, JSON, CSV)
- Validadores de balanço

## 📝 Arquivos de Exemplo

Exemplos de balanços criados em `data/examples/`:
- `balanco_exemplo.xlsx` - Excel
- `balanco_exemplo.csv` - CSV com delimitador `;`
- `balanco_exemplo.txt` - TXT com separação por tabs

Execute para recriar:
```bash
uv run python data/examples/create_parser_samples.py
```

## ✅ Status da Fase 3

- ✅ BaseParser (interface abstrata)
- ✅ ExcelParser (pandas)
- ✅ CSVParser (auto-detect delimiter)
- ✅ PDFParser (pdfplumber)
- ✅ TXTParser (multi-format)
- ✅ Testes completos (15 testes)
- ✅ Arquivos de exemplo
- ✅ Script de demonstração
- ✅ Documentação

**Total de Linhas de Código:** ~1.200 linhas
**Testes Passando:** 28/28 ✅
