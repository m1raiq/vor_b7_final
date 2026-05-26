import uuid 
from datetime import date ,datetime ,timezone 

from sqlalchemy import Date ,DateTime ,String ,UniqueConstraint 
from sqlalchemy .dialects .postgresql import UUID 
from sqlalchemy .orm import Mapped ,mapped_column 

from app .db .session import Base 


class B7Report (Base ):
    __tablename__ ="b7_reports"

    __table_args__ =(
    UniqueConstraint (
    "project_id",
    "report_date",
    name ="uq_b7_report_project_date",
    ),
    )

    id :Mapped [uuid .UUID ]=mapped_column (
    UUID (as_uuid =True ),
    primary_key =True ,
    default =uuid .uuid4 ,
    )

    project_id :Mapped [uuid .UUID ]=mapped_column (
    UUID (as_uuid =True ),
    nullable =False ,
    index =True ,
    )


    report_date :Mapped [date ]=mapped_column (
    Date ,
    nullable =False ,
    index =True ,
    )

    source_filename :Mapped [str ]=mapped_column (
    String (255 ),
    nullable =False ,
    )

    sheet_name :Mapped [str ]=mapped_column (
    String (128 ),
    nullable =False ,
    default ="Sheet1",
    )

    created_at :Mapped [datetime ]=mapped_column (
    DateTime ,
    nullable =False ,
    default =lambda :datetime .now (timezone .utc ),
    )