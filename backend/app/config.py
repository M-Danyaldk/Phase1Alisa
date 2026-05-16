from functools import lru_cache
from pathlib import Path
from secrets import compare_digest
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / '.env'

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ENV_FILE, extra='ignore')

    app_env: str = 'development'
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173'
    database_path: str = './msalisia_phase1.db'
    uploads_path: str = './uploads'
    admin_access_token: str = 'msalisia-admin-demo'

    primary_llm_provider: str = 'claude'
    fallback_llm_provider: str = 'groq'
    fallback_on_llm_error: bool = True

    anthropic_api_key: str = ''
    anthropic_model: str = 'claude-sonnet-4-5'
    anthropic_api_url: str = 'https://api.anthropic.com/v1/messages'

    groq_api_key: str = ''
    groq_model: str = 'llama-3.3-70b-versatile'
    groq_api_url: str = 'https://api.groq.com/openai/v1/chat/completions'

    max_output_tokens: int = 1200
    chat_max_output_tokens: int = 800
    assessment_max_output_tokens: int = 1600
    report_max_output_tokens: int = 1600
    homework_max_output_tokens: int = 1000
    classifier_max_output_tokens: int = 220
    temperature: float = 0.35

    supabase_url: str = ''
    supabase_anon_key: str = ''
    supabase_service_role_key: str = ''
    signup_code_ttl_minutes: int = 10
    signup_code_max_attempts: int = 5

    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(',') if x.strip()]

    def admin_token_valid(self, token: str) -> bool:
        expected = self.admin_access_token.strip()
        provided = token.strip()
        return bool(expected) and compare_digest(expected, provided)

    def normalized_llm_provider(self, provider_name: str) -> str:
        return provider_name.strip().lower()

    def llm_provider_supported(self, provider_name: str) -> bool:
        return self.normalized_llm_provider(provider_name) in {'claude', 'groq'}

@lru_cache
def get_settings() -> Settings:
    return Settings()
