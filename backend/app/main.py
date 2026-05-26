from fastapi import FastAPI 
from app .db .session import Base ,engine 
from app .db .session import SessionLocal 
from app .api .auth import router as auth_router 
from app .api .projects import router as projects_router 
from app .api .vor import router as vor_router 
from app .api .b7 import router as b7_router 
from app .api .matching import router as matching_router 
from app .api .summary import router as summary_router 
from app .api .b7_pdf import router as b7_pdf_router 
from app .services .auth_service import migrate_users_email_to_login ,ensure_seed_admin 

app =FastAPI (title ="VOR/B7 MVP")

Base .metadata .create_all (bind =engine )
with SessionLocal ()as _db :
    migrate_users_email_to_login (_db )
    ensure_seed_admin (_db )

app .include_router (auth_router )
app .include_router (projects_router )
app .include_router (vor_router )
app .include_router (b7_router )
app .include_router (matching_router )
app .include_router (summary_router )
app .include_router (b7_pdf_router )


@app .get ("/health")
def health ():
    return {"status":"ok"}
