from __future__ import annotations 

import base64 
import io 
import logging 
import re 
from typing import Any ,Dict ,List ,Optional ,Tuple 

import pandas as pd 
import requests 

from app .config import settings 
from app .utils .normalization import norm_text ,norm_unit ,parse_num 

logger =logging .getLogger (__name__ )

_NO_RE =re .compile (r"^\d+(\.\d+)*$")
_INT_RE =re .compile (r"^\d+$")
_UNIT_CAND ={"м3","м2","т","кг","шт","%","м.п.","компл"}
_HAS_CYR_RE =re .compile (r"[А-Яа-яЁё]")
_HAS_LAT_RE =re .compile (r"[A-Za-z]")
_WS_RE =re .compile (r"\s+")
_MD_TABLE_SEP_RE =re .compile (r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_PIPED_LINE_RE =re .compile (r"^\s*\|.*\|\s*$")

_LAT_TO_CYR =str .maketrans (
{
"A":"А",
"B":"В",
"C":"С",
"E":"Е",
"H":"Н",
"K":"К",
"M":"М",
"O":"О",
"P":"Р",
"T":"Т",
"X":"Х",
"Y":"У",
"a":"а",
"c":"с",
"e":"е",
"k":"к",
"m":"м",
"o":"о",
"p":"р",
"t":"т",
"x":"х",
"y":"у",
"u":"и",
}
)

def _clean_ocr_text (s :str )->str :
    return " ".join ((s or "").strip ().split ())


def _normalize_lookalikes (s :str )->str :
    if s and _HAS_CYR_RE .search (s )and _HAS_LAT_RE .search (s ):
        return s .translate (_LAT_TO_CYR )
    return s 


def _cleanup_cell_text (s :str )->str :
    s =_clean_ocr_text (s )
    if not s :
        return s 
    s =s .replace ("|","I").replace ("`","'").replace ("…","...")
    s =_normalize_lookalikes (s )
    s =re .sub (r"[^0-9A-Za-zА-Яа-яЁё\s\.,:%/\-\+\(\)\?]+"," ",s ,flags =re .UNICODE )
    s =re .sub (r"([.,:;\-])\1{1,}",r"\1",s )
    s =_WS_RE .sub (" ",s ).strip ()
    tokens =re .split (r"(\s+)",s .lower ())
    for i ,tok in enumerate (tokens ):
        if not tok or tok .isspace ():
            continue 
        if len (tok )>2 and _HAS_LAT_RE .search (tok ):
            tok =tok .translate (_LAT_TO_CYR )
        tok =re .sub (r"[^0-9A-Za-zА-Яа-яЁё\.,:%/\-\+\(\)\?]+","",tok ,flags =re .UNICODE )
        tokens [i ]=tok 
    return _WS_RE .sub (" ","".join (tokens )).strip ()


def _correct_russian_text (s :str )->str :

    return _clean_ocr_text (s )


def _capitalize_first (s :str )->str :
    txt =_clean_ocr_text (s )
    if not txt :
        return txt 
    return txt [:1 ].upper ()+txt [1 :]


def _render_pdf_pages_to_data_urls (pdf_bytes :bytes ,max_pages :int ,zoom :float )->List [str ]:
    try :
        import fitz 
    except Exception as e :
        raise RuntimeError ("PyMuPDF не установлен. Добавь зависимость `pymupdf`.")from e 

    doc =fitz .open (stream =pdf_bytes ,filetype ="pdf")
    urls :List [str ]=[]
    matrix =fitz .Matrix (max (1.0 ,float (zoom )),max (1.0 ,float (zoom )))
    for i in range (min (len (doc ),max (1 ,int (max_pages )))):
        page =doc .load_page (i )
        pix =page .get_pixmap (matrix =matrix ,alpha =False )
        img_bytes =pix .tobytes ("png")
        b64 =base64 .b64encode (img_bytes ).decode ("ascii")
        urls .append (f"data:image/png;base64,{b64 }")
    doc .close ()
    return urls 


def _qwen_vl_ocr_page (image_data_url :str )->Dict [str ,Any ]:
    api_url =(settings .qwen_vl_api_url or "").strip ().rstrip ("/")
    token =(settings .qwen_vl_token or "").strip ()
    model =(settings .qwen_vl_model or "").strip ()
    if not api_url :
        return {"ok":False ,"msg":"Не задан QWEN_VL_API_URL"}
    if not token :
        return {"ok":False ,"msg":"Не задан QWEN_VL_TOKEN"}
    if not model :
        return {"ok":False ,"msg":"Не задан QWEN_VL_MODEL"}

    url =f"{api_url }/v1/chat/completions"
    headers ={"Authorization":f"Bearer {token }","Content-Type":"application/json"}
    prompt =(
    "Это страница PDF со строительной таблицей Б.7 на русском языке. "
    "Сделай OCR максимально точно и верни только распознанный текст страницы "
    "в порядке чтения, без комментариев."
    )
    payload ={
    "model":model ,
    "temperature":0 ,
    "max_tokens":int (settings .qwen_vl_max_tokens ),
    "messages":[
    {
    "role":"user",
    "content":[
    {"type":"text","text":prompt },
    {"type":"image_url","image_url":{"url":image_data_url }},
    ],
    }
    ],
    }
    try :
        resp =requests .post (url ,headers =headers ,json =payload ,timeout =settings .qwen_vl_timeout_seconds )
    except Exception as e :
        return {"ok":False ,"msg":f"Ошибка вызова Qwen-VL API: {e }"}
    if resp .status_code !=200 :
        return {"ok":False ,"msg":f"Qwen-VL API вернул {resp .status_code }","debug":{"body":resp .text [:1000 ]}}
    try :
        data =resp .json ()
    except Exception as e :
        return {"ok":False ,"msg":f"Qwen-VL API вернул не-JSON: {e }"}
    text =((data .get ("choices")or [{}])[0 ].get ("message")or {}).get ("content")or ""
    text =str (text ).strip ()
    if not text :
        return {"ok":False ,"msg":"Qwen-VL вернул пустой текст"}
    return {"ok":True ,"text":text }


def _post_vl_layout_parsing (pdf_bytes :bytes )->Dict [str ,Any ]:
    try :
        pages =_render_pdf_pages_to_data_urls (
        pdf_bytes =pdf_bytes ,
        max_pages =int (settings .qwen_vl_max_pages ),
        zoom =float (settings .qwen_vl_render_zoom ),
        )
    except Exception as e :
        return {"ok":False ,"msg":f"Ошибка рендера PDF для Qwen-VL: {e }"}
    if not pages :
        return {"ok":False ,"msg":"PDF не содержит страниц"}

    lpr :List [Dict [str ,Any ]]=[]
    debug_pages :List [Dict [str ,Any ]]=[]
    for i ,img_url in enumerate (pages ):
        page_res =_qwen_vl_ocr_page (img_url )
        if not page_res .get ("ok"):
            debug_pages .append ({"page_index":i ,"ok":False ,"msg":page_res .get ("msg"),"debug":page_res .get ("debug")})
            continue 
        md_text =str (page_res .get ("text")or "")
        lpr .append ({"markdown":{"text":md_text }})
        debug_pages .append ({"page_index":i ,"ok":True ,"markdown_len":len (md_text )})

    if not lpr :
        return {"ok":False ,"msg":"Qwen-VL не распознал ни одной страницы","debug":debug_pages }
    return {"ok":True ,"result":{"layoutParsingResults":lpr },"debug":debug_pages }


def _split_md_row (line :str )->List [str ]:
    line =line .strip ()
    if line .startswith ("|"):
        line =line [1 :]
    if line .endswith ("|"):
        line =line [:-1 ]
    return [_cleanup_cell_text (c )for c in line .split ("|")]


def _extract_rows_from_md_tables (md_text :str )->List [List [str ]]:
    if not (md_text or "").strip ():
        return []
    lines =md_text .splitlines ()
    rows :List [List [str ]]=[]
    i =0 
    while i <len (lines ):
        if i +1 >=len (lines ):
            break 
        if _PIPED_LINE_RE .match (lines [i ])and _MD_TABLE_SEP_RE .match (lines [i +1 ]):
            i +=2 
            while i <len (lines )and _PIPED_LINE_RE .match (lines [i ]):
                cells =_split_md_row (lines [i ])
                if any (cells ):
                    rows .append (cells )
                i +=1 
            continue 
        i +=1 
    return rows 


def _extract_rows_from_pipe_lines_loose (md_text :str )->List [List [str ]]:
    if not (md_text or "").strip ():
        return []
    rows :List [List [str ]]=[]
    for line in md_text .splitlines ():
        if "|"not in line :
            continue 

        if re .fullmatch (r"\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*",line ):
            continue 
        parts =_split_md_row (line )
        if len (parts )>=3 and any (parts ):
            rows .append (parts )
    return rows 


def _extract_rows_from_html_tables (md_text :str )->List [List [str ]]:
    if "<table"not in (md_text or "").lower ():
        return []
    try :
        dfs =pd .read_html (io .StringIO (md_text ))
    except Exception :
        return []
    rows :List [List [str ]]=[]
    for df in dfs :
        if df is None or df .empty :
            continue 
        for _ ,row in df .fillna ("").iterrows ():
            vals =[_cleanup_cell_text (str (v ))for v in row .tolist ()]
            if any (vals ):
                rows .append (vals )
    return rows 


def _extract_rows_from_layout_result (result :Dict [str ,Any ])->Tuple [List [List [str ]],List [Dict [str ,Any ]]]:
    lpr =result .get ("layoutParsingResults")
    if not isinstance (lpr ,list ):
        return [],[{"msg":"layoutParsingResults отсутствует или не список"}]
    all_rows :List [List [str ]]=[]
    debug_pages :List [Dict [str ,Any ]]=[]
    for i ,page in enumerate (lpr ):
        md_text =""
        if isinstance (page ,dict ):
            md =page .get ("markdown")
            if isinstance (md ,dict ):
                md_text =str (md .get ("text")or "")
        page_rows =_extract_rows_from_md_tables (md_text )
        source ="markdown_pipes"
        if not page_rows :
            page_rows =_extract_rows_from_html_tables (md_text )
            if page_rows :
                source ="html_table"
        if not page_rows :
            page_rows =_extract_rows_from_pipe_lines_loose (md_text )
            if page_rows :
                source ="pipe_lines_loose"
        debug_pages .append (
        {
        "page_index":i ,
        "markdown_len":len (md_text ),
        "table_rows":len (page_rows ),
        "source":source ,
        "preview_first_rows":page_rows [:5 ],
        }
        )
        all_rows .extend (page_rows )
    return all_rows ,debug_pages 


def _trim_empty_rows_and_cols (raw_rows :List [List [str ]])->List [List [str ]]:
    if not raw_rows :
        return raw_rows 
    max_cols =max (len (r )for r in raw_rows )
    norm_rows =[r +[""]*(max_cols -len (r ))for r in raw_rows ]
    norm_rows =[row for row in norm_rows if any ((cell or "").strip ()for cell in row )]
    if not norm_rows :
        return []
    max_cols =max (len (r )for r in norm_rows )
    keep_cols =[any ((row [c ]or "").strip ()for row in norm_rows )for c in range (max_cols )]
    return [[cell for cell ,keep in zip (row ,keep_cols )if keep ]for row in norm_rows ]


def _to_xlsx_bytes (df :pd .DataFrame )->bytes :
    bio =io .BytesIO ()
    with pd .ExcelWriter (bio ,engine ="openpyxl")as writer :
        df .to_excel (writer ,index =False ,header =False ,sheet_name ="raw_table")
    return bio .getvalue ()


def _to_pipeline_b7_xlsx_bytes (parsed_rows :List [Dict [str ,Any ]])->bytes :
    from openpyxl import Workbook 

    rows_for_excel :List [List [Any ]]=[]
    current_section =None 
    for row in parsed_rows :
        section_title =str (row .get ("section_title")or "").strip ()or "Unsectioned"
        work_name =str (row .get ("work_name")or "").strip ()
        if not work_name :
            continue 
        if section_title !=current_section :
            rows_for_excel .append ([f"{section_title } contractor","-",0.0 ,""])
            current_section =section_title 
        week =parse_num (row .get ("fact_week"))
        unit =str (row .get ("unit")or "").strip ()or "-"
        rows_for_excel .append ([work_name ,unit ,float (week )if week is not None else 0.0 ,""])

    wb =Workbook ()
    ws =wb .active 
    ws .title ="B7"
    ws .append (["Work name","Unit","Works done","Note"])
    ws .append (["","","week",""])
    for row in rows_for_excel :
        ws .append (row )

    bio =io .BytesIO ()
    wb .save (bio )
    return bio .getvalue ()


def extract_b7_raw_table_from_pdf (pdf_bytes :bytes )->Dict [str ,Any ]:
    logger .info ("extract_b7_raw_table_from_pdf started: bytes=%s",len (pdf_bytes ))
    api_res =_post_vl_layout_parsing (pdf_bytes )
    if not api_res .get ("ok"):
        logger .warning ("extract_b7_raw_table_from_pdf failed: %s",api_res .get ("msg"))
        return {"ok":False ,"msg":api_res .get ("msg","Не удалось вызвать OCR API"),"rows":[],"debug":api_res .get ("debug")}

    raw_rows ,debug_pages =_extract_rows_from_layout_result (api_res ["result"])
    raw_rows =_trim_empty_rows_and_cols (raw_rows )
    logger .info ("extract_b7_raw_table_from_pdf parsed rows=%s",len (raw_rows ))

    if not raw_rows :
        return {"ok":False ,"msg":"OCR API не вернул таблиц с данными","rows":[],"debug":debug_pages }

    return {"ok":True ,"rows":raw_rows ,"debug":debug_pages ,"xlsx_bytes":_to_xlsx_bytes (pd .DataFrame (raw_rows ))}


def _cell (row :List [Any ],idx :int )->str :
    if idx <0 or idx >=len (row ):
        return ""
    v =row [idx ]
    return ""if v is None else str (v ).strip ()


def _is_index_legend_row (row :List [Any ])->bool :
    vals =[_cell (row ,i )for i in range (min (len (row ),15 ))]
    dense =[v for v in vals if v ]
    if len (dense )<10 :
        return False 
    return all (re .fullmatch (r"\d+",v or "")for v in dense [:10 ])


def _detect_header_columns (raw_rows :List [List [Any ]])->Dict [str ,Optional [int ]]:
    if not raw_rows :
        return {"no_col":None ,"name_col":None ,"unit_col":None ,"total_col":None ,"fact_week_col":None }

    max_cols =max (len (r )for r in raw_rows )
    scan_rows =min (len (raw_rows ),10 )
    norm_rows =[[norm_text (_cell (raw_rows [i ],c ))for c in range (max_cols )]for i in range (scan_rows )]

    no_col :Optional [int ]=None 
    name_col :Optional [int ]=None 
    unit_col :Optional [int ]=None 
    total_col :Optional [int ]=None 
    fact_week_col :Optional [int ]=None 

    for c in range (max_cols ):
        col_vals =[norm_rows [i ][c ]for i in range (scan_rows )]
        if name_col is None and any ("наименование"in v for v in col_vals ):
            name_col =c 
        if unit_col is None and any (("ед"in v and "изм"in v )for v in col_vals ):
            unit_col =c 
        if total_col is None and any (("всего"in v and "проект"in v )for v in col_vals ):
            total_col =c 
        if no_col is None and any (("n"in v and "/"in v )or ("№"in v )for v in col_vals ):
            no_col =c 



    fact_hits :List [int ]=[]
    for i in range (scan_rows ):
        row_vals =[norm_rows [i ][c ]for c in range (max_cols )]
        row_hits =[c for c ,v in enumerate (row_vals )if v =="факт"or v .endswith (" факт")or " факт "in f" {v } "]
        if len (row_hits )>=2 :
            fact_hits =row_hits 
    if fact_hits :
        fact_week_col =fact_hits [-1 ]

    week_cols :List [int ]=[]
    for c in range (max_cols ):
        if any ("за неделю"in norm_rows [i ][c ]for i in range (scan_rows )):
            week_cols .append (c )

    if week_cols :
        week_cols =sorted (set (week_cols ))
        for c in week_cols :
            if any (norm_rows [i ][c ]=="факт"or " факт"in norm_rows [i ][c ]for i in range (scan_rows )):
                fact_week_col =c 
                break 
        if fact_week_col is None :
            fact_week_col =week_cols [len (week_cols )//2 ]



    legend_map :Dict [str ,int ]={}
    for row in raw_rows [:min (len (raw_rows ),40 )]:
        if not _is_index_legend_row (row ):
            continue 
        for c in range (len (row )):
            v =_cell (row ,c )
            if re .fullmatch (r"\d+",v or ""):
                legend_map [v ]=c 
        if legend_map :
            break 

    if legend_map :
        no_col =legend_map .get ("1",no_col )
        name_col =legend_map .get ("2",name_col )
        unit_col =legend_map .get ("3",unit_col )
        total_col =legend_map .get ("4",total_col )
        fact_week_col =legend_map .get ("13",fact_week_col )

    return {
    "no_col":no_col ,
    "name_col":name_col ,
    "unit_col":unit_col ,
    "total_col":total_col ,
    "fact_week_col":fact_week_col ,
    }


def _find_data_start (raw_rows :List [List [Any ]])->int :
    for i ,row in enumerate (raw_rows ):
        if _is_index_legend_row (row ):
            continue 
        for t in [_cell (row ,0 ),_cell (row ,1 ),_cell (row ,2 )]:
            if _NO_RE .match (t .replace (",",".")):
                if not _is_index_legend_row (row ):
                    return i 
        txt_norm =norm_text (" ".join (str (x )for x in row if str (x ).strip ()))
        if any (k in txt_norm for k in ["демонтаж","монолит","кладка","монтаж","работ"]):
            nums =[parse_num (_cell (row ,j ))for j in range (len (row ))]
            if any (x is not None for x in nums ):
                return i 
    return 0 


def _find_no_in_row (row :List [Any ])->Optional [str ]:
    scan_cells =[_clean_ocr_text (_cell (row ,j ))for j in range (min (3 ,len (row )))]



    for src_clean in scan_cells :
        if not src_clean :
            continue 
        m_multi =re .match (r"^(\d+(?:\.\d+)*(?:\s*[;,]\s*\d+(?:\.\d+)*)+)\b",src_clean )
        if m_multi :
            raw =m_multi .group (1 )
            parts =re .findall (r"\d+(?:\.\d+)*",raw )
            if parts :
                delim ="; "if ";"in raw else ", "
                return delim .join (parts )


        tokens =re .findall (r"\d+(?:\.\d+)*",src_clean )
        if len (tokens )>=2 and re .fullmatch (r"[\d\s\.,;:/\-]+",src_clean ):
            prefix =tokens [0 ].split (".",1 )[0 ]
            if all (t .split (".",1 )[0 ]==prefix for t in tokens [:2 ]):
                return "; ".join (tokens [:2 ])



    pure_tokens :List [str ]=[]
    for src_clean in scan_cells [:2 ]:
        if re .fullmatch (r"\d+(?:\.\d+)*",src_clean or ""):
            pure_tokens .append (src_clean )
    if len (pure_tokens )>=2 :
        first_prefix =pure_tokens [0 ].split (".",1 )[0 ]
        if all (t .split (".",1 )[0 ]==first_prefix for t in pure_tokens ):
            return "; ".join (pure_tokens )


    for src_clean in scan_cells :
        if not src_clean :
            continue 
        m =re .search (r"\d+(?:\.\d+)*",src_clean )
        if not m :
            continue 
        t =m .group (0 )
        if _NO_RE .match (t ):
            return t 
    return None 


def _guess_name_col (raw_rows :List [List [Any ]],start_i :int )->int :
    if not raw_rows :
        return 1 
    max_cols =max (len (r )for r in raw_rows )
    scores =[0 ]*max_cols 
    for row in raw_rows [start_i :min (len (raw_rows ),start_i +20 )]:
        for c in range (max_cols ):
            val =_cell (row ,c )
            if not val :
                continue 
            t =norm_text (val )
            letters =sum (ch .isalpha ()for ch in t )
            digits =sum (ch .isdigit ()for ch in t )
            if letters >=5 and letters >digits :
                scores [c ]+=letters 
    return max (range (max_cols ),key =lambda i :scores [i ])if max_cols >0 else 1 


def _guess_unit_cols (raw_rows :List [List [Any ]],start_i :int ,name_col :int )->List [int ]:
    max_cols =max (len (r )for r in raw_rows )if raw_rows else 0 
    cand_scores :Dict [int ,int ]={}
    for c in range (max_cols ):
        if c ==name_col :
            continue 
        score =0 
        for row in raw_rows [start_i :min (len (raw_rows ),start_i +30 )]:
            if norm_unit (_cell (row ,c ))in _UNIT_CAND :
                score +=1 
        if score >0 :
            cand_scores [c ]=score 
    cols =sorted (cand_scores .keys (),key =lambda c :(-cand_scores [c ],abs (c -name_col )))
    return cols [:3 ]


def _guess_fact_week_cols (raw_rows :List [List [Any ]],start_i :int )->List [int ]:
    if not raw_rows :
        return []
    max_cols =max (len (r )for r in raw_rows )
    scores :Dict [int ,int ]={}
    for c in range (max_cols ):
        score =0 
        for row in raw_rows [start_i :min (len (raw_rows ),start_i +40 )]:
            if parse_num (_cell (row ,c ))is not None :
                score +=1 
        scores [c ]=score 
    candidates =sorted ([c for c in range (max_cols )if scores .get (c ,0 )>=3 ])
    if candidates :
        candidates =[c for c in candidates if c >=max_cols //2 ]
    if not candidates and max_cols >0 :
        candidates =list (range (max (0 ,max_cols -6 ),max_cols ))
    return candidates 


def _extract_unit (row :List [Any ],unit_cols :List [int ])->str :
    for c in unit_cols :
        raw =_cell (row ,c )
        raw_low =raw .lower ().replace ("m","м")

        m =re .search (r"(\d+)\s*м\s*([23])\b",raw_low )
        if m :
            return f"{m .group (1 )} м{m .group (2 )}"

        nu =norm_unit (raw )
        if nu in _UNIT_CAND :
            return nu 
        low =norm_text (raw_low )
        if "м3"in low or "m3"in low :
            return "м3"
        if "м2"in low or "m2"in low :
            return "м2"
        if "кг"in low :
            return "кг"
        if "шт"in low :
            return "шт"
        if "%"in low :
            return "%"
        if "компл"in low :
            return "компл"
    return ""


def _extract_work_name (row :List [Any ],no :Optional [str ],name_col :int )->str :
    name =_cell (row ,name_col )
    if not name :
        for c in [name_col -1 ,name_col +1 ,1 ,2 ,3 ]:
            if c >=0 :
                name =_cell (row ,c )
                if name :
                    break 
    if no and name .startswith (no ):
        name =name [len (no ):].strip ()
    return _capitalize_first (_correct_russian_text (name .strip ()))


def _parse_ocrish_num (raw :str )->Optional [float ]:
    txt =(raw or "").strip ()
    if not txt :
        return None 
    v =parse_num (txt )
    if v is None :
        return None 
    low =txt .lower ().replace (" ","")
    has_decimal_sep =(","in low )or ("."in low )
    if not has_decimal_sep and re .fullmatch (r"-?\d{4,}",low ):
        return float (v )/100.0 
    return float (v )


def _extract_fact_week (row :List [Any ],fact_cols :List [int ])->Optional [float ]:
    vals :List [Tuple [int ,float ,str ]]=[]
    for c in fact_cols :
        raw =_cell (row ,c )
        v =_parse_ocrish_num (raw )
        if v is not None :
            vals .append ((c ,float (v ),raw ))
    if not vals :
        return None 
    vals =sorted (vals ,key =lambda x :x [0 ])
    return vals [0 ][1 ]if len (vals )==1 else vals [-2 ][1 ]


def _extract_fact_week_raw_token (row :List [Any ],fact_cols :List [int ])->str :
    vals :List [Tuple [int ,str ]]=[]
    for c in fact_cols :
        raw =_cell (row ,c )
        if _parse_ocrish_num (raw )is not None :
            vals .append ((c ,raw ))
    if not vals :
        return ""
    vals =sorted (vals ,key =lambda x :x [0 ])
    return vals [0 ][1 ]if len (vals )==1 else vals [-2 ][1 ]


def _normalize_fact_week_by_total (fact_week :Optional [float ],total_value :Optional [float ],raw_token :str ="")->Optional [float ]:
    if fact_week is None :
        return None 
    if total_value is None or total_value <=0 :
        return fact_week 
    val =float (fact_week )
    raw =_clean_ocr_text (raw_token ).replace (" ","")

    if re .fullmatch (r"0\d{2}",raw or "")and 1.0 <=val <=9.0 :
        return val /100.0 
    if val >total_value *1.5 and val >=100 :
        for div in (10.0 ,100.0 ,1000.0 ):
            cand =val /div 
            if cand <=total_value *1.5 :
                return cand 
    return val 


def _normalize_no_value (no :str ,work_name :str ="")->str :
    txt =_clean_ocr_text (no )
    if not txt :
        return txt 

    if re .fullmatch (r"\d{4}",txt ):
        a ,b =int (txt [:2 ]),int (txt [2 :])
        if 1 <=a <=99 and 1 <=b <=99 and abs (a -b )<=1 :
            if "окон"in norm_text (work_name ):
                return f"{a }, {b }"
    return txt 


def _fill_merged_rows (parsed_rows :List [Dict [str ,Any ]])->List [Dict [str ,Any ]]:
    if not parsed_rows :
        return parsed_rows 
    fixed :List [Dict [str ,Any ]]=[]
    for i ,row in enumerate (parsed_rows ):
        row2 =dict (row )
        no =str (row2 .get ("no")or "")
        if no and "."in no :
            prefix =no .split (".",1 )[0 ]
            unit_missing =not str (row2 .get ("unit")or "").strip ()
            if unit_missing :
                for j in range (i -1 ,-1 ,-1 ):
                    prev =parsed_rows [j ]
                    prev_no =str (prev .get ("no")or "")
                    if not prev_no :
                        continue 
                    if prev_no ==prefix or prev_no .startswith (f"{prefix }."):
                        if unit_missing and str (prev .get ("unit")or "").strip ():
                            row2 ["unit"]=prev .get ("unit")
                            unit_missing =False 
                        if not unit_missing :
                            break 
        fixed .append (row2 )
    return fixed 


def _is_stop_row (row :List [Any ])->bool :
    txt =norm_text (" ".join (str (x )for x in row if str (x ).strip ()))
    return "ведущий инженер"in txt or "смирнов"in txt 


def extract_b7_rows_from_raw_table (raw_rows :List [List [Any ]])->Dict [str ,Any ]:
    if not raw_rows :
        return {"ok":False ,"rows":[],"debug":{"msg":"raw_rows пустой"}}

    start_i =_find_data_start (raw_rows )
    header_cols =_detect_header_columns (raw_rows )

    name_col =header_cols .get ("name_col")
    if name_col is None :
        name_col =_guess_name_col (raw_rows ,start_i )

    unit_col =header_cols .get ("unit_col")
    if unit_col is not None :
        unit_cols =[unit_col ]
    else :
        unit_cols =_guess_unit_cols (raw_rows ,start_i ,name_col )

    fact_col =header_cols .get ("fact_week_col")
    if fact_col is not None :
        fact_cols =[fact_col ]
    else :
        fact_cols =_guess_fact_week_cols (raw_rows ,start_i )
    total_col =header_cols .get ("total_col")

    candidates :List [Dict [str ,Any ]]=[]
    for i in range (start_i ,len (raw_rows )):
        row =raw_rows [i ]
        if _is_stop_row (row ):
            break 
        no =_find_no_in_row (row )
        work_name =_extract_work_name (row ,no ,name_col )
        unit =_extract_unit (row ,unit_cols )
        fact_week =_extract_fact_week (row ,fact_cols )
        fact_week_raw =_extract_fact_week_raw_token (row ,fact_cols )
        total_value =parse_num (_cell (row ,total_col ))if total_col is not None else None 
        fact_week =_normalize_fact_week_by_total (fact_week ,total_value ,fact_week_raw )
        txt_norm =norm_text (work_name )
        if "количество человеческих ресурсов"in txt_norm or "количество технических ресурсов"in txt_norm :
            continue 
        if not no and not txt_norm :
            continue 
        if not txt_norm :
            continue 
        candidates .append (
        {
        "no":no ,
        "work_name":work_name ,
        "unit":unit ,
        "fact_week":fact_week ,
        "txt_norm":txt_norm ,
        }
        )

    all_nos =[str (c .get ("no")or "")for c in candidates if c .get ("no")]
    parsed_rows :List [Dict [str ,Any ]]=[]
    current_section :Optional [str ]=None 
    current_section_no :Optional [str ]=None 
    section_by_prefix :Dict [str ,str ]={}

    for c in candidates :
        no =str (c .get ("no")or "")
        work_name =str (c .get ("work_name")or "")
        no =_normalize_no_value (no ,work_name )
        is_multi_no =bool (re .search (r"[;,]",no ))
        if no and _INT_RE .match (no ):
            current_section =work_name 
            current_section_no =no 
            section_by_prefix [no ]=work_name 
            has_children =any (n !=no and n .startswith (f"{no }.")for n in all_nos )
            if not has_children :
                parsed_rows .append (
                {
                "no":no ,
                "work_name":work_name ,
                "unit":c .get ("unit"),
                "fact_week":c .get ("fact_week"),
                "section_title":current_section ,
                }
                )
            continue 

        section_title =current_section 
        if no and "."in no :
            prefix =no .split (".",1 )[0 ]
            section_title =section_by_prefix .get (prefix )


            if not section_title and (not current_section_no or prefix !=current_section_no ):
                section_title =work_name 
        elif is_multi_no :

            section_title =work_name 

        parsed_rows .append (
        {
        "no":no ,
        "work_name":work_name ,
        "unit":c .get ("unit"),
        "fact_week":c .get ("fact_week"),
        "section_title":section_title ,
        }
        )

    for row in parsed_rows :
        row ["work_name"]=_clean_ocr_text (str (row .get ("work_name")or ""))
        row ["section_title"]=_clean_ocr_text (str (row .get ("section_title")or ""))



    has_children_by_int :Dict [str ,bool ]={}
    section_name_by_int :Dict [str ,str ]={}
    for row in parsed_rows :
        no =str (row .get ("no")or "")
        if no and _INT_RE .match (no ):
            has_children_by_int [no ]=any (
            str (r .get ("no")or "").startswith (f"{no }.")for r in parsed_rows if str (r .get ("no")or "")!=no 
            )
            section_name_by_int [no ]=str (row .get ("work_name")or "").strip ()

    for row in parsed_rows :
        no =str (row .get ("no")or "")
        if no and _INT_RE .match (no ):
            if not has_children_by_int .get (no ,False ):
                row ["section_title"]=row .get ("work_name")or row .get ("section_title")
            else :
                row ["section_title"]=section_name_by_int .get (no )or row .get ("section_title")
        elif no and "."in no :
            prefix =no .split (".",1 )[0 ]
            if prefix in section_name_by_int :
                row ["section_title"]=section_name_by_int [prefix ]
        row ["section_title"]=_clean_ocr_text (str (row .get ("section_title")or ""))

    parsed_rows =_fill_merged_rows (parsed_rows )
    for row in parsed_rows :
        if row .get ("fact_week")is None :
            row ["fact_week"]=0.0 
        if row .get ("unit")is None :
            row ["unit"]=""

    return {
    "ok":True ,
    "rows":parsed_rows ,
    "debug":{
    "start_i":start_i ,
    "header_cols":header_cols ,
    "name_col":name_col ,
    "unit_cols":unit_cols ,
    "fact_cols":fact_cols ,
    "parsed_rows":len (parsed_rows ),
    "preview_rows":parsed_rows [:10 ],
    },
    }


def extract_b7_rows_from_pdf (pdf_bytes :bytes )->Dict [str ,Any ]:
    raw_res =extract_b7_raw_table_from_pdf (pdf_bytes )
    if not raw_res .get ("ok"):
        return raw_res 
    parsed_res =extract_b7_rows_from_raw_table (raw_res ["rows"])
    parsed_rows =parsed_res .get ("rows",[])
    return {
    "ok":parsed_res .get ("ok",False ),
    "rows":parsed_rows ,
    "debug":{"raw":raw_res .get ("debug"),"parsed":parsed_res .get ("debug")},
    "raw_rows":raw_res .get ("rows",[]),
    "xlsx_bytes":_to_pipeline_b7_xlsx_bytes (parsed_rows ),
    "raw_xlsx_bytes":raw_res .get ("xlsx_bytes"),
    }


def build_b7_pipeline_xlsx_from_rows (rows :List [Dict [str ,Any ]])->bytes :
    parsed_rows :List [Dict [str ,Any ]]=[]
    for row in rows or []:
        if not isinstance (row ,dict ):
            continue 
        work_name =_clean_ocr_text (str (row .get ("work_name")or ""))
        section_title =_clean_ocr_text (str (row .get ("section_title")or ""))
        if not work_name :
            continue 
        parsed_rows .append (
        {
        "no":str (row .get ("no")or ""),
        "work_name":work_name ,
        "unit":str (row .get ("unit")or ""),
        "fact_week":parse_num (row .get ("fact_week"))or 0.0 ,
        "section_title":section_title ,
        }
        )
    return _to_pipeline_b7_xlsx_bytes (parsed_rows )


def extract_b7_pipeline_xlsx_from_pdf (pdf_bytes :bytes )->Dict [str ,Any ]:
    res =extract_b7_rows_from_pdf (pdf_bytes )
    if not res .get ("ok"):
        return res 
    if not res .get ("rows"):
        return {"ok":False ,"msg":"После OCR не найдено строк для формирования Excel","rows":[],"debug":res .get ("debug")}
    return {"ok":True ,"rows":res .get ("rows",[]),"xlsx_bytes":res .get ("xlsx_bytes"),"debug":res .get ("debug")}
