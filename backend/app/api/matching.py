import uuid 

from fastapi import APIRouter ,Depends ,HTTPException 
from sqlalchemy import delete ,select 
from sqlalchemy .orm import Session 

from app .db .session import get_db 
from app .deps .auth import get_current_user ,require_roles 
from app .models .b7_row import B7Row 
from app .models .b7_section import B7Section 
from app .models .b7_vor_mapping import B7VorMapping 
from app .models .user import User 
from app .models .vor_item import VorItem 
from app .schemas .mapping import MappingCreate 
from app .services .matching_service import build_matching_result 

router =APIRouter (prefix ="/projects/{project_id}/matching",tags =["matching"],dependencies =[Depends (get_current_user )])


@router .get ("/preview")
def preview_matching (
project_id :uuid .UUID ,
db :Session =Depends (get_db ),
limit :int =300 ,
fuzzy_threshold :int =85 ,
report_id :uuid .UUID |None =None ,
):
    return build_matching_result (
    project_id =project_id ,
    db =db ,
    limit =limit ,
    fuzzy_threshold =fuzzy_threshold ,
    report_id =report_id ,
    )


def _get_section_title_norm (db :Session ,b7 :B7Row )->str :
    if not b7 .section_id :
        return ""
    sec =db .execute (select (B7Section ).where (B7Section .id ==b7 .section_id )).scalar_one_or_none ()
    return (sec .title_norm or "").strip ()if sec else ""


@router .post ("/confirm")
def confirm_mapping (
payload :MappingCreate ,
project_id :uuid .UUID ,
db :Session =Depends (get_db ),
_editor :User =Depends (require_roles ("editor","admin")),
):
    b7 =db .execute (select (B7Row ).where (B7Row .id ==payload .b7_row_id )).scalar_one_or_none ()
    if not b7 or b7 .project_id !=project_id :
        raise HTTPException (status_code =404 ,detail ="B7 row not found for this project")

    vor =db .execute (select (VorItem ).where (VorItem .id ==payload .vor_item_id )).scalar_one_or_none ()
    if not vor or vor .project_id !=project_id :
        raise HTTPException (status_code =404 ,detail ="VOR item not found for this project")

    section_title_norm =_get_section_title_norm (db ,b7 )
    b7_name_norm =(b7 .work_name_norm or "").strip ()
    unit_norm =(b7 .unit_norm or "").strip ()

    db .execute (
    delete (B7VorMapping ).where (
    B7VorMapping .project_id ==project_id ,
    B7VorMapping .section_title_norm ==section_title_norm ,
    B7VorMapping .b7_name_norm ==b7_name_norm ,
    B7VorMapping .unit_norm ==unit_norm ,
    )
    )

    m =B7VorMapping (
    project_id =project_id ,
    section_id =b7 .section_id ,
    section_title_norm =section_title_norm ,
    b7_name_norm =b7_name_norm ,
    unit_norm =unit_norm ,
    vor_item_id =vor .id ,
    )
    db .add (m )
    db .commit ()

    return {
    "status":"ok",
    "b7_row_id":str (b7 .id ),
    "section_title_norm":section_title_norm ,
    "mapped_to_vor_id":str (vor .id ),
    }


@router .delete ("/confirm/{b7_row_id}")
def delete_mapping (
project_id :uuid .UUID ,
b7_row_id :uuid .UUID ,
db :Session =Depends (get_db ),
_editor :User =Depends (require_roles ("editor","admin")),
):
    b7 =db .execute (select (B7Row ).where (B7Row .id ==b7_row_id )).scalar_one_or_none ()
    if not b7 or b7 .project_id !=project_id :
        raise HTTPException (status_code =404 ,detail ="B7 row not found for this project")

    section_title_norm =_get_section_title_norm (db ,b7 )
    b7_name_norm =(b7 .work_name_norm or "").strip ()
    unit_norm =(b7 .unit_norm or "").strip ()

    db .execute (
    delete (B7VorMapping ).where (
    B7VorMapping .project_id ==project_id ,
    B7VorMapping .section_title_norm ==section_title_norm ,
    B7VorMapping .b7_name_norm ==b7_name_norm ,
    B7VorMapping .unit_norm ==unit_norm ,
    )
    )
    db .commit ()

    return {"status":"ok","deleted_for_b7_row_id":str (b7_row_id )}
