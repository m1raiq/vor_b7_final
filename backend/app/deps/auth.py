from datetime import datetime ,timedelta ,timezone 
from typing import Callable 

from fastapi import Depends ,HTTPException ,status 
from fastapi .security import OAuth2PasswordBearer 
from jose import JWTError ,jwt 
from passlib .context import CryptContext 
from sqlalchemy import select 
from sqlalchemy .orm import Session 

from app .config import settings 
from app .db .session import get_db 
from app .models .user import User 

pwd_context =CryptContext (schemes =["pbkdf2_sha256"],deprecated ="auto")
oauth2_scheme =OAuth2PasswordBearer (tokenUrl ="/auth/login")
_VALID_ROLES ={"user","editor","admin"}


def normalize_role (role :str )->str :
    r =(role or "").strip ().lower ()
    return r if r in _VALID_ROLES else "user"


def hash_password (password :str )->str :
    return pwd_context .hash (password )


def verify_password (password :str ,password_hash :str )->bool :
    try :
        return pwd_context .verify (password ,password_hash )
    except Exception :
        return False 


def create_access_token (subject :str ,role :str ,expires_minutes :int |None =None )->str :
    exp_minutes =expires_minutes or int (settings .jwt_access_token_expire_minutes )
    expire =datetime .now (timezone .utc )+timedelta (minutes =max (1 ,exp_minutes ))
    payload ={"sub":subject ,"role":normalize_role (role ),"exp":expire }
    return jwt .encode (payload ,settings .jwt_secret_key ,algorithm =settings .jwt_algorithm )


def _decode_token (token :str )->dict :
    try :
        return jwt .decode (token ,settings .jwt_secret_key ,algorithms =[settings .jwt_algorithm ])
    except JWTError as e :
        raise HTTPException (
        status_code =status .HTTP_401_UNAUTHORIZED ,
        detail =f"Invalid token: {e }",
        headers ={"WWW-Authenticate":"Bearer"},
        )from e 


def get_current_user (
token :str =Depends (oauth2_scheme ),
db :Session =Depends (get_db ),
)->User :
    payload =_decode_token (token )
    login =(payload .get ("sub")or "").strip ().lower ()
    if not login :
        raise HTTPException (status_code =401 ,detail ="Token subject is empty")
    user =db .execute (select (User ).where (User .login ==login )).scalar_one_or_none ()
    if not user or not user .is_active :
        raise HTTPException (status_code =401 ,detail ="User not found or inactive")
    return user 


def require_roles (*roles :str )->Callable :
    allowed ={normalize_role (r )for r in roles if r }

    def _checker (user :User =Depends (get_current_user ))->User :
        if normalize_role (user .role )not in allowed :
            raise HTTPException (status_code =403 ,detail ="Forbidden for your role")
        return user 

    return _checker 
