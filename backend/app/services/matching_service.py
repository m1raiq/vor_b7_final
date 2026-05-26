import uuid 
from typing import Any ,Optional 

from rapidfuzz import fuzz 
from sqlalchemy import select 
from sqlalchemy .orm import Session 

from app .models .b7_report import B7Report 
from app .models .b7_row import B7Row 
from app .models .b7_section import B7Section 
from app .models .b7_vor_mapping import B7VorMapping 
from app .models .vor_item import VorItem 
from app .services .semantic_match_service import semantic_pick_vor_id


def _safe_float (x )->float |None :
    try :
        if x is None :
            return None 
        if isinstance (x ,float )and x !=x :
            return None 
        return float (x )
    except Exception :
        return None 





def units_compatible (vor_unit_norm :str ,b7_unit_norm :str )->bool :
    vu =(vor_unit_norm or "").strip ()
    bu =(b7_unit_norm or "").strip ()
    if not vu or not bu :
        return False 
    return vu ==bu 





def convert_fact_week (value :float |None ,from_unit_norm :str ,to_unit_norm :str )->float |None :
    if value is None :
        return None 

    fu =(from_unit_norm or "").strip ()
    tu =(to_unit_norm or "").strip ()

    if not fu or not tu :
        return value 

    if fu ==tu :
        return value 

    if fu =="кг"and tu =="т":
        return value /1000.0 

    if fu =="т"and tu =="кг":
        return value *1000.0 

    return value 





_ARM ={"армирование"}
_CONC ={"бетонирование"}


def _b7_kind (work_name_norm :str )->str |None :
    wn =(work_name_norm or "").strip ()
    if wn in _ARM :
        return "ARM"
    if wn in _CONC :
        return "CONC"
    return None 


def _pick_vor_by_kind (cands :list [VorItem ],kind :str |None )->Optional [VorItem ]:
    if not cands or not kind :
        return None 

    if kind =="ARM":
        v =next ((x for x in cands if (x .unit_norm or "").strip ()=="т"),None )
        if v :
            return v 

    if kind =="CONC":
        v =next ((x for x in cands if (x .unit_norm or "").strip ()=="м3"),None )
        if v :
            return v 

    return None 


_MASS_UNITS ={"кг","т"}
_VOL_UNITS ={"м3"}

def _unit_group (u :str )->str |None :
    u =(u or "").strip ()
    if u in _MASS_UNITS :
        return "MASS"
    if u in _VOL_UNITS :
        return "VOL"
    return None 


def _filter_vor_by_group (cands :list [VorItem ],group :str |None )->list [VorItem ]:
    if not cands or not group :
        return cands 
    if group =="MASS":
        return [x for x in cands if (x .unit_norm or "").strip ()in _MASS_UNITS ]
    if group =="VOL":
        return [x for x in cands if (x .unit_norm or "").strip ()in _VOL_UNITS ]
    return cands 


def _resolve_report_id (project_id :uuid .UUID ,db :Session ,report_id :uuid .UUID |None )->uuid .UUID |None :
    if report_id is not None :
        return report_id 

    last =(
    db .execute (
    select (B7Report )
    .where (B7Report .project_id ==project_id )
    .order_by (B7Report .report_date .desc (),B7Report .created_at .desc ())
    .limit (1 )
    )
    .scalars ()
    .first ()
    )
    return last .id if last else None 


