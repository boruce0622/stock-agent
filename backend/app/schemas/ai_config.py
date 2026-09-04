from urllib.parse import urlparse

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.llm.providers import PROVIDER_PRESETS


class AIConfigPayload(BaseModel):
    provider: str = "openai"
    model: str = Field(min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: SecretStr | None = None
    enabled: bool = True

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        if value not in PROVIDER_PRESETS:
            raise ValueError("不支持的 AI 供应商")
        return value

    @field_validator("model")
    @classmethod
    def clean_model(cls, value: str) -> str:
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        is_local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
        if parsed.scheme != "https" and not is_local_http:
            raise ValueError("Base URL 必须使用 HTTPS；本地 localhost 可使用 HTTP")
        if not parsed.netloc:
            raise ValueError("Base URL 格式无效")
        return cleaned


class AIConfigOut(BaseModel):
    configured: bool
    provider: str = "openai"
    model: str = ""
    base_url: str | None = None
    api_key_masked: str | None = None
    enabled: bool = False


class AIConnectionTestOut(BaseModel):
    ok: bool
    model: str
    latency_ms: int
    message: str


class AIProviderOut(BaseModel):
    id: str
    name: str
    base_url: str | None
    model_examples: list[str]
    docs_url: str
    description: str
