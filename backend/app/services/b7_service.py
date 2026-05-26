import io 
import re 
import uuid 
from dataclasses import dataclass 
from datetime import date as dt_date 

import pandas as pd 
from fastapi import HTTPException 
from sqlalchemy import delete ,select 
from sqlalchemy .orm import Session 

from app .models .project import Project 
from app .models .b7_report import B7Report 
from app .models .b7_row import B7Row 
from app .models .b7_section import B7Section 
from app .utils .normalization import norm_text ,norm_unit ,parse_num ,row_full_text 

MAX_TEXT_LEN =1000 


def _clip (s :str |None ,max_len :int =MAX_TEXT_LEN )->str :
    if s is None :
        return ""
    s =str (s )
    return s [:max_len ]


def _find_header_row (df_raw :pd .DataFrame ,max_scan :int =220 )->int |None :
    best_i ,best_score =None ,-1 
    scan =min (max_scan ,len (df_raw ))

    for i in range (scan ):
        row =[str (x ).strip ().lower ()for x in df_raw .iloc [i ].tolist ()]
        score =0 
        if any ("наимен"in x for x in row ):
            score +=3 
        if any (("ед"in x and "изм"in x )or "ед. изм"in x or "ед.изм"in x for x in row ):
            score +=2 
        if any ("выполн"in x for x in row ):
            score +=1 
        if any ("примечан"in x for x in row ):
            score +=1 

        if any ("work name"in x or x =="name"for x in row ):
            score +=3 
        if any ("unit"in x for x in row ):
            score +=2 
        if any ("week"in x or "works done"in x for x in row ):
            score +=1 
        if any ("note"in x or "comment"in x for x in row ):
            score +=1 
        if score >best_score :
            best_score =score 
            best_i =i 

    return best_i if best_score >=4 else None 


def _col_text (col )->str :
    if isinstance (col ,tuple ):
        parts =[]
        for x in col :
            t =str (x ).strip ().lower ()
            if t and t !="nan":
                parts .append (t )
        return " ".join (parts )
    return str (col ).strip ().lower ()


def _pick_first (df_cols ,contains_all =(),contains_any =()):
    for c in df_cols :
        t =_col_text (c )
        if contains_all and not all (x in t for x in contains_all ):
            continue 
        if contains_any and not any (x in t for x in contains_any ):
            continue 
        return c 
    return None 


def _pick_best_week_col (df :pd .DataFrame ):
    candidates =[c for c in df .columns if "за неделю"in _col_text (c )or "week"in _col_text (c )]
    if not candidates :
        return None 

    best_col =None 
    best_score =-1 
    for c in candidates :
        series =df [c ]
        numeric_count =0 
        for v in series .head (600 ).tolist ():
            if parse_num (v )is not None :
                numeric_count +=1 
        if numeric_count >best_score :
            best_score =numeric_count 
            best_col =c 
    return best_col 


def _pick_b7_sheet_name (xls :pd .ExcelFile )->str :
    """
    Выбираем лист по названию:
    если в названии есть "б.7"/"б7"/"b.7"/"b7" (в любом регистре) — берем его.
    Если таких несколько — берем первый.
    Если нет — 400 со списком листов.
    """
    candidates =[]
    for s in xls .sheet_names :
        t =str (s or "").strip ().lower ()
        t =t .replace (" ","").replace ("-","").replace ("_","")
        if "б.7"in t or "б7"in t or "b.7"in t or "b7"in t :
            candidates .append (s )

    if candidates :
        return candidates [0 ]

    raise HTTPException (
    status_code =400 ,
    detail ={
    "msg":"Не найден лист Б.7 по названию. Переименуйте лист так, чтобы в названии было 'Б.7'.",
    "available_sheets":xls .sheet_names ,
    },
    )


SKIP_TRIGGERS =(
"перечень работ",
"наименование работ",
"проведение гэ",
"получение разрешения",
"разрешения на строительство",
"заключение договора",
"контракта на выполнение смр",
"отчет по выполнению",
"по состоянию на",
"администратор проекта",
"генеральный директор",
"работы, выполненные за неделю",
)

