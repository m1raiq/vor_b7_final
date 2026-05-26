import uuid 
from datetime import datetime ,timezone 

from sqlalchemy import String ,DateTime ,Numeric ,ForeignKey 
from sqlalchemy .dialects .postgresql import UUID 
from sqlalchemy .orm import Mapped ,mapped_column 

from app .db .session import Base 


class VorItem (Base ):
    __tablename__ ="vor_items"

    id :Mapped [uuid .UUID ]=mapped_column (UUID (as_uuid =True ),primary_key =True ,default =uuid .uuid4 )

    project_id :Mapped [uuid .UUID ]=mapped_column (
    UUID (as_uuid =True ),
    ForeignKey ("projects.id",ondelete ="CASCADE"),
    nullable =False ,
    index =True ,
    )

    work_name :Mapped [str ]=mapped_column (String (1000 ),nullable =False )
    work_name_norm :Mapped [str ]=mapped_column (String (1000 ),nullable =False ,index =True )

    unit :Mapped [str ]=mapped_column (String (64 ),nullable =False )
    unit_norm :Mapped [str ]=mapped_column (String (64 ),nullable =False ,index =True )

    plan_volume :Mapped [float |None ]=mapped_column (Numeric (18 ,6 ),nullable =True )

    created_at :Mapped [datetime ]=mapped_column (DateTime ,nullable =False ,default =lambda :datetime .now (timezone .utc ))