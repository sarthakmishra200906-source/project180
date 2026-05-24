"""Configuration values for Project 180."""

from pathlib import Path
from os import getenv

try:
	from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency fallback
	load_dotenv = None


_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
if load_dotenv is not None:
	load_dotenv(_ENV_PATH)


GEMINI_API_KEY = getenv("GEMINI_API_KEY", "")
OLLAMA_MODEL = getenv("OLLAMA_MODEL", "llama3.2:1b")
SERVER_HOST = getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(getenv("SERVER_PORT", "8787"))
ESP32_BASE_URL = getenv("ESP32_BASE_URL", "http://192.168.4.1")

# Default persona/system instruction for the AI. Can be overridden by clients
# by sending a `persona` field in the JSON body to `/ai` or by setting
# `project180_persona` in localStorage on clients.
DEFAULT_PERSONA = (
	"You are Cheeku, a friendly, concise companion robot created by the Long "
	"Brothers. When asked to describe yourself, speak in first person, be warm, "
	"and include factual details provided here. Always answer in-character."
)
