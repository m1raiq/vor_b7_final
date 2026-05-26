import uuid 
from datetime import date as dt_date 

from fastapi import APIRouter ,Depends ,File ,Query ,UploadFile ,HTTPException ,Body 
from sqlalchemy import select ,desc 
from sqlalchemy .orm import Session 

from app .db .session import get_db 
from app .deps .auth import get_current_user ,require_roles 
from app .models .b7_report import B7Report 
from app .models .b7_row import B7Row 
from app .models .b7_section import B7Section 
from app .models .user import User 
from app .schemas .b7 import B7RowOut 
from app .schemas .b7_section import B7SectionOut 

from app .services .b7_service import upload_b7_xlsx 
from app .services .b7_pdf_service import extract_b7_pipeline_xlsx_from_pdf ,build_b7_pipeline_xlsx_from_rows 

router =APIRouter (prefix ="/projects/{project_id}/b7",tags =["b7"],dependencies =[Depends (get_current_user )])


def _get_report_id_or_latest (
project_id :uuid .UUID ,
db :Session ,
report_id :uuid .UUID |None ,
report_date :dt_date |None ,
)->uuid .UUID |None :
    """
    Возвращает report_id:
    - если передан report_id -> он
    - если передан report_date -> ищем report по (project_id, report_date)
    - иначе -> берём последний загруженный report (по report_date desc, created_at desc)
    - если отчетов нет -> None
    """
    if report_id :
        return report_id 

    if report_date :
        r =db .execute (
        select (B7Report .id ).where (
        B7Report .project_id ==project_id ,
        B7Report .report_date ==report_date ,
        )
        ).scalar_one_or_none ()
        return r 

    latest =db .execute (
    select (B7Report .id )
    .where (B7Report .project_id ==project_id )
    .order_by (desc (B7Report .report_date ),desc (B7Report .created_at ))
    .limit (1 )
    ).scalar_one_or_none ()
    return latest 


@router .get ("/reports")
def list_b7_reports (project_id :uuid .UUID ,db :Session =Depends (get_db ),limit :int =200 ):
    """
    Список всех загруженных отчетов Б.7 по проекту.
    """
    reports =(
    db .execute (
    select (B7Report )
    .where (B7Report .project_id ==project_id )
    .order_by (desc (B7Report .report_date ),desc (B7Report .created_at ))
    .limit (limit )
    )
    .scalars ()
    .all ()
    )

    return [
    {
    "id":str (r .id ),
    "report_date":r .report_date .isoformat ()if getattr (r ,"report_date",None )else None ,
    "source_filename":r .source_filename ,
    "sheet_name":r .sheet_name ,
    "created_at":r .created_at .isoformat ()if r .created_at else None ,
    }
    for r in reports 
    ]


@router .get ("",response_model =list [B7RowOut ])
def list_b7 (
project_id :uuid .UUID ,
db :Session =Depends (get_db ),
limit :int =2000 ,
report_id :uuid .UUID |None =None ,
report_date :dt_date |None =None ,
):
    rid =_get_report_id_or_latest (project_id ,db ,report_id ,report_date )
    if rid is None :
        return []

    rows =(
    db .execute (
    select (B7Row )
    .where (B7Row .project_id ==project_id ,B7Row .report_id ==rid )
    .order_by (B7Row .section_id .asc (),B7Row .work_name .asc ())
    .limit (limit )
    )
    .scalars ()
    .all ()
    )
    return rows 


@router .get ("/rows",response_model =list [B7RowOut ])
def list_b7_rows (
project_id :uuid .UUID ,
db :Session =Depends (get_db ),
limit :int =2000 ,
report_id :uuid .UUID |None =None ,
report_date :dt_date |None =None ,
):
    rid =_get_report_id_or_latest (project_id ,db ,report_id ,report_date )
    if rid is None :
        return []

    rows =(
    db .execute (
    select (B7Row )
    .where (B7Row .project_id ==project_id ,B7Row .report_id ==rid )
    .order_by (B7Row .section_id .asc (),B7Row .work_name .asc ())
    .limit (limit )
    )
    .scalars ()
    .all ()
    )
    return rows 


@router .get ("/sections",response_model =list [B7SectionOut ])
def list_b7_sections (
project_id :uuid .UUID ,
db :Session =Depends (get_db ),
limit :int =2000 ,
report_id :uuid .UUID |None =None ,
report_date :dt_date |None =None ,
):
    rid =_get_report_id_or_latest (project_id ,db ,report_id ,report_date )
    if rid is None :
        return []

    sections =(
    db .execute (
    select (B7Section )
    .where (B7Section .project_id ==project_id ,B7Section .report_id ==rid )
    .order_by (B7Section .row_index .asc ())
    .limit (limit )
    )
    .scalars ()
    .all ()
    )
    return sections 


