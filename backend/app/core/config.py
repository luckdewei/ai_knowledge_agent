from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""

    # 应用配置
    app_name: str = "AI Knowledge Agent"
    app_version: str = "0.1.0"
    debug: bool = Field(default=False)
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS 配置
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"]
    )

    # DeepSeek API 配置
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"

    # 向量模型配置（硅基流动）
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    embedding_base_url: str = "https://api.siliconflow.cn/v1/embeddings"
    embedding_model: str = "BAAI/bge-m3"

    # 语音识别配置（硅基流动，未设置 SPEECH_API_KEY 时复用 EMBEDDING_API_KEY）
    speech_api_key: str = Field(default="", alias="SPEECH_API_KEY")
    speech_base_url: str = "https://api.siliconflow.cn/v1/audio/transcriptions"
    speech_model: str = "FunAudioLLM/SenseVoiceSmall"

    # 数据库配置
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres123@localhost:5432/knowledge_db",
        alias="DATABASE_URL",
    )

    # Redis 配置（用于缓存和任务队列）
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # SMTP 配置
    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: Optional[str] = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: Optional[str] = Field(default=None, alias="SMTP_PASSWORD")

    # Tavily API 配置
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")

    # 加载环境变量
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


# 全局配置实例
settings = Settings()
