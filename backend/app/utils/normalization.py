import re 
from typing import Any 


def norm_text (s :str )->str :
    s =(s or "").strip ().lower ()
    s =re .sub (r"\s+"," ",s )
    return s 


def norm_unit (u :Any )->str :
    if u is None :
        return ""

    u =str (u ).strip ().lower ()
    if not u or u in {"nan","none"}:
        return ""

    u =u .replace (",",".")
    u =re .sub (r"\s+","",u )

    if u in {"м2","m2","м²"}:
        return "м2"

    if u in {"м3","m3","м³"}:
        return "м3"

    if u in {"м.п.","мп","м.п","mp","m.p"}:
        return "м.п."

    if u in {"т","тонн","тонна","ton","tons"}:
        return "т"

    if u in {"шт","pcs","pc"}:
        return "шт"

    if u in {"%","проц","проц."}:
        return "%"

    return u 


def parse_num (v :Any ):
    if v is None :
        return None 

    if isinstance (v ,(int ,float )):
        try :
            return float (v )
        except Exception :
            return None 

    s =str (v ).strip ()
    if s .lower ()in {"nan","none",""}:
        return None 

    s =s .replace (" ","").replace (",",".")
    try :
        return float (s )
    except Exception :
        return None 


def row_full_text (row_values )->str :
    parts =[]
    for x in row_values :
        s =str (x ).strip ()
        if not s or s .lower ()in {"nan","none"}:
            continue 
        parts .append (s )
    return " ".join (parts )