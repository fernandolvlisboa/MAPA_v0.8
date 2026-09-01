# Guia de Uso — Sistema de Treinamento

## 🎯 Objetivo

Treinar o sistema de matching processando balancetes reais, filtrando automaticamente contas analíticas (fornecedores específicos, c/c bancárias) e aprendendo variações de descrição.

---

## 📁 Estrutura

```
src/bp/training/
├── DFS_Exemple/              # ← VOCÊ ADICIONA BALANCETES AQUI
│   ├── balancete_jan.csv
│   ├── balancete_fev.xlsx
│   └── ...
├── processed_files.json      # Tracking de processados
├── training_cache.json       # Cache de matching
├── account_variations.json   # Variações aprendidas ✨
├── learned_patterns.json     # Padrões (sinônimos)
├── training_stats.json       # Estatísticas
├── trainer.py                # Classe principal
└── train.py                  # Script de execução
```

---

## 🚀 Como Usar

### 1. Adicione Balancetes

Copie seus arquivos CSV ou Excel para `src/bp/training/DFS_Exemple/`:

```bash
cp meus_balancetes/*.csv src/bp/training/DFS_Exemple/
cp meus_balancetes/*.xlsx src/bp/training/DFS_Exemple/
```

**Formatos suportados:**
- `.csv` (UTF-8)
- `.xlsx` / `.xls`

**Estrutura esperada:**
- Colunas: `codigo`, `descricao`, `saldo` (mínimo)
- Hierarquia no código: `1.1.01.01.001`

### 2. Execute o Treinamento

```bash
python src/bp/training/train.py
```

**O que acontece:**
1. ✅ Identifica arquivos NOVOS (não processados)
2. ✅ Filtra contas **analíticas** automaticamente
3. ✅ Realiza matching de contas **sintéticas**
4. ✅ Aprende variações de descrição
5. ✅ Atualiza todos os JSONs
6. ✅ Gera relatório em `output/training_report.md`

### 3. Adicione Mais e Re-execute

```bash
# Adiciona novos balancetes
cp balancete_mar.csv src/bp/training/DFS_Exemple/

# Re-executa (processa APENAS novos)
python src/bp/training/train.py
```

**Sistema é incremental:** Não reprocessa arquivos já vistos.

---

## 📊 Exemplo de Saída

```
================================================================================
SISTEMA DE TREINAMENTO — Aprendizado de Padrões
================================================================================

[1] Arquivos novos encontrados: 2
  • balancete_jan.csv
  • balancete_fev.xlsx

[2] Processando arquivos...
  Processando: balancete_jan.csv
    Total: 150 | Sintéticas: 120 | Analíticas filtradas: 30
  Processando: balancete_fev.xlsx
    Total: 155 | Sintéticas: 125 | Analíticas filtradas: 30

[3] Atualizando estatísticas...

[4] Salvando resultados...

================================================================================
RELATÓRIO DE TREINAMENTO
================================================================================
Arquivos processados: 2
Contas totais: 305
Contas sintéticas: 245
Contas analíticas filtradas: 60
Matched: 220 (89.8%)
Precisam revisão: 25 (10.2%)

Variações aprendidas: 85 códigos
Sinônimos identificados: 12
Total acumulado: 8 arquivos processados
================================================================================

✓ Relatório exportado: output/training_report.md
```

---

## 🔍 O Que é Filtrado (Analítico)

Contas **ignoradas** automaticamente:

❌ **CNPJ/CPF:**
```
FORNECEDOR - ACME CORP LTDA (CNPJ: 12.345.678/0001-90)
```

❌ **Conta Corrente:**
```
Banco Itaú - Ag 1234 C/C 56789-0
```

❌ **Tipo Societário:**
```
CLIENTE - EMPRESA XPTO S/A
```

❌ **Nível > 5:**
```
1.1.01.01.01.001.002 (7 níveis)
```

---

## ✅ O Que é Usado (Sintético)

Contas **processadas** para treino:

✅ **Grupos/Totalizadores:**
```
1.1.01.01.01 | Bancos Conta Movimento
1.1.02.01 | Fornecedores Nacionais
2.1.01 | Obrigações Trabalhistas
```

---

## 📈 Como as Variações São Usadas

### 1. Durante o Treinamento

Sistema registra em `account_variations.json`:

```json
{
  "1.1.01.01.01": {
    "variations": [
      "caixa",
      "caixa geral",
      "disponibilidades caixa",
      "bancos conta movimento"
    ],
    "frequency": 45
  }
}
```

### 2. No Matching (Automático)

ContaMatcher **carrega automaticamente** as variações e:

- ✅ Adiciona ao fuzzy matching
- ✅ Aplica boost baseado em frequência
- ✅ Melhora matching de descrições não-padrão

**Exemplo:**

```python
# Antes do treinamento
matcher.match("Bancos Mov.")  # → 0.75 (needs_review)

# Depois do treinamento (aprendeu "bancos mov" → 1.1.01.01.02)
matcher.match("Bancos Mov.")  # → 0.87 (auto-aceita)
```

---

## 🛠️ Uso Programático

