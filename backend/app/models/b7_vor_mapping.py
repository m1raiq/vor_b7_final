import uuid 
from datetime import datetime ,timezone 

from sqlalchemy import DateTime ,ForeignKey ,String ,UniqueConstraint 
from sqlalchemy .dialects .postgresql import UUID 
from sqlalchemy .orm import Mapped ,mapped_column 

from app .db .session import Base 


class B7VorMapping (Base ):
    __tablename__ ="b7_vor_mappings"

    __table_args__ =(
    UniqueConstraint (
    "project_id",
    "section_title_norm",
    "b7_name_norm",
    "unit_norm",
    name ="uq_project_sectiontitle_b7name_unit",
    ),
    )

    id :Mapped [uuid .UUID ]=mapped_column (UUID (as_uuid =True ),primary_key =True ,default =uuid .uuid4 )

    project_id :Mapped [uuid .UUID ]=mapped_column (UUID (as_uuid =True ),nullable =False ,index =True )

    section_id :Mapped [uuid .UUID |None ]=mapped_column (
    UUID (as_uuid =True ),
    ForeignKey ("b7_sections.id",ondelete ="SET NULL"),
    nullable =True ,
    index =True ,
    )

    section_title_norm :Mapped [str ]=mapped_column (String (1000 ),nullable =False ,index =True ,default ="")

    b7_name_norm :Mapped [str ]=mapped_column (String (1000 ),nullable =False ,index =True )
    unit_norm :Mapped [str ]=mapped_column (String (100 ),nullable =False ,index =True )

    vor_item_id :Mapped [uuid .UUID ]=mapped_column (UUID (as_uuid =True ),nullable =False ,index =True )

    created_at :Mapped [datetime ]=mapped_column (
    DateTime ,nullable =False ,default =lambda :datetime .now (timezone .utc )
    )