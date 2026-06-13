from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session, joinedload

from api.config import settings
from api.db.session import get_session
from api.models.orm import DimCompany, FactCompanySnapshot
from api.models.schemas import CompanySnapshotOut, SnapshotListItemOut, SnapshotListOut
from api.routers.companies import _snapshot_to_dict

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


def _to_list_item(snapshot: FactCompanySnapshot, entity_name: str) -> SnapshotListItemOut:
    return SnapshotListItemOut(
        id=snapshot.id,
        company_id=snapshot.company_id,
        entity_name=entity_name,
        version_number=snapshot.version_number,
        valid_from=snapshot.valid_from,
        valid_to=snapshot.valid_to,
        corporate_sector=snapshot.corporate_sector,
        reporting_currency=snapshot.reporting_currency,
        country_of_origin=snapshot.country_of_origin,
        business_risk_profile=snapshot.business_risk_profile,
        financial_risk_profile=snapshot.financial_risk_profile,
    )


@router.get("", summary="List snapshots with optional filters", response_model=SnapshotListOut)
def list_snapshots(
    response: Response,
    company_id: int | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    sector: str | None = Query(None),
    country: str | None = Query(None),
    currency: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    session: Session = Depends(get_session),
) -> SnapshotListOut:
    q = session.query(FactCompanySnapshot, DimCompany.entity_name).join(
        DimCompany, DimCompany.id == FactCompanySnapshot.company_id
    )
    if company_id is not None:
        q = q.filter(FactCompanySnapshot.company_id == company_id)
    if from_date is not None:
        q = q.filter(FactCompanySnapshot.valid_from >= from_date)
    if to_date is not None:
        q = q.filter(FactCompanySnapshot.valid_from <= to_date)
    if sector is not None:
        q = q.filter(FactCompanySnapshot.corporate_sector == sector)
    if country is not None:
        q = q.filter(FactCompanySnapshot.country_of_origin == country)
    if currency is not None:
        q = q.filter(FactCompanySnapshot.reporting_currency == currency)

    total_count = q.count()
    rows = q.order_by(FactCompanySnapshot.valid_from.desc()).offset((page - 1) * page_size).limit(page_size).all()

    response.headers["X-Total-Count"] = str(total_count)
    return SnapshotListOut(
        total_count=total_count,
        items=[_to_list_item(s, name) for s, name in rows],
    )


@router.get("/latest", summary="Latest snapshot for each company", response_model=SnapshotListOut)
def get_latest_snapshots(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    session: Session = Depends(get_session),
) -> SnapshotListOut:
    base_query = (
        session.query(FactCompanySnapshot, DimCompany.entity_name)
        .join(DimCompany, DimCompany.id == FactCompanySnapshot.company_id)
        .filter(FactCompanySnapshot.valid_to.is_(None))
    )
    total_count = base_query.count()
    rows = base_query.order_by(DimCompany.entity_name).offset((page - 1) * page_size).limit(page_size).all()
    return SnapshotListOut(
        total_count=total_count,
        items=[_to_list_item(snapshot, name) for snapshot, name in rows],
    )


@router.get(
    "/{snapshot_id}",
    summary="Full snapshot detail including segments and metrics",
    response_model=CompanySnapshotOut,
)
def get_snapshot(snapshot_id: int, session: Session = Depends(get_session)) -> CompanySnapshotOut:
    snapshot = (
        session.query(FactCompanySnapshot)
        .options(
            joinedload(FactCompanySnapshot.company),
            joinedload(FactCompanySnapshot.industry_segments),
            joinedload(FactCompanySnapshot.credit_metrics),
        )
        .filter(FactCompanySnapshot.id == snapshot_id)
        .one_or_none()
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Snapshot with id={snapshot_id} does not exist")
    return CompanySnapshotOut(**_snapshot_to_dict(snapshot, snapshot.company.entity_name))
