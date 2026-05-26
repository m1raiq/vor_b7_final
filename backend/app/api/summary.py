import uuid
from datetime import date as dt_date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps.auth import get_current_user
from app.services.summary_service import build_weekly_summary, build_monthly_summary

router = APIRouter(
    prefix="/projects/{project_id}/summary",
    tags=["summary"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/weeks")
def summary_weeks(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    date_from: Optional[dt_date] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[dt_date] = Query(None, description="YYYY-MM-DD"),
    report_ids: list[uuid.UUID] | None = Query(None, description="repeatable report_ids"),
    include_problems: bool = Query(True, description="include UNMATCHED/UNIT_MISMATCH"),
):
    return build_weekly_summary(
        project_id=project_id,
        db=db,
        date_from=date_from,
        date_to=date_to,
        report_ids=report_ids,
        include_problems=include_problems,
    )


@router.get("/months")
def summary_months(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    date_from: Optional[dt_date] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[dt_date] = Query(None, description="YYYY-MM-DD"),
    report_ids: list[uuid.UUID] | None = Query(None, description="repeatable report_ids"),
    include_problems: bool = Query(True),
):
    return build_monthly_summary(
        project_id=project_id,
        db=db,
        date_from=date_from,
        date_to=date_to,
        report_ids=report_ids,
        include_problems=include_problems,
    )
