from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_secret: str = ""
    web_origin: str = "http://localhost:3000"
    public_base_url: str = "http://localhost:3000"
    jobs_secret: str = ""
    demo_key: str = ""
    reminder_demo_delay_sec: int = 0  # >0: reminders fire N s / 2N s after booking (prototype demo speed)
    prototype_mode: bool = False  # one-click admin login + hub data (demo only)
    demo_mode: bool = False  # enables destructive demo endpoints (reset). Never on for a real salon.
    trust_proxy: bool = True  # read client IP from X-Forwarded-For (set false if the API is directly exposed)
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    whatsapp_mode: str = "simulator"  # live | simulator | both
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_template_confirmed: str = "slotpay_booking_confirmed"
    whatsapp_template_reminder: str = "slotpay_appointment_reminder"
    whatsapp_template_cancelled: str = "slotpay_booking_cancelled"


@lru_cache
def get_settings() -> Settings:
    return Settings()
