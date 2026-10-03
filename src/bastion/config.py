from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Setting(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="Bastion_", env_file=".env",extra="ignore")


    env: Literal["local","test","hosted"] = "local"
    demo_mode: bool = False
    jwt_secret: str = ""
    database_url_owner: str = "postgresql://bastion_owner:bastion_owner@localhost:5432/bastion"
    database_url_app: str = "postgresql://bastion_app:bastion_app@localhost:5432/bastion"
    database_url_worker: str = "postgresql://bastion_worker:bastion_worker@localhost:5432/bastion"

@lru_cache
def get_settings() -> Setting:
    return Setting()