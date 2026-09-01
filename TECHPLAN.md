# TECHPLAN — Parsers CSV, PDF, TXT, XLS, XLSX

## Executive Summary
A unified, secure, and observable parsing platform for CSV, PDF, TXT, XLS, and XLSX with a standard output contract, isolation, timeouts, streaming for large files, and reliable handling of legacy `.xls`. We prioritize native libraries and headless conversion; Excel COM is isolated and used only as a last resort with regression tests. Success criteria: ≥90% success per format on the corpus, p95 latency within SLAs, and ≥85% automated test coverage.

## High-Level Objectives & Targets
- Security: sandboxed parsing, macro detection/rejection, path sanitization.
- Performance: streaming/chunking (CSV/TXT), controlled concurrency, per-file timeouts.
- Observability: structured logs with `job_id`/`correlation_id`, Prometheus metrics, traces.
- Reliability: retries with backoff for transient I/O; clear policies for irrecoverable files.
- Compatibility: encoding autodetect; BIFF `.xls`, modern `.xlsx`; PDF native/scan (OCR).
- Maintainability: unified output contract; modular parsers; documented versions & APIs.
- Usability: CLI/HTTP orchestration; human-friendly error reports.
- Testability: unit/integration/fuzz; CI with coverage and performance baselines.

### Measurable Goals (KPIs)
- Success rate per format on corpus: ≥90%.
- Test coverage: ≥85% lines/branches.
- p95 latency: CSV/TXT ≤2s per 50MB; PDF ≤10s per OCR job; XLS/XLSX ≤5s per file.
- Error budget: failures ≤10% per hour; alert when exceeded.
- COM fallback usage: ≤5% of `.xls` jobs; headless conversion preferred.

## Unified Output Contract (JSON)
Same as `README.md` section; all parsers return the `ParserResult` schema.

## Format-Specific Specifications
Refer to `README.md` sections 4 (CSV/PDF/TXT/XLS/XLSX). Each includes:
- Essential characteristics (8–12)
- Failure modes (≥8)
- Typical weaknesses to avoid (≥6)
- Strengths/guarantees (≥6)
- Test requirements (≥8 cases)

## Critical `.xls` Strategy
- Diagnosis: COM pitfalls (global dispatch, visible app, closing Application), BIFF quirks, macros/links.
- Corrections: (1) Native libs + headless conversion (preferred). (2) COM isolated with `DispatchEx`, invisible, strict lifecycle. (3) Hybrid pipeline with circuit-breaker.
- Regression tests: ensure other workbooks remain open; no visible UI; exceptions don’t kill Application; sequence processing without leaks; macro detection without execution.

## Phased Roadmap & Milestones

### Phase A — Discovery & Preparation (Days 1–3)
- Inventory current parsers and dependencies.
- Collect problematic samples, esp. `.xls` closing other workbooks.
- Run parser checklist; identify security/observability gaps.
- Deliverables: gap report; curated corpus list; initial metrics plan.

### Phase B — Critical Fixes (Days 4–10)
- Implement unified `ParserResult` contract (done: `src/bp/parsers/result.py`).
- `.xls`: headless conversion pipeline; COM isolated fallback; backups before conversion.
- Implement per-file timeouts; memory limits; structured logging with IDs.
- Deliverables: `xls_converter` script; `XlsParser` with COM isolation; logging hooks.
- Milestone: `.xls` baseline success ≥80% on corpus without closing other workbooks.

### Phase C — Robustness & Normalization (Days 11–24)
- CSV/TXT: streaming with chunking; delimiter/encoding autodetect; schema inference.
- PDF: OCR detection + Tesseract pipeline in isolated worker; table heuristics.
- XLSX: formula/value policy; dates/number normalization; merges handling.
- Policies: password-protected files fail-fast; macros detected/rejected.
- Deliverables: parser modules updated; config flags; isolation via process pool.
- Milestone: per-format success ≥90%; p95 latencies within SLAs.

### Phase D — Testing & Hardening (Days 25–34)
- Build corpus (≥20 files) + synthetic generators; fuzz CSV/PDF/XLS.
- Integration tests via dispatcher; performance and crash-recovery tests.
- CI pipeline: coverage, linters, benchmarks snapshot.
- Deliverables: `tests/` suites, CI config, coverage reports.
- Milestone: coverage ≥85%; stability under stress/concurrency.

### Phase E — Observability & Operation (Days 35–40)
- Expose Prometheus metrics; dashboards & alerts.
- Operational docs: how to debug, add new parsers, run conversion safely.
- Rollout: canary per format; feature flags for COM/OCR.
- Deliverables: metrics exporters, dashboards JSON, runbooks.
- Milestone: on-call ready with alerts; rollback plan validated.

## Dependencies & Management
- Python libs: `pandas`, `openpyxl`, `pdfplumber`, `camelot`/`tabula`, `tesseract` (OCR), `pywin32` (optional), `libreoffice` for conversion.
- Manage via `pyproject.toml`; validate native deps at startup; containerize OCR/conversion workers.

## Test Plan & Corpora
- Mandatory cases (≥30) across formats (see README 7): encodings, delimiters, huge files, OCR, BIFF, macros, passwords, truncation, stress.
- Corpus: ≥20 curated examples + synthetic generators stored under `tests/corpora/` with metadata.
- Fuzzing: random delimiter/encoding perturbations; truncations; layout merges.
- Acceptance: success ≥90% per format; coverage ≥85%; p95 latency within SLAs.

## Observability & Operation
- Metrics: `jobs_processed_total`, `jobs_failed_total`, `avg_latency_seconds{format}`, `retry_count`, `memory_usage_mb`, `ocr_runs_total`.
- Logs: `timestamp`, `level`, `job_id`, `correlation_id`, `format`, `source_path`, `duration_ms`, `error_code`, `message`.
- Alerts: failure rate >10%/h; p95 latency breaches; OCR/COM unavailable; corpus missing.
- Rollback & Recovery: disable COM via flags; revert conversion route; requeue with backoff.

## Security & Sanitation
- Reject macros by default; flag OLE; sandbox parsing; backups before mutation; path validation; least privileges; network/FS limits.

## Concrete Deliverables
- Parsers (csv/pdf/txt/xls/xlsx), dispatcher, `ParserResult`, conversion script, CLI/HTTP wrapper, corpus, tests (unit/integration/fuzz), CI pipeline, dashboards.
- Quality bars: contract compliance; coverage ≥85%; linters clean; docs & examples; metrics live.

## Evaluation Rubric
- Completude 25%; Técnica 25%; Testes 20%; Segurança/Robustez 15%; Clareza 10%; Tempo 5%.

## Risks & Mitigations (10+)
- Unknown encodings → autodetect + fallback.
- PDF images only → OCR with timeouts.
- `.xls` COM instability → prefer headless; `DispatchEx` isolated.
- Password files → explicit failure path.
- Insufficient corpus → expand and fuzz.
- Native deps missing → startup checks; clear errors.
- COM leaks → strict try/finally; monitoring.
- High latency → streaming & parallelism tuning.
- Network/storage glitches → retries/backoff.
- Malicious content → sandbox; validation.

## Rollout & Maintenance
- Gradual rollout with canary; feature flags for OCR/COM; concurrency limits.
- Maintenance: onboarding docs; contracts stable; versioning; mandatory regression tests for new formats.

---
Participants: BP Parsers Team
Estimated time: 20–40 person-days
PR metadata: include participants, time spent, and summary (≤300 words)
