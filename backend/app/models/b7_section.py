import uuid 
from datetime import datetime ,timezone 

from sqlalchemy import DateTime ,ForeignKey ,Integer ,String 
from sqlalchemy .dialects .postgresql import UUID 
from sqlalchemy .orm import Mapped ,mapped_column 

from app .db .session import Base 


class B7Section (Base ):
    __tablename__ ="b7_sections"

    id :Mapped [uuid .UUID ]=mapped_column (UUID (as_uuid =True ),primary_key =True ,default =uuid .uuid4 )
    project_id :Mapped [uuid .UUID ]=mapped_column (UUID (as_uuid =True ),nullable =False ,index =True )

    report_id :Mapped [uuid .UUID ]=mapped_column (
    UUID (as_uuid =True ),
    ForeignKey ("b7_reports.id",ondelete ="CASCADE"),
    nullable =False ,
    index =True ,
    )

    title :Mapped [str ]=mapped_column (String (1000 ),nullable =False )
    title_norm :Mapped [str ]=mapped_column (String (1000 ),nullable =False ,index =True )

    row_index :Mapped [int ]=mapped_column (Integer ,nullable =False )

    created_at :Mapped [datetime ]=mapped_column (
    DateTime ,nullable =False ,default =lambda :datetime .now (timezone .utc )
    )