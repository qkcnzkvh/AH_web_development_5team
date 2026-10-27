from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DB_USER: str = "root"
    DB_PASSWORD: str = "password1234"
    DB_HOST: str = "localhost"
    DB_PORT: str = "3306"
    DB_NAME: str = "ai_health"
    # JWT (Access 30분, Refresh 7일 — 4일차 User API 공통 규칙)
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # HTTPS 환경에서만 True (로컬 http 개발 환경은 False)
    COOKIE_SECURE: bool = False

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }


settings = Settings()
