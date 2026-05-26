import uuid 
from fastapi import APIRouter ,Depends ,File ,HTTPException ,UploadFile 
from sqlalchemy import select 
from sqlalchemy .orm import Session 

from app .db .session import get_db 
from app .deps .auth import get_current_user ,require_roles 
from app .models .user import User 
from app .models .vor_item import VorItem 
from app .schemas .vor import VorItemOut 
from app .services .vor_service import upload_vor_rows_service ,upload_vor_service 
from app .services .vor_pdf_service import extract_vor_rows_from_pdf

router =APIRouter (prefix ="/projects/{project_id}/vor",tags =["vor"],dependencies =[Depends (get_current_user )])


@router .get ("",response_model =list [VorItemOut ])
def list_vor (project_id :uuid .UUID ,db :Session =Depends (get_db )):
    items =(
    db .execute (
    select (VorItem )
    .where (VorItem .project_id ==project_id )
    .order_by (VorItem .work_name .asc ())
    )
    .scalars ()
    .all ()
    )
    return items 


@router .post ("/upload")
async def upload_vor (
project_id :uuid .UUID ,
file :UploadFile =File (...),
db :Session =Depends (get_db ),
_editor :User =Depends (require_roles ("editor","admin")),
):
    content =await file .read ()
    return upload_vor_service (
    project_id =project_id ,
    file_bytes =content ,
    db =db ,
    filename =file .filename ,
    )


@router .post ("/upload_pdf")
async def upload_vor_pdf (
project_id :uuid .UUID ,
file :UploadFile =File (...),
db :Session =Depends (get_db ),
_editor :User =Depends (require_roles ("editor","admin")),
):
    content =await file .read ()
    ocr =extract_vor_rows_from_pdf (content )
    if not ocr .get ("ok"):
        raise HTTPException (status_code =400 ,detail ={"msg":ocr .get ("msg"),"debug":ocr .get ("debug")})
    save =upload_vor_rows_service (
    project_id =project_id ,
    rows =ocr .get ("rows")or [],
    db =db ,
    )
    save ["recognized_rows"]=len (ocr .get ("rows")or [])
    return save
