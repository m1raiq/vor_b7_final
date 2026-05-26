from fastapi import APIRouter ,Depends ,HTTPException ,Body 
from sqlalchemy import select 
from sqlalchemy .orm import Session 

from app .config import settings 
from app .db .session import get_db 
from app .deps .auth import (
create_access_token ,
get_current_user ,
hash_password ,
normalize_role ,
require_roles ,
verify_password ,
)
from app .models .user import User 
import uuid 

from app .schemas .auth import RegisterIn ,TokenOut ,UserCreate ,UserOut ,UserUpdate 

router =APIRouter (prefix ="/auth",tags =["auth"])


@router .post ("/login",response_model =TokenOut )
def login (payload :dict =Body (...),db :Session =Depends (get_db )):
    login_raw =(payload .get ("login")or payload .get ("email")or "").strip ().lower ()
    password =str (payload .get ("password")or "")
    if not login_raw or not password :
        raise HTTPException (status_code =422 ,detail ="login/email and password are required")
    login =login_raw 
    user =db .execute (select (User ).where (User .login ==login )).scalar_one_or_none ()
    if not user or not verify_password (password ,user .password_hash ):
        raise HTTPException (status_code =401 ,detail ="Invalid login or password")
    if not user .is_active :
        raise HTTPException (status_code =403 ,detail ="User is inactive")

    token =create_access_token (
    subject =user .login ,
    role =user .role ,
    expires_minutes =int (settings .jwt_access_token_expire_minutes ),
    )
    return TokenOut (
    access_token =token ,
    token_type ="bearer",
    expires_in =int (settings .jwt_access_token_expire_minutes )*60 ,
    role =normalize_role (user .role ),
    login =user .login ,
    full_name =user .full_name or "",
    )


@router .get ("/me",response_model =UserOut )
def me (user :User =Depends (get_current_user )):
    return user 


@router .post ("/register",response_model =UserOut )
def register (payload :RegisterIn ,db :Session =Depends (get_db )):
    login =payload .login .strip ().lower ()
    existing =db .execute (select (User ).where (User .login ==login )).scalar_one_or_none ()
    if existing :
        raise HTTPException (status_code =409 ,detail ="User with this login already exists")
    user =User (
    login =login ,
    password_hash =hash_password (payload .password ),
    full_name =payload .full_name .strip (),
    role ="user",
    is_active =True ,
    )
    db .add (user )
    db .commit ()
    db .refresh (user )
    return user 


@router .get ("/users",response_model =list [UserOut ])
def list_users (
db :Session =Depends (get_db ),
_admin :User =Depends (require_roles ("admin")),
):
    return db .execute (select (User ).order_by (User .created_at .asc ())).scalars ().all ()


@router .post ("/users",response_model =UserOut )
def create_user (
payload :UserCreate ,
db :Session =Depends (get_db ),
_admin :User =Depends (require_roles ("admin")),
):
    login =payload .login .strip ().lower ()
    existing =db .execute (select (User ).where (User .login ==login )).scalar_one_or_none ()
    if existing :
        raise HTTPException (status_code =409 ,detail ="User with this login already exists")

    role =normalize_role (payload .role )
    user =User (
    login =login ,
    password_hash =hash_password (payload .password ),
    full_name =payload .full_name .strip (),
    role =role ,
    is_active =bool (payload .is_active ),
    )
    db .add (user )
    db .commit ()
    db .refresh (user )
    return user 


@router .patch ("/users/{user_id}",response_model =UserOut )
def update_user (
user_id :uuid .UUID ,
payload :UserUpdate ,
db :Session =Depends (get_db ),
_admin :User =Depends (require_roles ("admin")),
):
    user =db .execute (select (User ).where (User .id ==user_id )).scalar_one_or_none ()
    if not user :
        raise HTTPException (status_code =404 ,detail ="User not found")
    if payload .full_name is not None :
        user .full_name =payload .full_name .strip ()
    if payload .role is not None :
        user .role =normalize_role (payload .role )
    if payload .is_active is not None :
        user .is_active =bool (payload .is_active )
    if payload .password :
        user .password_hash =hash_password (payload .password )
    db .add (user )
    db .commit ()
    db .refresh (user )
    return user 
