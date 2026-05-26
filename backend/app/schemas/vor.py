import uuid 
from pydantic import BaseModel 


class VorItemOut (BaseModel ):
    id :uuid .UUID 
    project_id :uuid .UUID 
    work_name :str 
    unit :str 
    plan_volume :float |None 

    class Config :
        from_attributes =True 