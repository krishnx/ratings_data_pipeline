from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.config import settings
from api.db.session import get_session
from api.models.orm import FactCompanySnapshot, UploadAudit
from api.models.schemas import UploadDetailOut, UploadListItemOut, UploadListPageOut, UploadStatsOut
from api.pipeline.loader import DatabaseFileStore

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.get("", summary="List all ingested files", response_model=UploadListPageOut)
def list_uploads(
        page: int = Query(1, ge=1),
        page_size: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
        session: Session = Depends(get_session),
):
    total = session.query(func.count(UploadAudit.id)).scalar()
    rows = (
        session.query(UploadAudit)
        .order_by(UploadAudit.uploaded_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        UploadListItemOut(
            id=row.id,
            filename=row.filename,
            uploaded_at=row.uploaded_at,
            pipeline_run_id=row.pipeline_run_id,
            byte_size=row.byte_size,
            validation_status=row.validation_status,
        )
        for row in rows
    ]
    return UploadListPageOut(total=total, page=page, page_size=page_size, items=items)


@router.get("/stats", summary="Aggregated upload and pipeline statistics", response_model=UploadStatsOut)
def get_upload_stats(session: Session = Depends(get_session)):
    total = session.query(UploadAudit).count()
    passed = session.query(UploadAudit).filter(UploadAudit.validation_status == "passed").count()
    warnings = session.query(UploadAudit).filter(UploadAudit.validation_status == "passed_with_warnings").count()
    failed = session.query(UploadAudit).filter(UploadAudit.validation_status == "failed").count()

    sector_rows = (
        session.query(FactCompanySnapshot.corporate_sector, func.count().label("cnt"))
        .filter(FactCompanySnapshot.valid_to.is_(None), FactCompanySnapshot.corporate_sector.isnot(None))
        .group_by(FactCompanySnapshot.corporate_sector)
        .all()
    )
    currency_rows = (
        session.query(FactCompanySnapshot.reporting_currency, func.count().label("cnt"))
        .filter(FactCompanySnapshot.valid_to.is_(None), FactCompanySnapshot.reporting_currency.isnot(None))
        .group_by(FactCompanySnapshot.reporting_currency)
        .all()
    )
    country_rows = (
        session.query(FactCompanySnapshot.country_of_origin, func.count().label("cnt"))
        .filter(FactCompanySnapshot.valid_to.is_(None), FactCompanySnapshot.country_of_origin.isnot(None))
        .group_by(FactCompanySnapshot.country_of_origin)
        .all()
    )

    return UploadStatsOut(
        files_processed=total,
        files_passed=passed,
        files_with_warnings=warnings,
        files_failed=failed,
        by_sector={r.corporate_sector: r.cnt for r in sector_rows},
        by_currency={r.reporting_currency: r.cnt for r in currency_rows},
        by_country={r.country_of_origin: r.cnt for r in country_rows},
    )


@router.get("/{upload_id}/details", summary="Upload detail with validation report", response_model=UploadDetailOut)
def get_upload_details(upload_id: int, session: Session = Depends(get_session)):
    row = session.query(UploadAudit).filter(UploadAudit.id == upload_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Upload with id={upload_id} does not exist")
    return UploadDetailOut(
        id=row.id,
        filename=row.filename,
        uploaded_at=row.uploaded_at,
        pipeline_run_id=row.pipeline_run_id,
        byte_size=row.byte_size,
        validation_status=row.validation_status,
        validation_report=row.validation_report,
    )


@router.get("/{upload_id}/file", summary="Download the original .xlsm file")
def download_file(upload_id: int, session: Session = Depends(get_session)):
    try:
        file_bytes = DatabaseFileStore(session).load(upload_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File for upload id={upload_id} not found")

    audit = session.query(UploadAudit).filter(UploadAudit.id == upload_id).one()
    return Response(
        content=file_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{audit.filename}"'},
    )
