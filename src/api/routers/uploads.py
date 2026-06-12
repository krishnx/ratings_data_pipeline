from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.db.session import get_session
from api.models.orm import FactCompanySnapshot, UploadAudit, UploadFileStore
from api.models.schemas import UploadDetailOut, UploadListItemOut, UploadStatsOut

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.get("", summary="List all ingested files", response_model=list[UploadListItemOut])
def list_uploads(session: Session = Depends(get_session)):
    rows = session.query(UploadAudit).order_by(UploadAudit.uploaded_at.desc()).all()
    return [
        UploadListItemOut(
            id=r.id,
            filename=r.filename,
            uploaded_at=r.uploaded_at,
            pipeline_run_id=r.pipeline_run_id,
            byte_size=r.byte_size,
            validation_status=r.validation_status,
        )
        for r in rows
    ]


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
    store = session.query(UploadFileStore).filter(UploadFileStore.upload_id == upload_id).one_or_none()
    if store is None:
        raise HTTPException(status_code=404, detail=f"File for upload id={upload_id} not found")

    audit = session.query(UploadAudit).filter(UploadAudit.id == upload_id).one()
    return Response(
        content=bytes(store.raw_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{audit.filename}"'},
    )