RE_PURE_INDEX =re .compile (r"^\s*\d+(\.\d+)*\s*$")
RE_SECTION_SUFFIX =re .compile (r"\s+(contractor|подрядчик)\s*$",re .IGNORECASE )


def _should_skip_text (text :str )->bool :
    t =norm_text (text )
    if not t or t =="nan":
        return True 
    if RE_PURE_INDEX .match (t ):
        return True 
    for trig in SKIP_TRIGGERS :
        if trig in t :
            return True 
    return False 


def _is_section_by_rowtext (row_text :str )->bool :
    t =norm_text (row_text )
    return "подрядчик"in t or "contractor"in t 


def _strip_section_suffix (name :str )->str :
    txt =str (name or "").strip ()
    txt =RE_SECTION_SUFFIX .sub ("",txt ).strip ()
    return txt 


def _is_work_row (name :str ,unit :str |None ,week_val_raw )->bool :
    if _should_skip_text (name ):
        return False 

    unit_s =str (unit or "").strip ()
    unit_s_norm =unit_s .lower ()

    week_val =parse_num (week_val_raw )

    has_unit =bool (unit_s )and unit_s_norm not in {"nan","none"}
    has_week =week_val is not None 

    return has_unit or has_week 


@dataclass 
class UploadResult :
    report_id :uuid .UUID 
    inserted_sections :int 
    inserted_rows :int 
    header_row_detected :int 
    chosen_columns :dict 


