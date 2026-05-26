import uuid 
from pydantic import BaseModel ,Field 


class ProjectCreate (BaseModel ):
    name :str =Field (min_length =1 ,max_length =255 )


class ProjectOut (BaseModel ):
    id :uuid .UUID 
    name :str 

    class Config :
        from_attributes =True 