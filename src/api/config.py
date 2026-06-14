import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://ratings:ratings@localhost:5432/ratings"
    data_dir: str = "/data"
    log_level: str = "INFO"
    default_page_size: int = 100
    max_page_size: int = 1000
    # Concurrency: override via PIPELINE_CPU_WORKERS / PIPELINE_IO_WORKERS env vars.
    # Defaults keep the worker count conservative so the pipeline doesn't starve the API.
    pipeline_cpu_workers: int = max(1, (os.cpu_count() or 2) - 1)
    pipeline_io_workers: int = 2

    model_config = {"env_file": ".env"}


settings = Settings()
