import configparser
import os


# Load configuration from environment variables or config.ini
def load_config():
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.dirname(__file__), "../config/config.ini"))

    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", config.get("settings", "TELEGRAM_TOKEN"))
    GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", config.get("settings", "GITLAB_TOKEN"))
    GITLAB_URL = os.getenv("GITLAB_URL", config.get("settings", "GITLAB_URL"))
    MODEL = os.getenv("MODEL", config.get("settings", "MODEL", fallback="gpt-4"))
    MR_ID = os.getenv("MR_ID", config.get("settings", "MR_ID"))
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", config.get("settings", "OPENAI_API_KEY"))
    PROJECT_ID = os.getenv("PROJECT_ID", config.get("settings", "PROJECT_ID"))
    TOKEN_LIMIT = int(os.getenv("TOKEN_LIMIT", config.get("settings", "TOKEN_LIMIT", fallback="30000")))
    PROMPT_FILE = os.getenv("PROMPT_FILE", config.get("settings", "PROMPT_FILE"))

    # Process SKIP_EXTENSIONS, removing spaces and ignoring comments
    raw_extensions = os.getenv("SKIP_EXTENSIONS", config.get("settings", "SKIP_EXTENSIONS", fallback=""))
    SKIP_EXTENSIONS = [ext.split("#")[0].strip() for ext in raw_extensions.split(",") if ext.strip()]

    return GITLAB_TOKEN, GITLAB_URL, MODEL, MR_ID, OPENAI_API_KEY, PROJECT_ID, SKIP_EXTENSIONS, TOKEN_LIMIT, TELEGRAM_TOKEN, PROMPT_FILE

# Load once when imported
GITLAB_TOKEN, GITLAB_URL, MODEL, MR_ID, OPENAI_API_KEY, PROJECT_ID, SKIP_EXTENSIONS, TOKEN_LIMIT, TELEGRAM_TOKEN, PROMPT_FILE = load_config()

# Make constants accessible when importing from config_loader
__all__ = [
    "GITLAB_TOKEN", "GITLAB_URL", "MODEL", "MR_ID", "OPENAI_API_KEY", 
    "PROJECT_ID", "SKIP_EXTENSIONS", "TOKEN_LIMIT", "TELEGRAM_TOKEN", "PROMPT_FILE"
]
