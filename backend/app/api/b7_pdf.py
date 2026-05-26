import uuid 
from datetime import date as dt_date 

from fastapi import APIRouter ,File ,UploadFile ,Query ,HTTPException ,Depends 

from app .deps .auth import get_current_user 
from app .services .b7_pdf_service import extract_b7_rows_from_pdf 

router =APIRouter (prefix ="/projects/{project_id}/b7_pdf",tags =["b7_pdf"],dependencies =[Depends (get_current_user )])


@router .post ("/upload_pdf_preview")
async def upload_b7_pdf_preview (
project_id :uuid .UUID ,
file :UploadFile =File (...),
report_date :str =Query (...,description ="Дата недельного отчета YYYY-MM-DD"),
):
    try :
        _ =dt_date .fromisoformat (report_date )
    except Exception :
        raise HTTPException (status_code =400 ,detail ="report_date must be YYYY-MM-DD")

    ctype =(file .content_type or "").lower ()
    if "pdf"not in ctype and not (file .filename or "").lower ().endswith (".pdf"):
        raise HTTPException (status_code =400 ,detail ="Only PDF is supported for this endpoint")

    pdf_bytes =await file .read ()
    res =extract_b7_rows_from_pdf (pdf_bytes )

    if not res .get ("ok"):
        raise HTTPException (
        status_code =400 ,
        detail ={
        "msg":res .get ("msg","OCR failed"),
        "debug":res .get ("debug"),
        },
        )

    return {
    "status":"ok",
    "project_id":str (project_id ),
    "report_date":report_date ,
    "recognized_rows":len (res ["rows"]),
    "rows":res ["rows"],
    "debug":res .get ("debug"),
    "xlsx_ready":bool (res .get ("xlsx_bytes")),
    }
