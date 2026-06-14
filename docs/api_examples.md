# API Examples

All examples target `http://localhost:8000`. Start the stack with:

```bash
cd src && docker compose up --build
```

---

## Health

```bash
curl -s http://localhost:8000/health | jq .
```

```json
{"status": "ok", "db": "connected"}
```

---

## Companies

### List all companies (paginated, current snapshot per company)

```bash
curl -s "http://localhost:8000/companies?page=1&page_size=10" | jq .
```

```json
{
  "total": 4,
  "page": 1,
  "page_size": 10,
  "items": [
    {
      "company_id": 1,
      "entity_name": "Company A",
      "corporate_sector": "Automobiles & Parts",
      "reporting_currency": "EUR",
      "country_of_origin": "Germany",
      "snapshot_id": 3,
      "valid_from": "2024-01-15T10:29:55.108000",
      "version_number": 2,
      "business_risk_profile": "BB+",
      "financial_risk_profile": "B+"
    }
  ]
}
```

### Get a single company (latest snapshot with full detail)

```bash
curl -s http://localhost:8000/companies/1 | jq .
```

```json
{
  "snapshot_id": 3,
  "company_id": 1,
  "entity_name": "Company A",
  "corporate_sector": "Automobiles & Parts",
  "rating_methodologies": ["General Corporate Rating Methodology"],
  "reporting_currency": "EUR",
  "country_of_origin": "Germany",
  "accounting_principles": "IFRS",
  "business_year_end_month": "December",
  "business_risk_profile": "BB+",
  "blended_industry_risk_profile": "BB",
  "competitive_positioning": "BB+",
  "market_share": "BB",
  "diversification": "BB+",
  "operating_profitability": "BB+",
  "sector_specific_factor_1": "BB",
  "sector_specific_factor_2": null,
  "financial_risk_profile": "B+",
  "leverage": "B+",
  "interest_cover": "BB-",
  "cash_flow_cover": "B+",
  "liquidity_adjustment": "+1 notch",
  "valid_from": "2024-01-15T10:29:55.108000",
  "valid_to": null,
  "version_number": 2,
  "industry_segments": [
    {
      "segment_order": 0,
      "industry_name": "Automobiles & Parts",
      "industry_risk_profile": "BB",
      "weight": 0.7
    },
    {
      "segment_order": 1,
      "industry_name": "Consumer Electronics",
      "industry_risk_profile": "BB+",
      "weight": 0.3
    }
  ],
  "credit_metrics": [
    {
      "year": 2019,
      "revenue": 15200.5,
      "ebitda_margin": 12.3,
      "debt_to_ebitda": 3.1,
      "interest_coverage": 4.2,
      "free_cash_flow": 820.0,
      "capex_to_revenue": 5.1
    },
    {
      "year": 2020,
      "revenue": 14800.0,
      "ebitda_margin": 10.1,
      "debt_to_ebitda": 3.8,
      "interest_coverage": 3.5,
      "free_cash_flow": 610.0,
      "capex_to_revenue": 6.0
    }
  ]
}
```

### Get all SCD2 versions for a company (paginated)

```bash
curl -s "http://localhost:8000/companies/1/versions?page=1&page_size=10" | jq .
```

```json
{
  "total": 2,
  "page": 1,
  "page_size": 10,
  "items": [
    {
      "snapshot_id": 1,
      "version_number": 1,
      "valid_from": "2023-06-01T09:00:00",
      "valid_to": "2024-01-15T10:29:55.105000"
    },
    {
      "snapshot_id": 3,
      "version_number": 2,
      "valid_from": "2024-01-15T10:29:55.108000",
      "valid_to": null
    }
  ]
}
```

### Get company credit metric history (paginated time-series)

```bash
curl -s "http://localhost:8000/companies/1/history?page=1&page_size=10" | jq .
```

```json
{
  "total": 2,
  "page": 1,
  "page_size": 10,
  "items": [
    {
      "snapshot_id": 1,
      "version_number": 1,
      "valid_from": "2023-06-01T09:00:00",
      "valid_to": "2024-01-15T10:29:55.105000",
      "credit_metrics": [
        {"year": 2018, "revenue": 13900.0, "ebitda_margin": 11.2, "debt_to_ebitda": 3.5, "interest_coverage": 3.9, "free_cash_flow": 700.0, "capex_to_revenue": 5.5}
      ]
    },
    {
      "snapshot_id": 3,
      "version_number": 2,
      "valid_from": "2024-01-15T10:29:55.108000",
      "valid_to": null,
      "credit_metrics": [
        {"year": 2019, "revenue": 15200.5, "ebitda_margin": 12.3, "debt_to_ebitda": 3.1, "interest_coverage": 4.2, "free_cash_flow": 820.0, "capex_to_revenue": 5.1}
      ]
    }
  ]
}
```

