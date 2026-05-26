import uuid 
from datetime import date as dt_date 
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


def convert_value (value :float |None ,from_unit_norm :str ,to_unit_norm :str )->float |None :
    """
    Конвертация значения из from -> to.
    Сейчас достаточно: кг <-> т.
    (м3 остаётся м3, и т.п.)
    """
    if value is None :
        return None 
    fu =(from_unit_norm or "").strip ()
    tu =(to_unit_norm or "").strip ()
    if not fu or not tu or fu ==tu :
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
        return next ((x for x in cands if (x .unit_norm or "").strip ()=="т"),None )
    if kind =="CONC":
        return next ((x for x in cands if (x .unit_norm or "").strip ()=="м3"),None )
    return None 





def _resolve_vor_for_b7_row (
*,
b7 :B7Row ,
section_by_id :dict [uuid .UUID ,B7Section ],
vor_items :list [VorItem ],
vor_by_name :dict [str ,list [VorItem ]],
vor_by_name_unit :dict [tuple [str ,str ],VorItem ],
mapping_by_key :dict [tuple [str ,str ,str ],uuid .UUID ],
fuzzy_threshold :int ,
)->dict [str ,Any ]:
    """
    Возвращает:
    - vor_candidate (или None)
    - status: MATCHED / UNIT_MISMATCH / UNMATCHED
    - unit_display, fact_week_display (если MEMORY -> приводим к эталону ВОР)
    - match_type
    """
    b7_name_norm =(b7 .work_name_norm or "").strip ()
    b7_unit_norm =(b7 .unit_norm or "").strip ()
    fact_week_raw =_safe_float (getattr (b7 ,"fact_week",None ))or 0.0 

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
            fact_week_display =convert_value (fact_week_raw ,b7_unit_norm ,unit_display_norm )

            status ="MATCHED"


    if not vor_candidate and b7_match_key and b7_unit_norm :
        exact =vor_by_name_unit .get ((b7_match_key ,b7_unit_norm ))
        if exact :
            vor_candidate =exact 
            match_type ="EXACT"
            status ="MATCHED"


    if not vor_candidate and b7_match_key :
        cands =vor_by_name .get (b7_match_key )or []
        if cands :
            picked =_pick_vor_by_kind (cands ,kind )or cands [0 ]
            vor_candidate =picked 
            match_type ="EXACT_NAME"

            status ="MATCHED"if units_compatible (picked .unit_norm or "",b7_unit_norm )else "UNIT_MISMATCH"


    if not vor_candidate and b7_match_key :
        best =None 
        best_score =-1 
        for v in vor_items :
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
        scored :list [tuple [int ,VorItem ]]=[]
        for v in vor_items :
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

    return {
    "vor":vor_candidate ,
    "status":status ,
    "match_type":match_type ,
    "fuzzy_score":fuzzy_score ,
    "unit_display":unit_display ,
    "unit_display_norm":unit_display_norm ,
    "fact_week_display":fact_week_display ,
    "section_title":sec_title ,
    }





def _load_reports (
project_id :uuid .UUID ,
db :Session ,
date_from :Optional [dt_date ],
date_to :Optional [dt_date ],
report_ids :Optional [list [uuid .UUID ]]=None ,
)->list [B7Report ]:
    q =select (B7Report ).where (B7Report .project_id ==project_id )

    if report_ids :
        q =q .where (B7Report .id .in_ (report_ids ))

    if date_from is not None :
        q =q .where (B7Report .report_date >=date_from )
    if date_to is not None :
        q =q .where (B7Report .report_date <=date_to )

    q =q .order_by (B7Report .report_date .asc ())
    return db .execute (q ).scalars ().all ()


def _month_key (d :dt_date )->str :
    return f"{d .year :04d}-{d .month :02d}"





