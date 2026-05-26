import uuid 
import datetime as dt 
from pydantic import BaseModel 


class B7RowOut (BaseModel ):
    id :uuid .UUID 
    project_id :uuid .UUID 
    report_id :uuid .UUID 
    section_id :uuid .UUID |None 
    work_name :str 
    unit :str 
    report_date :dt .date 
    fact_week :float 

    class Config :
        from_attributes =True 