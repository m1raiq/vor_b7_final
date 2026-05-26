import uuid 
from pydantic import BaseModel 


class MappingCreate (BaseModel ):
    b7_row_id :uuid .UUID 
    vor_item_id :uuid .UUID 