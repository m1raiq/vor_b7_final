from pydantic_settings import BaseSettings ,SettingsConfigDict 


class Settings (BaseSettings ):
    database_url :str 
    qwen_vl_api_url :str =""
    qwen_vl_token :str =""
    qwen_vl_model :str ="Qwen/Qwen3-VL-235B-A22B-Instruct"
    qwen_vl_timeout_seconds :int =180 
    qwen_vl_render_zoom :float =2.0 
    qwen_vl_max_pages :int =2 
    qwen_vl_max_tokens :int =8000 
    jwt_secret_key :str ="change-me-in-env"
    jwt_algorithm :str ="HS256"
    jwt_access_token_expire_minutes :int =480 
    auth_seed_admin_login :str ="admin"
    auth_seed_admin_email :str ="admin@local"
    auth_seed_admin_password :str ="admin123"
    auth_seed_admin_full_name :str ="Administrator"

    model_config =SettingsConfigDict (
    env_file =".env",
    env_prefix ="",
    extra ="ignore",
    )


settings =Settings ()
