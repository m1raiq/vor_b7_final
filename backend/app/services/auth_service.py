from sqlalchemy import select 
from sqlalchemy import text 
from sqlalchemy .orm import Session 

from app .config import settings 
from app .deps .auth import hash_password 
from app .models .user import User 


def migrate_users_email_to_login (db :Session )->None :
    rows =db .execute (
    text (
    """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema='public' AND table_name='users'
    """
    )
    ).fetchall ()
    cols ={str (r [0 ])for r in rows }
    if "login"not in cols and "email"in cols :
        db .execute (text ("ALTER TABLE users RENAME COLUMN email TO login"))
        db .commit ()
        return 
    if "login"in cols and "email"in cols :
        db .execute (text ("UPDATE users SET login = COALESCE(login, email) WHERE login IS NULL OR login = ''"))
        db .execute (text ("ALTER TABLE users DROP COLUMN email"))
        db .commit ()


def ensure_seed_admin (db :Session )->None :
    login =(
    (settings .auth_seed_admin_login or "").strip ().lower ()
    or (settings .auth_seed_admin_email or "").strip ().lower ()
    )
    password =settings .auth_seed_admin_password or ""
    if not login or not password :
        return 

    existing =db .execute (select (User ).where (User .login ==login )).scalar_one_or_none ()
    if existing :
        return 

    admin =User (
    login =login ,
    password_hash =hash_password (password ),
    full_name =(settings .auth_seed_admin_full_name or "Administrator").strip (),
    role ="admin",
    is_active =True ,
    )
    db .add (admin )
    db .commit ()
