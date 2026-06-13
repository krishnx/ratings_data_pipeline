# Corporate Credit Rating Data Pipeline

A FastAPI service that ingests corporate credit rating data from `.xlsm` files, validates and transforms it, and exposes a paginated REST API backed by PostgreSQL.

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start — Docker](#quick-start--docker)
- [Local Development Setup](#local-development-setup)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)

---

## Architecture

```
.xlsm files (data/)
        │
        ▼
  ┌─────────────┐     ┌───────────┐     ┌─────────────┐     ┌────────┐
  │  Extractor  │────▶│ Validator │────▶│ Transformer │────▶│ Loader │
  └─────────────┘     └───────────┘     └─────────────┘     └────────┘
                                                                  │
                                                                  ▼
                                                           PostgreSQL
                                                                  │
                                                                  ▼
                                                           FastAPI REST API
```

**Pipeline stages:**

| Stage | Description |
|---|---|
| Extract | Reads the `MASTER` sheet from each `.xlsm`, maps raw labels to canonical fields |
| Validate | Runs 16 rules (R01–R16); errors block load, warnings annotate |
| Transform | Normalises strings, months, weights; produces a clean `DomainRecord` |
| Load | Writes to `dim_company`, `fact_company_snapshot`, `fact_industry_segment`, `fact_credit_metric_year`; records lineage |

---

## Prerequisites

| Tool | Version |
|---|---|
| Docker | 24+ |
| Docker Compose | v2 (bundled with Docker Desktop) |
| Python | 3.13 (for local dev) |

---

## Quick Start — Docker

```bash
# 1. Clone the repo
git clone git@github.com:krishnx/ratings_data_pipeline.git
cd ratings_data_pipeline

# 2. Place .xlsm data files
mkdir -p data
cp /path/to/your/*.xlsm data/

# 3. Start the stack
cd src
docker compose up --build
```

The API will be available at **http://localhost:8000** once the health check passes.  
Interactive docs: **http://localhost:8000/docs**

To stop and clean up:

```bash
docker compose down -v
```

---

## Local Development Setup

```bash
cd src

# Create and activate a virtual environment
python3.13 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r api/requirements.txt

# Start a local PostgreSQL (using the test compose file)
docker compose -f docker-compose.test.yml up -d postgres

# Apply the schema
# (the container runs migrations/init.sql automatically on first start)

# Set environment variables
export DATABASE_URL="postgresql+psycopg://ratings:ratings@localhost:5432/ratings"
export DATA_DIR="../data"

# Run the API
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Configuration

All settings are read from environment variables (or a `.env` file placed in `src/`):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://ratings:ratings@localhost:5432/ratings` | SQLAlchemy connection string |
| `DATA_DIR` | `/data` | Directory scanned for `.xlsm` files at startup |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `DEFAULT_PAGE_SIZE` | `100` | Default number of items per page |
| `MAX_PAGE_SIZE` | `1000` | Upper bound for `page_size` query param |
| `POSTGRES_DB` | `ratings` | Database name (Docker Compose only) |
| `POSTGRES_USER` | `ratings` | Database user (Docker Compose only) |
| `POSTGRES_PASSWORD` | `ratings` | Database password (Docker Compose only) |

---

## API Reference

All list endpoints support `?page=<n>&page_size=<n>` (default: 100, max: 1000).

### Health

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Returns `{"status": "ok", "db": "connected"}` |

### Companies

| Method | Path | Description |
|---|---|---|
| GET | `/companies` | Paginated list of companies (current snapshot per company) |
| GET | `/companies/{company_id}` | Full snapshot detail for a company |
| GET | `/companies/{company_id}/versions` | Paginated SCD2 version history |
| GET | `/companies/{company_id}/history` | Paginated time-series snapshots with credit metrics |
| GET | `/companies/compare` | Side-by-side comparison; params: `company_ids` (CSV), `as_of_date` |

**Paginated response shape (`/companies`):**
```json
{
  "total": 12,
  "page": 1,
  "page_size": 100,
  "items": [{ "company_id": 1, "entity_name": "...", ... }]
}
```

### Snapshots

| Method | Path | Description |
|---|---|---|
| GET | `/snapshots` | Filtered, paginated list; params: `company_id`, `from_date`, `to_date`, `sector`, `country`, `currency` |
| GET | `/snapshots/latest` | Paginated list — one current snapshot per company |
| GET | `/snapshots/{snapshot_id}` | Full snapshot including industry segments and credit metrics |

`GET /snapshots` also returns an `X-Total-Count` response header for BI tools.

**Paginated response shape (`/snapshots`):**
```json
{
  "total_count": 24,
  "items": [{ "id": 1, "entity_name": "...", ... }]
}
```

### Uploads

| Method | Path | Description |
|---|---|---|
| GET | `/uploads` | Paginated list of all ingested files |
| GET | `/uploads/{upload_id}/details` | Upload record with full validation report |
| GET | `/uploads/{upload_id}/file` | Download the original `.xlsm` file |
| GET | `/uploads/stats` | Aggregated pipeline metrics by sector, currency, country |

**Paginated response shape (`/uploads`):**
```json
{
  "total": 4,
  "page": 1,
  "page_size": 100,
  "items": [{ "id": 1, "filename": "company_a.xlsm", ... }]
}
```

---

## Running Tests

### Unit tests (no database required)

```bash
cd src
python -m pytest tests/unit/ -v
```

### Integration tests (requires PostgreSQL)

```bash
# Start the test database
docker compose -f docker-compose.test.yml up -d postgres

# Run tests
TEST_DATABASE_URL="postgresql+psycopg://ratings:ratings@localhost:5432/ratings_test" \
  python -m pytest tests/integration/ -v

# Tear down
docker compose -f docker-compose.test.yml down
```

### All tests

```bash
TEST_DATABASE_URL="postgresql+psycopg://ratings:ratings@localhost:5432/ratings_test" \
  python -m pytest tests/unit/ tests/integration/ -v
```

### E2E tests (full Docker stack)

```bash
cd src
docker compose -f docker-compose.test.yml up --abort-on-container-exit --exit-code-from api
```

### Makefile shortcuts

```bash
make test-unit         # unit tests with coverage
make test-integration  # integration tests
make test              # unit + integration
make test-e2e          # full Docker e2e run
make lint              # flake8 + mypy
make format            # black + isort
```

---

## Project Structure

```
ratings_data_pipeline/
├── data/                          # .xlsm input files (gitignored)
├── docs/
│   ├── api_examples.md        # curl examples for every endpoint
│   └── data_quality_report_example.json
└── src/
    ├── docker-compose.yml          # production stack
    ├── docker-compose.test.yml     # test stack (isolated DB)
    ├── migrations/
    │   └── init.sql               # schema + indexes + materialized views
    ├── Makefile
    └── api/
        ├── Dockerfile
        ├── requirements.txt
        ├── config.py              # Settings (pydantic-settings, reads .env)
        ├── main.py                # FastAPI app + lifespan pipeline trigger
        ├── db/
        │   └── session.py         # SQLAlchemy engine + session factory
        ├── models/
        │   ├── orm.py             # SQLAlchemy ORM models
        │   └── schemas.py         # Pydantic request/response models
        ├── pipeline/
        │   ├── constants.py       # Shared constants (labels, patterns, limits)
        │   ├── extractor.py       # .xlsm → RawRecord
        │   ├── validator.py       # 16 validation rules → ValidationReport
        │   ├── transformer.py     # RawRecord → DomainRecord
        │   ├── loader.py          # DomainRecord → PostgreSQL
        │   ├── runner.py          # Orchestration, retry, lineage tracking
        │   └── exceptions.py      # MissingSheetError, ExtractionError
        └── routers/
            ├── companies.py       # /companies endpoints
            ├── snapshots.py       # /snapshots endpoints
            └── uploads.py         # /uploads endpoints
```
