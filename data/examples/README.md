# 📁 `data/examples/` — Exemplos de Balanços para Enriquecimento

Esta pasta contém exemplos de balanços reais (ou anônimos) em diversos formatos. Esses exemplos são usados para:

1. **Treinar e validar parsers** — garantir que ExcelParser, PDFParser, etc. funcionam com formatos reais.
2. **Alimentar o plano de contas** — extrair contas novas/variações que possam enriquecer `plano_contas.json`.
3. **Testar matching** — validar fuzzy matching e heurísticas contra casos reais.

---

## 📋 Formatos Suportados

### Excel (`.xlsx`)
- **Estrutura esperada:**
  - Coluna 1: Código da conta (ex: `1`, `1.1`, `1.1.1`)
  - Coluna 2: Descrição (ex: `ATIVO`, `ATIVO CIRCULANTE`)
  - Coluna 3: Saldo/Valor (numérico)
  - Colunas adicionais: Natureza, Tipo, etc. (opcionais)
- **Exemplo de arquivo:**
  ```
  | Código | Descrição               | Saldo      | Natureza |
  |--------|-------------------------|------------|----------|
  | 1      | ATIVO                   | 100000.00  | Devedora |
  | 1.1    | ATIVO CIRCULANTE        | 50000.00   | Devedora |
  | 1.1.1  | CAIXA                   | 5000.00    | Devedora |
  ```
- **Nome do arquivo:** `balancete_[empresa]_[data].xlsx` ou `sample_plano.xlsx`

### PDF (`.pdf`)
- **Estrutura esperada:**
  - Tabela com colunas: Código, Descrição, Saldo, etc.
  - Pode ser um scanned PDF (com OCR) ou PDF digital (com texto)
- **Exemplo:**
  - PDFs de balanços publicados (DFPs, ITRs, etc.)
  - Balancetes em layout padrão SPED

### CSV (`.csv`)
- **Estrutura esperada:**
  - Delimitador: vírgula (`,`) ou ponto-e-vírgula (`;`)
  - Cabeçalho: `Codigo,Descricao,Saldo,Natureza`
  - Encoding: UTF-8
- **Exemplo:**
  ```csv
  Codigo,Descricao,Saldo,Natureza
  1,ATIVO,100000,Devedora
  1.1,ATIVO CIRCULANTE,50000,Devedora
  ```

### TXT (`.txt`)
- **Estrutura esperada:**
  - Arquivo delimitado por espaços ou tabs
  - Ou formato SPED específico
- **Exemplo:**
  ```
  1       ATIVO                   100000.00
  1.1     ATIVO CIRCULANTE         50000.00
  1.1.1   CAIXA                     5000.00
  ```

---

## 🔄 Pipeline de Ingestão

Quando você colocar arquivos nesta pasta e executar o script de ingestão:

```bash
python src/bp/generators/ingest_examples.py
```

O sistema irá:

1. **Ler cada arquivo** e aplicar o parser apropriado (baseado em extensão).
2. **Extrair contas** — consolidar descrições, códigos, saldos.
3. **Gerar relatório** — mostrar contas novas/variações encontradas.
4. **Sugerir merge** — propostas para atualizar `plano_contas.json` (com aprovação humana).
5. **Registrar auditoria** — log em `data/plano_audit.log` com origem, timestamp, etc.

---

## 📝 Convenção de Nomes

Recomendamos nomear arquivos de forma descritiva:

```
balancete_[empresa]_[periodo]_[ano].[formato]
sample_[setor].[formato]
exemplo_[tipo].[formato]
```

**Exemplos:**
- `balancete_acme_2025_q1.xlsx`
- `sample_banco.pdf`
- `exemplo_varejo.csv`
- `plano_simplificado.txt`

---

## 🎯 Passos para Adicionar Exemplos

1. **Copie/crie seu arquivo** (Excel, PDF, CSV ou TXT) e coloque nesta pasta.
2. **Anonimize dados sensíveis** se necessário (renomear empresas, CNPJ, etc.).
3. **Teste localmente** — rode `ingest_examples.py` e revise o relatório.
4. **Aprove/recuse** as sugestões de novas contas.
5. **Commit para Git** — registre a origem do exemplo (setor, tipo, período).

---

## 📊 Exemplos Inclusos (se houver)

| Arquivo | Formato | Setor | Descrição |
|---------|---------|-------|-----------|
| (nenhum) | — | — | Você pode começar adicionando exemplos! |

---

## 🔗 Referências

- [SPED — Sistema Público de Escrituração Digital](https://www.gov.br/receitafederal/pt-br/assuntos/obrigacoes-acessorias/sped)
- [CVM — Balanços Padronizados](https://www.cvm.gov.br/)
- [Plano de Contas BR (Base)](/data/plano_contas.json)

---

**Última atualização:** 28 de Novembro de 2025
