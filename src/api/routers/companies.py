from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from api.config import settings
from api.db.session import get_session
from api.models.orm import DimCompany, FactCompanySnapshot
from api.models.schemas import (
    CompanyListItemOut,
    CompanyListPageOut,
    CompanySnapshotOut,
    CompanySnapshotPageOut,
    CompareOut,
)

router = APIRouter(prefix="/companies", tags=["companies"])


def _snapshot_to_dict(snapshot: FactCompanySnapshot, entity_name: str) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "company_id": snapshot.company_id,
        "entity_name": entity_name,
        "version_number": snapshot.version_number,
        "valid_from": snapshot.valid_from,
        "valid_to": snapshot.valid_to,
        "corporate_sector": snapshot.corporate_sector,
        "reporting_currency": snapshot.reporting_currency,
        "country_of_origin": snapshot.country_of_origin,
        "accounting_principles": snapshot.accounting_principles,
        "business_year_end_month": snapshot.business_year_end_month,
        "segmentation_criteria": snapshot.segmentation_criteria,
        "business_risk_profile": snapshot.business_risk_profile,
        "blended_industry_risk_profile": snapshot.blended_industry_risk_profile,
        "competitive_positioning": snapshot.competitive_positioning,
        "market_share": snapshot.market_share,
        "diversification": snapshot.diversification,
        "operating_profitability": snapshot.operating_profitability,
        "sector_specific_factor_1": snapshot.sector_specific_factor_1,
        "sector_specific_factor_2": snapshot.sector_specific_factor_2,
        "financial_risk_profile": snapshot.financial_risk_profile,
        "leverage": snapshot.leverage,
        "interest_cover": snapshot.interest_cover,
        "cash_flow_cover": snapshot.cash_flow_cover,
        "liquidity_adjustment": snapshot.liquidity_adjustment,
        "rating_methodologies": snapshot.rating_methodologies or [],
        "industry_segments": [
            {
                "index": seg.segment_index,
                "industry_name": seg.industry_name,
                "risk_score": seg.risk_score,
                "weight": float(seg.weight),
            }
            for seg in snapshot.industry_segments
        ],
        "credit_metrics": [
            {
                "year": metric.metric_year,
                "ebitda_interest_cover": metric.ebitda_interest_cover,
                "debt_ebitda": metric.debt_ebitda,
                "ffo_debt": metric.ffo_debt,
                "loan_value": metric.loan_value,
                "focf_debt": metric.focf_debt,
                "liquidity": metric.liquidity,
            }
            for metric in snapshot.credit_metrics
        ],
    }


@router.get("", summary="List all companies with their current snapshot", response_model=CompanyListPageOut)
def list_companies(
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        default=settings.default_page_size, ge=1, le=settings.max_page_size, description="Items per page"
    ),
    session: Session = Depends(get_session),
) -> CompanyListPageOut:
    base_query = (
        session.query(FactCompanySnapshot, DimCompany.entity_name)
        .join(DimCompany, DimCompany.id == FactCompanySnapshot.company_id)
        .filter(FactCompanySnapshot.valid_to.is_(None))
    )
    total = (
        session.query(func.count(FactCompanySnapshot.id))
        .join(DimCompany, DimCompany.id == FactCompanySnapshot.company_id)
        .filter(FactCompanySnapshot.valid_to.is_(None))
        .scalar()
    )
    rows = base_query.order_by(DimCompany.entity_name).offset((page - 1) * page_size).limit(page_size).all()
    items = [
        CompanyListItemOut(
            id=snapshot.id,
            company_id=snapshot.company_id,
            entity_name=name,
            version_number=snapshot.version_number,
            valid_from=snapshot.valid_from,
            corporate_sector=snapshot.corporate_sector,
            reporting_currency=snapshot.reporting_currency,
            country_of_origin=snapshot.country_of_origin,
            business_risk_profile=snapshot.business_risk_profile,
            financial_risk_profile=snapshot.financial_risk_profile,
        )
        for snapshot, name in rows
    ]
    return CompanyListPageOut(total=total, page=page, page_size=page_size, items=items)