def build_weekly_summary (
*,
project_id :uuid .UUID ,
db :Session ,
date_from :Optional [dt_date ]=None ,
date_to :Optional [dt_date ]=None ,
report_ids :Optional [list [uuid .UUID ]]=None ,
include_problems :bool =True ,
fuzzy_threshold :int =85 ,
)->dict [str ,Any ]:


    vor_items :list [VorItem ]=(
    db .execute (select (VorItem ).where (VorItem .project_id ==project_id ))
    .scalars ()
    .all ()
    )
    vor_by_id :dict [uuid .UUID ,VorItem ]={v .id :v for v in vor_items }

    vor_by_name :dict [str ,list [VorItem ]]={}
    vor_by_name_unit :dict [tuple [str ,str ],VorItem ]={}
    for v in vor_items :
        n =(v .work_name_norm or "").strip ()
        u =(v .unit_norm or "").strip ()
        if n :
            vor_by_name .setdefault (n ,[]).append (v )
            if u :
                vor_by_name_unit [(n ,u )]=v 


    reports =_load_reports (project_id ,db ,date_from ,date_to ,report_ids )
    if not reports :
        return {
        "project_id":str (project_id ),
        "weeks":[],
        "items":[],
        "problems":[]if include_problems else None ,
        }

    report_ids =[r .id for r in reports ]
    weeks =[r .report_date .isoformat ()for r in reports ]


    b7_rows :list [B7Row ]=(
    db .execute (
    select (B7Row )
    .where (
    B7Row .project_id ==project_id ,
    B7Row .report_id .in_ (report_ids ),
    )
    )
    .scalars ()
    .all ()
    )


    section_ids ={r .section_id for r in b7_rows if r .section_id is not None }
    sections =(
    db .execute (
    select (B7Section ).where (
    B7Section .project_id ==project_id ,
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
    ((m .section_title_norm or "").strip (),(m .b7_name_norm or "").strip (),(m .unit_norm or "").strip ()):m .vor_item_id 
    for m in mappings 
    }


    agg :dict [uuid .UUID ,dict [str ,float ]]={}
    problems :list [dict [str ,Any ]]=[]

    for b7 in b7_rows :
        rep_date =b7 .report_date .isoformat ()if b7 .report_date else None 
        if not rep_date :
            continue 

        resolved =_resolve_vor_for_b7_row (
        b7 =b7 ,
        section_by_id =section_by_id ,
        vor_items =vor_items ,
        vor_by_name =vor_by_name ,
        vor_by_name_unit =vor_by_name_unit ,
        mapping_by_key =mapping_by_key ,
        fuzzy_threshold =fuzzy_threshold ,
        )

        status =resolved ["status"]
        vor =resolved ["vor"]


        if status =="MATCHED"and vor :
            val =_safe_float (resolved ["fact_week_display"])or 0.0 
            agg .setdefault (vor .id ,{})
            agg [vor .id ][rep_date ]=agg [vor .id ].get (rep_date ,0.0 )+float (val )
        else :
            if include_problems :
                problems .append (
                {
                "report_date":rep_date ,
                "section_title":resolved .get ("section_title"),
                "work_name":b7 .work_name ,
                "unit":b7 .unit ,
                "fact_week":_safe_float (getattr (b7 ,"fact_week",None )),
                "status":status ,
                "match_type":resolved .get ("match_type"),
                "vor_candidate":(vor .work_name if vor else None ),
                "vor_unit":(vor .unit if vor else None ),
                }
                )


    result_items :list [dict [str ,Any ]]=[]

    for v in vor_items :
        plan =_safe_float (v .plan_volume )
        row ={
        "vor_id":str (v .id ),
        "work_name":v .work_name ,
        "unit":v .unit ,
        "plan_total":plan ,
        "weeks":{},
        "fact_total":0.0 ,
        "delta_abs":None ,
        "delta_pct":None ,
        }

        total =0.0 
        week_map =agg .get (v .id ,{})
        for w in weeks :
            x =float (week_map .get (w ,0.0 ))
            row ["weeks"][w ]=round (x ,6 )
            total +=x 

        row ["fact_total"]=round (total ,6 )

        if plan is not None :
            row ["delta_abs"]=round (float (plan )-float (total ),6 )
            row ["delta_pct"]=round ((float (total )/float (plan )*100.0 ),4 )if float (plan )!=0.0 else None 

        result_items .append (row )

    return {
    "project_id":str (project_id ),
    "weeks":weeks ,
    "items":result_items ,
    "problems":problems if include_problems else None ,
    }





def build_monthly_summary (
*,
project_id :uuid .UUID ,
db :Session ,
date_from :Optional [dt_date ]=None ,
date_to :Optional [dt_date ]=None ,
report_ids :Optional [list [uuid .UUID ]]=None ,
include_problems :bool =True ,
fuzzy_threshold :int =85 ,
)->dict [str ,Any ]:

    reports =_load_reports (project_id ,db ,date_from ,date_to ,report_ids )
    if not reports :
        return {
        "project_id":str (project_id ),
        "months":[],
        "items":[],
        "problems":[]if include_problems else None ,
        }



    weekly =build_weekly_summary (
    project_id =project_id ,
    db =db ,
    date_from =date_from ,
    date_to =date_to ,
    report_ids =report_ids ,
    include_problems =include_problems ,
    fuzzy_threshold =fuzzy_threshold ,
    )

    weeks =weekly ["weeks"]

    months_ordered :list [str ]=[]
    month_by_week :dict [str ,str ]={}
    for r in reports :
        wk =r .report_date .isoformat ()
        mk =_month_key (r .report_date )
        month_by_week [wk ]=mk 
        if mk not in months_ordered :
            months_ordered .append (mk )

    result_items :list [dict [str ,Any ]]=[]
    for item in weekly ["items"]:
        month_sums :dict [str ,float ]={m :0.0 for m in months_ordered }
        for w in weeks :
            mk =month_by_week .get (w )
            if not mk :
                continue 
            month_sums [mk ]+=float (item ["weeks"].get (w ,0.0 ))

        out ={
        "vor_id":item ["vor_id"],
        "work_name":item ["work_name"],
        "unit":item ["unit"],
        "plan_total":item ["plan_total"],
        "months":{m :round (month_sums [m ],6 )for m in months_ordered },
        "fact_total":item ["fact_total"],
        "delta_abs":item ["delta_abs"],
        "delta_pct":item ["delta_pct"],
        }
        result_items .append (out )

    return {
    "project_id":str (project_id ),
    "months":months_ordered ,
    "items":result_items ,
    "problems":weekly .get ("problems")if include_problems else None ,
    }
