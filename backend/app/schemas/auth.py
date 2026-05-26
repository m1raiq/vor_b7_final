import uuid 
from pydantic import BaseModel ,Field 


class LoginIn (BaseModel ):
    login :str =Field (min_length =1 ,max_length =320 )
    password :str =Field (min_length =1 )


class TokenOut (BaseModel ):
    access_token :str 
    token_type :str ="bearer"
    expires_in :int 
    role :str 
    login :str 
    full_name :str 


class UserOut (BaseModel ):
    id :uuid .UUID 
    login :str 
    full_name :str 
    role :str 
    is_active :bool 

    class Config :
        from_attributes =True 


class UserCreate (BaseModel ):
    login :str =Field (min_length =1 ,max_length =320 )
    password :str =Field (min_length =6 ,max_length =128 )
    full_name :str =Field (default ="",max_length =255 )
    role :str =Field (default ="user")
    is_active :bool =True 


class RegisterIn (BaseModel ):
    login :str =Field (min_length =1 ,max_length =320 )
    password :str =Field (min_length =6 ,max_length =128 )
    full_name :str =Field (default ="",max_length =255 )


class UserUpdate (BaseModel ):
    full_name :str |None =Field (default =None ,max_length =255 )
    role :str |None =None 
    is_active :bool |None =None 
    password :str |None =Field (default =None ,min_length =6 ,max_length =128 )