def upload_b7_xlsx (
*,
project_id :uuid .UUID ,
file_bytes :bytes ,
filename :str |None ,
report_date :dt_date ,
db :Session ,
)->UploadResult :
    project =db .execute (select (Project ).where (Project .id ==project_id )).scalar_one_or_none ()
    if not project :
        raise HTTPException (status_code =404 ,detail ="Project not found")

    if not file_bytes :
        raise HTTPException (status_code =400 ,detail ="Empty file")


    try :
        xls =pd .ExcelFile (io .BytesIO (file_bytes ))
    except Exception as e :
        raise HTTPException (status_code =400 ,detail =f"Cannot read Excel: {e }")

    sheet =_pick_b7_sheet_name (xls )

    try :
        df_raw =pd .read_excel (xls ,sheet_name =sheet ,header =None )
    except Exception as e :
        raise HTTPException (status_code =400 ,detail =f"Cannot read Excel (sheet '{sheet }'): {e }")

    header_i =_find_header_row (df_raw )
    if header_i is None :
        preview =df_raw .head (25 ).fillna ("").astype (str ).values .tolist ()
        raise HTTPException (
        status_code =400 ,
        detail ={
        "msg":f"Не удалось найти строку заголовков Б.7 на листе '{sheet }'.",
        "sheet_used":sheet ,
        "preview_first_25_rows":preview ,
        },
        )

    try :
        df =pd .read_excel (xls ,sheet_name =sheet ,header =[header_i ,header_i +1 ])
    except Exception as e :
        raise HTTPException (
        status_code =400 ,detail =f"Cannot read Excel with 2-level header (sheet '{sheet }'): {e }"
        )

    df =df .dropna (axis =1 ,how ="all")

    name_col =_pick_first (df .columns ,contains_any =("наимен",))
    if name_col is None :
        name_col =_pick_first (df .columns ,contains_any =("work name","name","work"))

    unit_col =_pick_first (df .columns ,contains_all =("ед","изм"))
    if unit_col is None :
        unit_col =_pick_first (df .columns ,contains_any =("unit",))
    week_col =_pick_best_week_col (df )

    if name_col is None or unit_col is None or week_col is None :
        raise HTTPException (
        status_code =400 ,
        detail ={
        "msg":"Не найдены колонки (Наименование/Ед.изм/За неделю).",
        "sheet_used":sheet ,
        "found_columns":[str (c )for c in df .columns ],
        },
        )

    base =df [[name_col ,unit_col ,week_col ]].copy ()
    base .columns =["work_name","unit","fact_week"]

    row_texts =[]
    for idx in df .index :
        row_texts .append (row_full_text (df .loc [idx ].tolist ()))
    base ["row_text"]=row_texts 


    report =db .execute (
    select (B7Report ).where (
    B7Report .project_id ==project_id ,
    B7Report .report_date ==report_date ,
    )
    ).scalar_one_or_none ()

    if report :

        db .execute (delete (B7Row ).where (B7Row .report_id ==report .id ))
        db .execute (delete (B7Section ).where (B7Section .report_id ==report .id ))
        report .source_filename =filename or report .source_filename 
        report .sheet_name =sheet 
        db .flush ()
    else :
        report =B7Report (
        project_id =project_id ,
        report_date =report_date ,
        source_filename =filename or "Отчет.xlsx",
        sheet_name =sheet ,
        )
        db .add (report )
        db .flush ()

    rows =[]
    for idx ,r in base .iterrows ():
        name =str (r ["work_name"]).strip ()
        rt =str (r ["row_text"]or "")
        rows .append (
        {
        "idx":int (idx ),
        "name":name ,
        "unit":r .get ("unit"),
        "week":r .get ("fact_week"),
        "row_text":rt ,
        "is_section_marker":_is_section_by_rowtext (rt ),
        }
        )

    current_section_id =None 
    inserted_sections =0 
    inserted_rows =0 

    pending_section :B7Section |None =None 
    pending_section_has_work =False 
    pending_section_unit =""
    pending_section_week =0.0 

    def _close_pending_if_needed ():
        nonlocal inserted_rows ,pending_section ,pending_section_has_work 
        nonlocal pending_section_unit ,pending_section_week 

        if pending_section and not pending_section_has_work :
            db .add (
            B7Row (
            project_id =project_id ,
            report_id =report .id ,
            section_id =pending_section .id ,
            work_name =_clip (pending_section .title ),
            work_name_norm =norm_text (pending_section .title ),
            unit =_clip (pending_section_unit ),
            unit_norm =norm_unit (pending_section_unit ),
            report_date =report_date ,
            fact_week =float (pending_section_week ),
            )
            )
            inserted_rows +=1 

    for r in rows :
        name_raw =r ["name"]
        unit_raw =r .get ("unit")
        week_raw =r .get ("week")

        name =_clip (name_raw )
        unit_str =_clip (str (unit_raw or "").strip ())

        week_val =parse_num (week_raw )
        if week_val is None :
            week_val =0.0 

        if r ["is_section_marker"]:
            if _should_skip_text (name_raw ):
                continue 

            _close_pending_if_needed ()
            section_title =_strip_section_suffix (name )
            if not section_title :
                continue 

            sec =B7Section (
            project_id =project_id ,
            report_id =report .id ,
            title =section_title ,
            title_norm =norm_text (section_title ),
            row_index =r ["idx"],
            )
            db .add (sec )
            db .flush ()
            inserted_sections +=1 

            current_section_id =sec .id 
            pending_section =sec 
            pending_section_has_work =False 
            pending_section_unit =unit_str 
            pending_section_week =float (week_val )
            continue 

        if _is_work_row (name_raw ,unit_raw ,week_raw ):
            if _should_skip_text (name_raw ):
                continue 

            if pending_section is not None :
                pending_section_has_work =True 

            db .add (
            B7Row (
            project_id =project_id ,
            report_id =report .id ,
            section_id =current_section_id ,
            work_name =name ,
            work_name_norm =norm_text (name ),
            unit =unit_str ,
            unit_norm =norm_unit (unit_str ),
            report_date =report_date ,
            fact_week =float (week_val ),
            )
            )
            inserted_rows +=1 

    _close_pending_if_needed ()

    db .commit ()

    return UploadResult (
    report_id =report .id ,
    inserted_sections =inserted_sections ,
    inserted_rows =inserted_rows ,
    header_row_detected =header_i +1 ,
    chosen_columns ={
    "sheet_used":sheet ,
    "name_col":str (name_col ),
    "unit_col":str (unit_col ),
    "week_col":str (week_col ),
    "section_marker":"row_text contains 'Подрядчик'",
    "skip_triggers":list (SKIP_TRIGGERS ),
    },
    )
