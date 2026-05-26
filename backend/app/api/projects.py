from fastapi import APIRouter ,Depends ,HTTPException 
from sqlalchemy .orm import Session 
from sqlalchemy import select 

from app .db .session import get_db 
from app .deps .auth import get_current_user ,require_roles 
from app .models .user import User 
from app .models .project import Project 
from app .schemas .project import ProjectCreate ,ProjectOut 

router =APIRouter (prefix ="/projects",tags =["projects"],dependencies =[Depends (get_current_user )])


@router .get ("",response_model =list [ProjectOut ])
def list_projects (db :Session =Depends (get_db )):
    rows =db .execute (select (Project ).order_by (Project .name .asc ())).scalars ().all ()
    return rows 


@router .post ("",response_model =ProjectOut )
def create_project (
payload :ProjectCreate ,
db :Session =Depends (get_db ),
_admin :User =Depends (require_roles ("admin")),
):
    existing =db .execute (select (Project ).where (Project .name ==payload .name )).scalar_one_or_none ()
    if existing :
        raise HTTPException (status_code =409 ,detail ="Project with this name already exists")

    obj =Project (name =payload .name )
    db .add (obj )
    db .commit ()
    db .refresh (obj )
    return obj 
