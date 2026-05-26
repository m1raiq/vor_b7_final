import uuid 
from pydantic import BaseModel 


class B7SectionOut (BaseModel ):
    id :uuid .UUID 
    project_id :uuid .UUID 
    report_id :uuid .UUID 
    title :str 
    row_index :int 

    class Config :
        from_attributes =True 