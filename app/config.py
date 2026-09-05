from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
class Settings(BaseSettings):
    TELEGRAM_TOKEN: str
    WEBHOOK_URL: str = ""
    API_BASE_URL: str = "https://api.telegram.org"
    BOT_NAME: str = "National ID converter"
    AUTHORIZED_USER_IDS: str = ""
    REQUIRED_GROUP_ID: int = 0 
    TELEGRAM_WEBHOOK_SECRET: str = ""
    MAX_BATCH_SIZE: int = 15
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    UPLOAD_DIR: Path = BASE_DIR / "storage" / "uploads"
    OUTPUT_DIR: Path = BASE_DIR / "storage" / "outputs"
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",          
        case_sensitive=True
    )
    @property
    def authorized_users(self) -> set[int]:
        try:
            if not self.AUTHORIZED_USER_IDS:
                return set()
            return {int(uid.strip()) for uid in self.AUTHORIZED_USER_IDS.split(",")}
        except Exception as e:
            print(f" Error parsing AUTHORIZED_USER_IDS: {e}")
            return set()
settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)