@router .post ("/upload")
async def upload_b7 (
project_id :uuid .UUID ,
file :UploadFile =File (...),
report_date :str =Query (...,description ="Дата недельного отчёта YYYY-MM-DD"),
db :Session =Depends (get_db ),
_editor :User =Depends (require_roles ("editor","admin")),
):
    try :
        rd =dt_date .fromisoformat (report_date )
    except Exception :
        raise HTTPException (status_code =400 ,detail ="report_date must be YYYY-MM-DD")

    content =await file .read ()
    res =upload_b7_xlsx (
    project_id =project_id ,
    file_bytes =content ,
    filename =file .filename ,
    report_date =rd ,
    db =db ,
    )
    return {
    "status":"ok",
    "report_id":str (res .report_id ),
    "inserted_sections":res .inserted_sections ,
    "inserted_rows":res .inserted_rows ,
    "header_row_detected":res .header_row_detected ,
    "chosen_columns":res .chosen_columns ,
    }


@router .post ("/upload_pdf")
async def upload_b7_pdf (
project_id :uuid .UUID ,
file :UploadFile =File (...),
report_date :str =Query (...,description ="Дата недельного отчёта YYYY-MM-DD"),
db :Session =Depends (get_db ),
_editor :User =Depends (require_roles ("editor","admin")),
):
    try :
        rd =dt_date .fromisoformat (report_date )
    except Exception :
        raise HTTPException (status_code =400 ,detail ="report_date must be YYYY-MM-DD")

    ctype =(file .content_type or "").lower ()
    filename =file .filename or "b7_report.pdf"
    if "pdf"not in ctype and not filename .lower ().endswith (".pdf"):
        raise HTTPException (status_code =400 ,detail ="Only PDF is supported for this endpoint")

    pdf_bytes =await file .read ()
    ocr_res =extract_b7_pipeline_xlsx_from_pdf (pdf_bytes )
    if not ocr_res .get ("ok"):
        raise HTTPException (
        status_code =400 ,
        detail ={
        "msg":ocr_res .get ("msg","OCR failed"),
        "debug":ocr_res .get ("debug"),
        },
        )

    xlsx_bytes =ocr_res .get ("xlsx_bytes")
    if not xlsx_bytes :
        raise HTTPException (
        status_code =400 ,
        detail ={
        "msg":"OCR не вернул xlsx для сохранения",
        "debug":ocr_res .get ("debug"),
        },
        )

    save_res =upload_b7_xlsx (
    project_id =project_id ,
    file_bytes =xlsx_bytes ,
    filename =(filename .rsplit (".",1 )[0 ]+"_ocr.xlsx"),
    report_date =rd ,
    db =db ,
    )

    return {
    "status":"ok",
    "report_id":str (save_res .report_id ),
    "inserted_sections":save_res .inserted_sections ,
    "inserted_rows":save_res .inserted_rows ,
    "header_row_detected":save_res .header_row_detected ,
    "chosen_columns":save_res .chosen_columns ,
    "recognized_rows":len (ocr_res .get ("rows",[])),
    "rows":ocr_res .get ("rows",[]),
    "debug":ocr_res .get ("debug"),
    "xlsx_ready":bool (ocr_res .get ("xlsx_bytes")),
    "db_saved":True ,
    }


@router .post ("/upload_pdf_rows")
async def upload_b7_pdf_rows (
project_id :uuid .UUID ,
payload :dict =Body (...),
report_date :str =Query (...,description ="Р”Р°С‚Р° РЅРµРґРµР»СЊРЅРѕРіРѕ РѕС‚С‡С‘С‚Р° YYYY-MM-DD"),
db :Session =Depends (get_db ),
_editor :User =Depends (require_roles ("editor","admin")),
):
    try :
        rd =dt_date .fromisoformat (report_date )
    except Exception :
        raise HTTPException (status_code =400 ,detail ="report_date must be YYYY-MM-DD")

    rows =payload .get ("rows")
    source_filename =str (payload .get ("source_filename")or "b7_report.pdf")
    if not isinstance (rows ,list )or not rows :
        raise HTTPException (status_code =400 ,detail ="rows must be non-empty list")

    xlsx_bytes =build_b7_pipeline_xlsx_from_rows (rows )
    if not xlsx_bytes :
        raise HTTPException (status_code =400 ,detail ="Failed to build xlsx from rows")

    save_res =upload_b7_xlsx (
    project_id =project_id ,
    file_bytes =xlsx_bytes ,
    filename =(source_filename .rsplit (".",1 )[0 ]+"_ocr.xlsx"),
    report_date =rd ,
    db =db ,
    )

    return {
    "status":"ok",
    "report_id":str (save_res .report_id ),
    "inserted_sections":save_res .inserted_sections ,
    "inserted_rows":save_res .inserted_rows ,
    "header_row_detected":save_res .header_row_detected ,
    "chosen_columns":save_res .chosen_columns ,
    "db_saved":True ,
    }


@router .delete ("/reports/{report_id}")
def delete_b7_report (
project_id :uuid .UUID ,
report_id :uuid .UUID ,
db :Session =Depends (get_db ),
_editor :User =Depends (require_roles ("editor","admin")),
):
    report =db .execute (
    select (B7Report ).where (
    B7Report .id ==report_id ,
    B7Report .project_id ==project_id ,
    )
    ).scalar_one_or_none ()

    if not report :
        raise HTTPException (status_code =404 ,detail ="B7 report not found for this project")

    db .delete (report )
    db .commit ()

    return {"status":"ok","deleted_report_id":str (report_id )}