### Point-in-time comparison of two companies

```bash
curl -s "http://localhost:8000/companies/compare?company_ids=1,2&as_of_date=2024-01-01" | jq .
```

```json
{
  "as_of_date": "2024-01-01T00:00:00",
  "companies": [
    {
      "company_id": 1,
      "entity_name": "Company A",
      "snapshot_id": 1,
      "valid_from": "2023-06-01T09:00:00",
      "valid_to": "2024-01-15T10:29:55.105000",
      "corporate_sector": "Automobiles & Parts",
      "business_risk_profile": "BB+",
      "financial_risk_profile": "B+"
    },
    {
      "company_id": 2,
      "entity_name": "Company B",
      "snapshot_id": 2,
      "valid_from": "2023-06-01T09:00:00",
      "valid_to": null,
      "corporate_sector": "Personal & Household Goods",
      "business_risk_profile": "BBB-",
      "financial_risk_profile": "BB"
    }
  ]
}
```

---

## Snapshots

### List snapshots with pagination and filters

```bash
curl -s "http://localhost:8000/snapshots?page=1&page_size=10&sector=Automobiles+%26+Parts" | jq .
```

```json
{
  "total_count": 1,
  "items": [
    {
      "id": 3,
      "company_id": 1,
      "entity_name": "Company A",
      "corporate_sector": "Automobiles & Parts",
      "reporting_currency": "EUR",
      "country_of_origin": "Germany",
      "valid_from": "2024-01-15T10:29:55.108000",
      "valid_to": null,
      "version_number": 2
    }
  ]
}
```

The `X-Total-Count` response header is also set for BI tool integration:

```bash
curl -sI "http://localhost:8000/snapshots?page=1&page_size=10" | grep -i x-total-count
# X-Total-Count: 4
```

### Filter by date range

```bash
curl -s "http://localhost:8000/snapshots?from_date=2024-01-01&to_date=2024-12-31" | jq .total_count
```

```
2
```

### Latest snapshot per company (paginated)

```bash
curl -s "http://localhost:8000/snapshots/latest?page=1&page_size=10" | jq .
```

```json
{
  "total_count": 2,
  "items": [
    {"id": 3, "entity_name": "Company A", "valid_from": "2024-01-15T10:29:55.108000", "valid_to": null},
    {"id": 4, "entity_name": "Company B", "valid_from": "2024-01-15T10:29:55.211000", "valid_to": null}
  ]
}
```

### Get a specific snapshot by ID

```bash
curl -s http://localhost:8000/snapshots/3 | jq '{entity_name, version_number, valid_to}'
```

```json
{
  "entity_name": "Company A",
  "version_number": 2,
  "valid_to": null
}
```

---

## Uploads

### List all uploads (paginated)

```bash
curl -s "http://localhost:8000/uploads?page=1&page_size=10" | jq .
```

```json
{
  "total": 2,
  "page": 1,
  "page_size": 10,
  "items": [
    {"id": 2, "filename": "Company_B_Ratings.xlsm", "validation_status": "passed_with_warnings", "uploaded_at": "2024-01-15T10:29:55.204000"},
    {"id": 1, "filename": "Company_A_Ratings.xlsm", "validation_status": "passed",  "uploaded_at": "2024-01-15T10:29:55.101000"}
  ]
}
```

### Upload stats (aggregated counts)

```bash
curl -s http://localhost:8000/uploads/stats | jq .
```

```json
{
  "files_processed": 2,
  "files_passed": 1,
  "files_with_warnings": 1,
  "files_failed": 0,
  "by_sector": {"Automobiles & Parts": 1, "Personal & Household Goods": 1},
  "by_currency": {"EUR": 2},
  "by_country": {"Germany": 1, "Netherlands": 1}
}
```

### Upload detail with validation report

```bash
curl -s http://localhost:8000/uploads/2/details | jq '{filename, validation_status, validation_report}'
```

```json
{
  "filename": "Company_B_Ratings.xlsm",
  "validation_status": "passed_with_warnings",
  "validation_report": {
    "passed": false,
    "completeness_pct": 100.0,
    "validity_pct": 93.75,
    "errors": [],
    "warnings": [
      {
        "rule_id": "R12",
        "rule_name": "currency_iso",
        "level": "WARNING",
        "message": "Reporting currency 'XYZ' is not a recognised ISO-4217 code",
        "field": "reporting_currency",
        "value": "XYZ"
      }
    ]
  }
}
```

### Download the raw .xlsm file

```bash
curl -s -OJ http://localhost:8000/uploads/1/file
# Saves as: Company_A_Ratings.xlsm
```

---

## OpenAPI / Docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