```python
from src.bp.training import AccountTrainer

# Inicializa
trainer = AccountTrainer()

# Treina
result = trainer.train()

print(f"Processados: {result['processed']}")
print(f"Match rate: {result['match_rate']:.1f}%")

# Exporta relatório
trainer.export_report("output/training_report.md")

# Estatísticas
stats = trainer.get_stats_summary()
print(f"Total arquivos: {stats['total_files']}")
print(f"Variações: {stats['learned_variations']}")
```

---

## 📝 Arquivos Gerados

| Arquivo | Descrição |
|---------|-----------|
| `processed_files.json` | Lista de arquivos processados (tracking) |
| `training_cache.json` | Cache isolado de matching para treino |
| `account_variations.json` | Variações aprendidas (**usado pelo matcher**) |
| `learned_patterns.json` | Sinônimos e padrões identificados |
| `training_stats.json` | Estatísticas acumuladas por sessão |
| `output/training_report.md` | Relatório completo em Markdown |

---

## ⚙️ Configuração Avançada

### Thresholds de Matching

```python
trainer = AccountTrainer()
trainer.matcher.auto_accept_threshold = 0.90  # Mais rigoroso
trainer.matcher.requery_threshold = 0.70

trainer.train()
```

### Reset Completo

```python
trainer = AccountTrainer()
trainer.reset()  # Limpa TUDO (cuidado!)
```

---

## 🎯 Workflow Recomendado

### Inicial (Setup)

1. ✅ Adicione 5-10 balancetes representativos
2. ✅ Execute `python src/bp/training/train.py`
3. ✅ Revise `output/training_report.md`
4. ✅ Verifique `account_variations.json`

### Contínuo (Manutenção)

1. ✅ Adicione novos balancetes periodicamente
2. ✅ Re-execute treinamento (processa apenas novos)
3. ✅ Sistema aprende continuamente
4. ✅ Matching melhora com o tempo

---

## ✅ Checklist

- [ ] Balancetes adicionados em `DFS_Exemple/`
- [ ] Executei `python src/bp/training/train.py`
- [ ] Revisei `output/training_report.md`
- [ ] Match rate > 85% (bom desempenho)
- [ ] `account_variations.json` populado
- [ ] Matching melhorou em novos PDFs

---

## 🐛 Troubleshooting

### Nenhum arquivo processado

```
✓ Nenhum arquivo novo encontrado
  Total processados: 0
```

**Solução:** Adicione arquivos em `src/bp/training/DFS_Exemple/`

### Erro ao parsear arquivo

```
❌ Erro ao parsear: ...
```

**Causas:**
- Encoding incorreto (use UTF-8)
- Colunas faltando (`codigo`, `descricao`)
- Formato Excel corrompido

### Match rate muito baixo (<70%)

**Soluções:**
1. Verifique se plano de contas é adequado
2. Adicione mais balancetes para treino
3. Ajuste thresholds (reduzir `auto_accept_threshold`)

---

**Sistema de Treinamento Implementado!** 🎉

---

## 🧭 Revisão Interativa (Wizard)

Quando o relatório indicar contas que “precisam de revisão”, use o assistente interativo para classificar e ensinar o sistema.

### Executar (Windows PowerShell)

```powershell
# Usando o Python do ambiente virtual do projeto
C:/Users/FernandoLuizdeVascon/Desktop/PyhtonProjects/BP/.venv/Scripts/python.exe -m src.bp.training.review_wizard --all

# Ou revise um arquivo específico
C:/Users/FernandoLuizdeVascon/Desktop/PyhtonProjects/BP/.venv/Scripts/python.exe -m src.bp.training.review_wizard --file "src/bp/training/DFS_Exemple/MeuBalancete.xlsx"

# Limitar aos primeiros N itens (ex.: 10)
C:/Users/FernandoLuizdeVascon/Desktop/PyhtonProjects/BP/.venv/Scripts/python.exe -m src.bp.training.review_wizard --all --limit 10
```

### Comandos no assistente

- `s`: Buscar candidatos por descrição (fuzzy)
- `h`: Navegar por hierarquia (Ativo → Circulante → ...)
- `c`: Informar código manualmente (ex.: `1.01.01.02.01`)
- `i`: Ignorar permanentemente (ruído específico — não volta a aparecer)
- `k`: Pular nesta sessão (pode reaparecer futuramente)
- `q`: Sair do assistente

Cada decisão é salva no `training_cache.json` como manual e também alimenta `account_variations.json` para melhorar o matching futuro.

### Ignorando Ruídos Permanentes

Use `i` quando a descrição for muito específica (ex.: nome de software interno, apelido de banco em um único balancete) e NÃO quiser que ela influencie o aprendizado.

Isso grava a versão normalizada em `training_ignore.json`. O treinamento e o wizard passam a ignorar essas descrições (não entram em variações, nem em revisão futura).

Após algumas decisões, reexecute o treinamento para validar a melhora do match rate:

```powershell
C:/Users/FernandoLuizdeVascon/Desktop/PyhtonProjects/BP/.venv/Scripts/python.exe src/bp/training/train.py
```

