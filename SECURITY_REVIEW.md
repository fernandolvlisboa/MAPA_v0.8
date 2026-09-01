# Security Review — BP

Varredura de segurança das mudanças da branch (Planos A–G + passe de qualidade).

## Escopo

- Todos os módulos Python novos/alterados em `src/bp/`.
- Arquivos de dados novos: `data/plano_referencial.json`,
  `data/plano_referencial_extra.json`, `data/accounting_synonyms.json`,
  `data/llm_mappings.json`, `output/review_worklist.csv`.
- Requisito do projeto: aplicação executável offline, sem chamadas externas.

## Achados

### Rede (100% offline — requisito atendido)

`grep -rInE "import requests|import urllib|import http|socket\.|urlopen|api_key|openai|anthropic|boto3" src/bp` → **zero ocorrências**. Nada sai da máquina; matching e treino são totalmente locais.

### Injeção de shell / código dinâmico

`grep -rnE "\beval\(|\bexec\(|pickle\.load|os\.system|shell=True"` → **zero**.

Único `subprocess.run` em `src/bp/parsers/xls_parser.py:180` (chamada ao `soffice --headless` para converter .xls → .xlsx):
- Usa forma-lista de argumentos (não interpretado por shell).
- Timeout de 30s (não pendura).
- `creationflags=CREATE_NO_WINDOW` no Windows (não abre janela).
- `self.file_path.absolute()` é o único input do usuário, passado como argumento — **não é interpretado como shell**.
- **Veredicto: seguro.**

### Deserialização insegura

- `yaml.load`: **zero uso**.
- 18 `json.load(s)` — todos sobre arquivos gerados/controlados pelo próprio projeto (plano de contas, cache de treino, variations). Nenhum consome JSON de rede/upload externo.
- `pickle.load`: **zero uso**.
- **Veredicto: seguro.**

### Path traversal

`open(f"...")` com input do usuário: **nenhum caso onde o usuário fornece diretamente uma string interpolada em path**. Todas as leituras são via `Path` construído a partir do argumento CLI ou do diretório `DFS_Exemple/`. **Veredicto: seguro** para o modelo de uso pretendido (o próprio colaborador escolhe o arquivo).

### Segredos em código

- Nenhum `api_key`, `secret`, `password`, `token` real no código-fonte.
- `xls_parser.py:256-257` passa `Password=""` intencionalmente para pywin32 abrir Excel sem prompt de senha — não é credencial, é a **ausência** de credencial (por design).
- Arquivos `.env` no `.gitignore`.
- **Veredicto: limpo.**

### Vazamento de PII nos dados aprendidos

O treino processa balancetes reais e grava JSONs versionados (`account_variations.json`, `learned_patterns.json`, `training_cache.json`). Risco: CNPJ/CPF/razão social vazando em variações aprendidas.

Scan: `grep -oE "CNPJ_pattern|CPF_pattern" src/bp/training/*.json data/*.json` → **zero ocorrências**.

Isso é garantido por três camadas defensivas do projeto:
- `AccountTrainer.is_analytical_level` filtra descrições com CNPJ/CPF/tipo societário via `_ANALYTICAL_RE` **antes** de aprender.
- `is_garbage_description` descarta linhas numéricas.
- Threshold de aprendizado (`auto_accept_threshold=0.85`) só absorve matches confiantes.

**Veredicto: limpo, com controles apropriados.**

### `assert` em produção (podem ser removidos por `python -O`)

`grep -rn "^\s*assert " src/bp` → **zero** (fora de testes). **Veredicto: ok.**

### `warnings.warn` sem `stacklevel`

11 pontos legados (não corrigidos porque `warnings.warn` retornam warning normal — só perde contexto do caller). Não é vulnerabilidade. Documentado em `pyproject.toml` — não bloqueia.

## Considerações de arquitetura de segurança

- **`llm_mappings.json`** carrega decisões vindas de um LLM. O
  `apply_llm_mappings` **valida cada entrada** contra o plano referencial
  (código existe? classe respeita?) e rejeita as inválidas. Ninguém consegue
  injetar um código arbitrário via esse arquivo.
- **`review_worklist.csv`** contém descrições de balancetes reais (pode ter
  nomes próprios). Está em `output/` — se `output/` for versionado, os
  balancetes reais dos clientes vazam no git. **Recomendação:** adicionar
  `output/` ao `.gitignore` **exceto** o `training_report.md`.
- O produto final (executável para colaboradores) empacota `plano_referencial*.json`
  e `account_variations.json` — auditados nesta revisão como limpos de PII.

## Recomendações

1. **Adicionar `output/` ao `.gitignore`** (exceto `training_report.md`) — evita
   que balancetes de clientes reais vazem em versionamento.
2. **Manter os filtros analíticos ligados** — são o que protege PII.
3. Ao embutir OCR na estação de curadoria (Plano G/futuro), garantir que os
   arquivos escaneados não fiquem no `output/` versionado.

## Veredicto geral

**Aprovado.** Nenhuma vulnerabilidade explorável encontrada. O único ajuste
recomendado é higienizar o `.gitignore` para evitar vazamento de dados reais
de clientes num commit descuidado.