@router.get("/compare", summary="Compare multiple companies at a point in time", response_model=CompareOut)
def compare_companies(
    company_ids: str = Query(..., description="Comma-separated company IDs"),
    as_of_date: datetime | None = Query(None, description="ISO 8601 date (defaults to now)"),
    session: Session = Depends(get_session),
) -> CompareOut:
    if not company_ids.strip():
        raise HTTPException(status_code=400, detail="company_ids must not be empty")

    try:
        ids: list[int] = [int(part.strip()) for part in company_ids.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="company_ids must be comma-separated integers")

    if not ids:
        raise HTTPException(status_code=400, detail="company_ids must not be empty")

    as_of: datetime = as_of_date or datetime.now(timezone.utc)

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
    for snapshot in snapshots:
        if snapshot.company_id not in seen:
            seen.add(snapshot.company_id)
            unique.append(snapshot)

    return CompareOut(
        as_of_date=as_of,
        companies=[
            CompanySnapshotOut(**_snapshot_to_dict(snapshot, snapshot.company.entity_name)) for snapshot in unique
        ],
    )


@router.get("/{company_id}", summary="Get latest snapshot for a company", response_model=CompanySnapshotOut)
def get_company(company_id: int, session: Session = Depends(get_session)) -> CompanySnapshotOut:
    snapshot = (
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
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Company with id={company_id} does not exist")
    return CompanySnapshotOut(**_snapshot_to_dict(snapshot, snapshot.company.entity_name))


@router.get(
    "/{company_id}/versions",
    summary="All versions for a company (SCD2 history)",
    response_model=CompanySnapshotPageOut,
)
def get_company_versions(
    company_id: int,
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        default=settings.default_page_size, ge=1, le=settings.max_page_size, description="Items per page"
    ),
    session: Session = Depends(get_session),
) -> CompanySnapshotPageOut:
    company = session.query(DimCompany).filter(DimCompany.id == company_id).one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company with id={company_id} does not exist")

    total = (
        session.query(func.count(FactCompanySnapshot.id)).filter(FactCompanySnapshot.company_id == company_id).scalar()
    )
    snapshots = (
        session.query(FactCompanySnapshot)
        .options(
            joinedload(FactCompanySnapshot.industry_segments),
            joinedload(FactCompanySnapshot.credit_metrics),
        )
        .filter(FactCompanySnapshot.company_id == company_id)
        .order_by(FactCompanySnapshot.valid_from)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [CompanySnapshotOut(**_snapshot_to_dict(snapshot, company.entity_name)) for snapshot in snapshots]
    return CompanySnapshotPageOut(total=total, page=page, page_size=page_size, items=items)


@router.get(
    "/{company_id}/history",
    summary="Time-series history with credit metrics",
    response_model=CompanySnapshotPageOut,
)
def get_company_history(
    company_id: int,
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        default=settings.default_page_size, ge=1, le=settings.max_page_size, description="Items per page"
    ),
    session: Session = Depends(get_session),
) -> CompanySnapshotPageOut:
    company = session.query(DimCompany).filter(DimCompany.id == company_id).one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company with id={company_id} does not exist")

    total = (
        session.query(func.count(FactCompanySnapshot.id)).filter(FactCompanySnapshot.company_id == company_id).scalar()
    )
    snapshots = (
        session.query(FactCompanySnapshot)
        .options(
            joinedload(FactCompanySnapshot.industry_segments),
            joinedload(FactCompanySnapshot.credit_metrics),
        )
        .filter(FactCompanySnapshot.company_id == company_id)
        .order_by(FactCompanySnapshot.valid_from)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [CompanySnapshotOut(**_snapshot_to_dict(snapshot, company.entity_name)) for snapshot in snapshots]
    return CompanySnapshotPageOut(total=total, page=page, page_size=page_size, items=items)
