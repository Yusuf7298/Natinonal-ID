from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
class Settings(BaseSettings):
    TELEGRAM_TOKEN: str
    WEBHOOK_URL: str = ""
    API_BASE_URL: str = "https://api.telegram.org"
    BOT_NAME: str = "National ID converter"
    AUTHORIZED_USER_IDS: str = ""
    REQUIRED_GROUP_ID: int | str = 0
    REQUIRED_CHANNELS: str = ""
    CHANNEL_INVITE_LINKS: str = ""
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

    @property
    def required_channels_list(self) -> list[int | str]:
        """Returns list of channel/group IDs (int) or usernames (str) from REQUIRED_CHANNELS and REQUIRED_GROUP_ID."""
        channels: list[int | str] = []
        raw_sources = []
        if self.REQUIRED_CHANNELS:
            raw_sources.append(str(self.REQUIRED_CHANNELS))
        if self.REQUIRED_GROUP_ID:
            raw_sources.append(str(self.REQUIRED_GROUP_ID))

        for source in raw_sources:
            for ch in source.split(","):
                ch = ch.strip()
                if not ch or ch == "0":
                    continue
                try:
                    val = int(ch)
                    if val != 0 and val not in channels:
                        channels.append(val)
                except ValueError:
                    if ch not in channels:
                        channels.append(ch)
        return channels

    @property
    def channel_invite_links_map(self) -> dict[str, str]:
        """Returns mapping of channel ID/username string to explicit invite link if provided."""
        links: dict[str, str] = {}
        if not self.CHANNEL_INVITE_LINKS:
            return links
        parts = [p.strip() for p in self.CHANNEL_INVITE_LINKS.split(",") if p.strip()]
        for idx, part in enumerate(parts):
            if "=" in part:
                k, v = part.split("=", 1)
                links[k.strip()] = v.strip()
            elif ":" in part and not (part.startswith("http://") or part.startswith("https://")):
                k, v = part.split(":", 1)
                links[k.strip()] = v.strip()
            else:
                if idx < len(self.required_channels_list):
                    links[str(self.required_channels_list[idx])] = part
        return links
settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)