from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from api.db.session import get_session
from api.models.orm import DimCompany, FactCompanySnapshot
from api.models.schemas import CompanyListItemOut, CompanySnapshotOut, CompareOut

router = APIRouter(prefix="/companies", tags=["companies"])


def _snapshot_to_dict(s: FactCompanySnapshot, entity_name: str) -> dict:
    return {
        "id": s.id,
        "company_id": s.company_id,
        "entity_name": entity_name,
        "version_number": s.version_number,
        "valid_from": s.valid_from,
        "valid_to": s.valid_to,
        "corporate_sector": s.corporate_sector,
        "reporting_currency": s.reporting_currency,
        "country_of_origin": s.country_of_origin,
        "accounting_principles": s.accounting_principles,
        "business_year_end_month": s.business_year_end_month,
        "segmentation_criteria": s.segmentation_criteria,
        "business_risk_profile": s.business_risk_profile,
        "blended_industry_risk_profile": s.blended_industry_risk_profile,
        "competitive_positioning": s.competitive_positioning,
        "market_share": s.market_share,
        "diversification": s.diversification,
        "operating_profitability": s.operating_profitability,
        "sector_specific_factor_1": s.sector_specific_factor_1,
        "sector_specific_factor_2": s.sector_specific_factor_2,
        "financial_risk_profile": s.financial_risk_profile,
        "leverage": s.leverage,
        "interest_cover": s.interest_cover,
        "cash_flow_cover": s.cash_flow_cover,
        "liquidity_adjustment": s.liquidity_adjustment,
        "rating_methodologies": s.rating_methodologies or [],
        "industry_segments": [
            {"index": seg.segment_index, "industry_name": seg.industry_name,
             "risk_score": seg.risk_score, "weight": float(seg.weight)}
            for seg in s.industry_segments
        ],
        "credit_metrics": [
            {"year": m.metric_year, "ebitda_interest_cover": m.ebitda_interest_cover,
             "debt_ebitda": m.debt_ebitda, "ffo_debt": m.ffo_debt,
             "loan_value": m.loan_value, "focf_debt": m.focf_debt, "liquidity": m.liquidity}
            for m in s.credit_metrics
        ],
    }


@router.get("", summary="List all companies with their current snapshot", response_model=list[CompanyListItemOut])
def list_companies(session: Session = Depends(get_session)):
    rows = (
        session.query(FactCompanySnapshot, DimCompany.entity_name)
        .join(DimCompany, DimCompany.id == FactCompanySnapshot.company_id)
        .filter(FactCompanySnapshot.valid_to.is_(None))
        .order_by(DimCompany.entity_name)
        .all()
    )
    return [
        CompanyListItemOut(
            id=s.id,
            company_id=s.company_id,
            entity_name=name,
            version_number=s.version_number,
            valid_from=s.valid_from,
            corporate_sector=s.corporate_sector,
            reporting_currency=s.reporting_currency,
            country_of_origin=s.country_of_origin,
            business_risk_profile=s.business_risk_profile,
            financial_risk_profile=s.financial_risk_profile,
        )
        for s, name in rows
    ]


@router.get("/compare", summary="Compare multiple companies at a point in time", response_model=CompareOut)
def compare_companies(
    company_ids: str = Query(..., description="Comma-separated company IDs"),
    as_of_date: datetime | None = Query(None, description="ISO 8601 date (defaults to now)"),
    session: Session = Depends(get_session),
):
    if not company_ids.strip():
        raise HTTPException(status_code=400, detail="company_ids must not be empty")

    try:
        ids = [int(x.strip()) for x in company_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="company_ids must be comma-separated integers")

    if not ids:
        raise HTTPException(status_code=400, detail="company_ids must not be empty")

    as_of = as_of_date or datetime.now(timezone.utc)

    snapshots = (
        session.query(FactCompanySnapshot)
        .options(
            joinedload(FactCompanySnapshot.company),
            joinedload(FactCompanySnapshot.industry_segments),
            joinedload(FactCompanySnapshot.credit_metrics),
        )
        .filter(
            FactCompanySnapshot.company_id.in_(ids),
            FactCompanySnapshot.valid_from <= as_of,
            (FactCompanySnapshot.valid_to.is_(None)) | (FactCompanySnapshot.valid_to > as_of),
        )
        .order_by(FactCompanySnapshot.company_id, FactCompanySnapshot.valid_from.desc())
        .all()
    )

    seen: set[int] = set()
    unique: list[FactCompanySnapshot] = []
    for s in snapshots:
        if s.company_id not in seen:
            seen.add(s.company_id)
            unique.append(s)

    return CompareOut(
        as_of_date=as_of,
        companies=[CompanySnapshotOut(**_snapshot_to_dict(s, s.company.entity_name)) for s in unique],
    )


@router.get("/{company_id}", summary="Get latest snapshot for a company", response_model=CompanySnapshotOut)
def get_company(company_id: int, session: Session = Depends(get_session)):
    s = (
        session.query(FactCompanySnapshot)
        .options(
            joinedload(FactCompanySnapshot.company),
            joinedload(FactCompanySnapshot.industry_segments),
            joinedload(FactCompanySnapshot.credit_metrics),
        )
        .filter(
            FactCompanySnapshot.company_id == company_id,
            FactCompanySnapshot.valid_to.is_(None),
        )
        .one_or_none()
    )
    if s is None:
        raise HTTPException(status_code=404, detail=f"Company with id={company_id} does not exist")
    return CompanySnapshotOut(**_snapshot_to_dict(s, s.company.entity_name))


@router.get(
    "/{company_id}/versions",
    summary="All versions for a company (SCD2 history)",
    response_model=list[CompanySnapshotOut],
)
def get_company_versions(company_id: int, session: Session = Depends(get_session)):
    company = session.query(DimCompany).filter(DimCompany.id == company_id).one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company with id={company_id} does not exist")

    snapshots = (
        session.query(FactCompanySnapshot)
        .options(
            joinedload(FactCompanySnapshot.industry_segments),
            joinedload(FactCompanySnapshot.credit_metrics),
        )
        .filter(FactCompanySnapshot.company_id == company_id)
        .order_by(FactCompanySnapshot.valid_from)
        .all()
    )
    return [CompanySnapshotOut(**_snapshot_to_dict(s, company.entity_name)) for s in snapshots]


@router.get(
    "/{company_id}/history",
    summary="Time-series history with credit metrics",
    response_model=list[CompanySnapshotOut],
)
def get_company_history(company_id: int, session: Session = Depends(get_session)):
    company = session.query(DimCompany).filter(DimCompany.id == company_id).one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company with id={company_id} does not exist")

    snapshots = (
        session.query(FactCompanySnapshot)
        .options(
            joinedload(FactCompanySnapshot.industry_segments),
            joinedload(FactCompanySnapshot.credit_metrics),
        )
        .filter(FactCompanySnapshot.company_id == company_id)
        .order_by(FactCompanySnapshot.valid_from)
        .all()
    )
    return [CompanySnapshotOut(**_snapshot_to_dict(s, company.entity_name)) for s in snapshots]