def build_matching_result (
project_id :uuid .UUID ,
db :Session ,
limit :int =300 ,
fuzzy_threshold :int =85 ,
only_problems :bool =False ,
report_id :uuid .UUID |None =None ,
)->dict [str ,Any ]:

    resolved_report_id =_resolve_report_id (project_id ,db ,report_id )
    if resolved_report_id is None :
        return {
        "checked":0 ,
        "matched":0 ,
        "unit_mismatch":0 ,
        "unmatched":0 ,
        "items":[],
        "report_id":None ,
        }




    vor_items :list [VorItem ]=(
    db .execute (select (VorItem ).where (VorItem .project_id ==project_id ))
    .scalars ()
    .all ()
    )

    vor_by_name_unit :dict [tuple [str ,str ],VorItem ]={}
    vor_by_name :dict [str ,list [VorItem ]]={}

    for v in vor_items :
        n =(v .work_name_norm or "").strip ()
        u =(v .unit_norm or "").strip ()
        if n :
            vor_by_name .setdefault (n ,[]).append (v )
            if u :
                vor_by_name_unit [(n ,u )]=v 




    b7_rows :list [B7Row ]=(
    db .execute (
    select (B7Row )
    .where (
    B7Row .project_id ==project_id ,
    B7Row .report_id ==resolved_report_id ,
    )
    .order_by (B7Row .report_date .asc (),B7Row .section_id .asc (),B7Row .work_name .asc ())
    .limit (limit )
    )
    .scalars ()
    .all ()
    )

    if not b7_rows :
        return {
        "checked":0 ,
        "matched":0 ,
        "unit_mismatch":0 ,
        "unmatched":0 ,
        "items":[],
        "report_id":str (resolved_report_id ),
        }




    section_ids ={r .section_id for r in b7_rows if r .section_id is not None }
    section_by_id :dict [uuid .UUID ,B7Section ]={}

    if section_ids :
        sections =(
        db .execute (
        select (B7Section ).where (
        B7Section .project_id ==project_id ,
        B7Section .report_id ==resolved_report_id ,
        B7Section .id .in_ (section_ids ),
        )
        )
        .scalars ()
        .all ()
        )
        section_by_id ={s .id :s for s in sections }




    mappings =(
    db .execute (select (B7VorMapping ).where (B7VorMapping .project_id ==project_id ))
    .scalars ()
    .all ()
    )

    mapping_by_key ={
    (
    (m .section_title_norm or "").strip (),
    (m .b7_name_norm or "").strip (),
    (m .unit_norm or "").strip (),
    ):m .vor_item_id 
    for m in mappings 
    }

    items :list [dict [str ,Any ]]=[]

    for b7 in b7_rows :
        b7_name_norm =(b7 .work_name_norm or "").strip ()
        b7_unit_norm =(b7 .unit_norm or "").strip ()


        sec_title =None 
        sec_title_norm =""
        if b7 .section_id and b7 .section_id in section_by_id :
            sec =section_by_id [b7 .section_id ]
            sec_title =sec .title 
            sec_title_norm =(sec .title_norm or "").strip ()


        kind =_b7_kind (b7_name_norm )
        b7_match_key =sec_title_norm if (kind and sec_title_norm )else b7_name_norm 

        status ="UNMATCHED"
        match_type =None 
        fuzzy_score =None 
        vor_candidate :VorItem |None =None 


        unit_display =b7 .unit 
        unit_display_norm =b7_unit_norm 
        fact_week_raw =_safe_float (getattr (b7 ,"fact_week",None ))
        fact_week_display =fact_week_raw 




        mem_key =(sec_title_norm ,b7_name_norm ,b7_unit_norm )
        mapped_vor_id =mapping_by_key .get (mem_key )
        if mapped_vor_id :
            v =next ((x for x in vor_items if x .id ==mapped_vor_id ),None )
            if v :
                vor_candidate =v 
                match_type ="MEMORY"


                unit_display =v .unit 
                unit_display_norm =(v .unit_norm or "").strip ()
                fact_week_display =convert_fact_week (fact_week_raw ,b7_unit_norm ,unit_display_norm )


                status ="MATCHED"




        if not vor_candidate and b7_match_key and b7_unit_norm :
            exact =vor_by_name_unit .get ((b7_match_key ,b7_unit_norm ))
            if exact :
                vor_candidate =exact 
                match_type ="EXACT"
                status ="MATCHED"




        if not vor_candidate and b7_match_key :
            cands =vor_by_name .get (b7_match_key )or []
            group =_unit_group (b7_unit_norm )
            cands =_filter_vor_by_group (cands ,group )or []
            if cands :
                picked =_pick_vor_by_kind (cands ,kind )or cands [0 ]
                vor_candidate =picked 
                match_type ="EXACT_NAME"
                status ="MATCHED"if units_compatible (picked .unit_norm or "",b7_unit_norm )else "UNIT_MISMATCH"




        if not vor_candidate and b7_match_key :
            group =_unit_group (b7_unit_norm )
            pool =vor_items 

            if group :
                if group =="MASS":
                    pool =[x for x in vor_items if (x .unit_norm or "").strip ()in _MASS_UNITS ]
                elif group =="VOL":
                    pool =[x for x in vor_items if (x .unit_norm or "").strip ()in _VOL_UNITS ]

            best =None 
            best_score =-1 

            for v in pool :
                v_name_norm =(v .work_name_norm or "").strip ()
                if not v_name_norm :
                    continue 

                score =fuzz .token_sort_ratio (b7_match_key ,v_name_norm )
                if score >best_score :
                    best_score =score 
                    best =v 

            if best and best_score >=fuzzy_threshold :
                vor_candidate =best 
                match_type ="FUZZY"
                fuzzy_score =float (best_score )
                status ="MATCHED"if units_compatible (best .unit_norm or "",b7_unit_norm )else "UNIT_MISMATCH"

        if not vor_candidate and b7_match_key :
            group =_unit_group (b7_unit_norm )
            pool =vor_items 
            if group =="MASS":
                pool =[x for x in vor_items if (x .unit_norm or "").strip ()in _MASS_UNITS ] or vor_items 
            elif group =="VOL":
                pool =[x for x in vor_items if (x .unit_norm or "").strip ()in _VOL_UNITS ] or vor_items 

            scored :list [tuple [int ,VorItem ]]=[]
            for v in pool :
                v_name_norm =(v .work_name_norm or "").strip ()
                if not v_name_norm :
                    continue 
                score =int (fuzz .token_sort_ratio (b7_match_key ,v_name_norm ))
                scored .append ((score ,v ))
            scored .sort (key =lambda x :x [0 ],reverse =True )
            top =[v for _s ,v in scored [:8 ]]

            pick_id =semantic_pick_vor_id (
            section_title =sec_title or "",
            work_name =b7 .work_name or "",
            unit =b7 .unit or "",
            candidates =[
            {"id":str (v .id ),"name":str (v .work_name or ""),"unit":str (v .unit or "")}
            for v in top 
            ],
            )
            if pick_id :
                picked =next ((x for x in top if str (x .id )==pick_id ),None )
                if picked :
                    vor_candidate =picked 
                    match_type ="SEMANTIC"
                    status ="MATCHED"if units_compatible (picked .unit_norm or "",b7_unit_norm )else "UNIT_MISMATCH"

        item ={
        "b7_row_id":str (b7 .id ),
        "report_id":str (resolved_report_id ),
        "report_date":b7 .report_date .isoformat ()if b7 .report_date else None ,
        "section_id":str (b7 .section_id )if b7 .section_id else None ,
        "section_title":sec_title ,
        "work_name":b7 .work_name ,


        "unit":unit_display ,
        "fact_week":fact_week_display ,

        "status":status ,
        "match_type":match_type ,
        "fuzzy_score":fuzzy_score ,

        "vor_id_candidate":str (vor_candidate .id )if vor_candidate else None ,
        "vor_work_name":vor_candidate .work_name if vor_candidate else None ,
        "vor_unit":vor_candidate .unit if vor_candidate else None ,


        "unit_original":b7 .unit ,
        "fact_week_original":fact_week_raw ,
        }

        if only_problems :
            if status in ("UNMATCHED","UNIT_MISMATCH"):
                items .append (item )
        else :
            items .append (item )

    matched =sum (1 for x in items if x ["status"]=="MATCHED")
    unit_mismatch =sum (1 for x in items if x ["status"]=="UNIT_MISMATCH")
    unmatched =sum (1 for x in items if x ["status"]=="UNMATCHED")

    return {
    "checked":len (items ),
    "matched":matched ,
    "unit_mismatch":unit_mismatch ,
    "unmatched":unmatched ,
    "items":items ,
    "report_id":str (resolved_report_id ),
    }
