from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://ratings:ratings@localhost:5432/ratings"
    data_dir: str = "/data"
    log_level: str = "INFO"
    default_page_size: int = 100
    max_page_size: int = 1000

    model_config = {"env_file": ".env"}


settings = Settings()
