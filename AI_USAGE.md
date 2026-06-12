# AI Usage Disclosure

## Tools Used

| Tool | Version / Access | Purpose |
|------|-----------------|---------|
| Claude (Anthropic) | `claude-sonnet-4-6` via Claude Code CLI | Architecture planning, schema design, code generation, test writing, review |

## Components with AI Assistance

| Component | AI Tool | Nature of Assistance |
|-----------|---------|---------------------|
| `data_main/PLAN.md` | Claude | Full architecture design: star schema, SCD2, index strategy, SOLID patterns, test pyramid |
| `src/migrations/init.sql` | Claude | DDL with materialized views, covering indexes, BRIN, GIN, partial indexes, generated tsvector column |
| `src/api/pipeline/extractor.py` | Claude | MASTER sheet parsing algorithm, all 9 edge cases (EC-1..9), label normalization, SHA-256 idempotency |
| `src/api/pipeline/validator.py` | Claude | 16-rule validation framework (R01–R16), RULE_REGISTRY pattern, ValidationReport structure |
| `src/api/pipeline/transformer.py` | Claude | DomainRecord transformation, month normalization, float coercion |
| `src/api/pipeline/loader.py` | Claude | SCD2 close-out logic, atomic 7-table transaction scope |
| `src/api/pipeline/runner.py` | Claude | Orchestration, retry with exponential backoff, idempotency gate, data lineage recording, materialized view refresh |
| `src/api/models/orm.py` | Claude | SQLAlchemy 2.0 ORM models, ARRAY/JSONB/TSVECTOR column types, relationships |
| `src/api/routers/*.py` | Claude | FastAPI endpoint design, point-in-time SCD2 queries, pagination, binary download |
| `src/api/main.py` | Claude | FastAPI lifespan hook, structured JSON logging, global exception handler |
| `src/docker-compose.yml` | Claude | Multi-service orchestration, PostgreSQL tuning parameters, healthcheck config |
| `src/tests/` | Claude | All unit, integration, e2e, and performance tests; fixture design; OpenAPI completeness gate |
| `docs/` | Claude | API examples with real responses, sample data quality report, pipeline execution log |

## What Claude Did and Did Not Do

Claude Code (the CLI tool) was used throughout to write, review, and iterate on all source code. The code was not copy-pasted from a training corpus — Claude reasoned about the specific Excel structure of the provided `.xlsm` files, the PostgreSQL incompatibilities between partitioning and generated columns, and the edge cases in the data (EC-1 through EC-9) before writing code.

Human judgement was applied to:
- Directing Claude to move code from `data_main/` to `src/` after the initial incorrect placement
- Reviewing architectural choices (e.g. rejecting partitioning due to FK + generated column incompatibilities)
- Deciding not to use Alembic, Celery, Redis, or authentication per the README non-goals

## Evidence

This project was built using Claude Code CLI in an interactive session. The full conversation transcript is stored locally at:

```
~/.claude/projects/-Users-<user>-projects-ratings-data-pipeline/
```

The session involved two main phases:
1. Planning phase: Claude read all four `.xlsm` source files and produced `data_main/PLAN.md` with detailed schema, index justifications, and edge case analysis
2. Implementation phase: Claude built the full `src/` tree following the plan, with one correction (moved code from `data_main/` to `src/` after user instruction)

> Personal information has been redacted per README guidance. Chat logs available on request.
