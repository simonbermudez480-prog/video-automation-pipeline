"""
Configuración centralizada del pipeline de automatización multimedia.
Carga variables de entorno desde .env y valida rutas y parámetros del sistema.
"""
import os
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(override=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

# Rutas estándar del proyecto
ASSETS_DIR = ROOT_DIR / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
AUDIO_DIR = ASSETS_DIR / "audio"
SUBTITLES_DIR = ASSETS_DIR / "subtitles"
TEMP_DIR = ASSETS_DIR / "temp"
OUTPUT_DIR = ROOT_DIR / "output"
SOCIAL_PACKAGES_DIR = OUTPUT_DIR / "social_packages"
LOGS_DIR = ROOT_DIR / "logs"

# Asegurar existencia de directorios operativos
for directory in [ASSETS_DIR, IMAGES_DIR, AUDIO_DIR, SUBTITLES_DIR, TEMP_DIR, OUTPUT_DIR, SOCIAL_PACKAGES_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


class Settings:
    # --- Rutas de Directorios ---
    ROOT_DIR = ROOT_DIR
    ASSETS_DIR = ASSETS_DIR
    IMAGES_DIR = IMAGES_DIR
    AUDIO_DIR = AUDIO_DIR
    SUBTITLES_DIR = SUBTITLES_DIR
    TEMP_DIR = TEMP_DIR
    OUTPUT_DIR = OUTPUT_DIR
    SOCIAL_PACKAGES_DIR = SOCIAL_PACKAGES_DIR
    LOGS_DIR = LOGS_DIR

    # --- LLM / Guion ---
    LLM_PROVIDER: Literal["gemini", "deepseek"] = os.getenv("LLM_PROVIDER", "gemini").lower() # type: ignore
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # --- TTS / Síntesis de Voz ---
    TTS_PROVIDER: Literal["elevenlabs", "edge-tts"] = os.getenv("TTS_PROVIDER", "edge-tts").lower() # type: ignore
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    EDGE_TTS_VOICE: str = os.getenv("EDGE_TTS_VOICE", "es-US-AlonsoNeural")
    ENABLE_PHONETIC_CORRECTION: bool = os.getenv("ENABLE_PHONETIC_CORRECTION", "true").lower() == "true"

    # --- Audio Alignment & Whisper ---
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "tiny")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
    WHISPER_BEAM_SIZE: int = int(os.getenv("WHISPER_BEAM_SIZE", "1"))

    # --- Generación de Imágenes y Recursos Visuales ---
    IMAGE_PROVIDER: Literal["pollinations", "imagen", "fal", "replicate", "stability", "pexels"] = os.getenv( # type: ignore
        "IMAGE_PROVIDER", "pollinations"
    ).lower()
    IMAGE_API_KEY: str = os.getenv("IMAGE_API_KEY", "")
    POLLINATIONS_API_KEY: str = os.getenv("POLLINATIONS_API_KEY", "")
    PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")
    IMAGE_ASPECT_RATIO: str = os.getenv("IMAGE_ASPECT_RATIO", "16:9")
    CONCURRENT_IMAGE_WORKERS: int = int(os.getenv("CONCURRENT_IMAGE_WORKERS", "4"))
    ENABLE_IMAGE_ENHANCEMENT: bool = os.getenv("ENABLE_IMAGE_ENHANCEMENT", "true").lower() in ("true", "1", "yes")

    # --- Duración y Estructura ---
    DEFAULT_DURATION_MINUTES: float = float(os.getenv("DEFAULT_DURATION_MINUTES", "3.5"))

    DEFAULT_ASPECT_RATIO: str = os.getenv("DEFAULT_ASPECT_RATIO", "9:16")

    # --- Montaje de Video (Optimización de Rendimiento) ---
    OUTPUT_RESOLUTION: str = os.getenv("OUTPUT_RESOLUTION", "1080x1920")
    OUTPUT_FPS: int = int(os.getenv("OUTPUT_FPS", "30"))
    CONCURRENT_CLIP_WORKERS: int = int(os.getenv("CONCURRENT_CLIP_WORKERS", "2"))
    FFMPEG_PRESET: str = os.getenv("FFMPEG_PRESET", "veryfast")
    FFMPEG_CRF: str = os.getenv("FFMPEG_CRF", "19")

    @staticmethod
    def get_dimensions(aspect_ratio: str = "16:9") -> tuple[int, int]:
        """Devuelve (ancho, alto) para la resolución de salida según el aspect ratio."""
        if aspect_ratio == "9:16":
            return 1080, 1920
        return 1920, 1080

    @staticmethod
    def get_zoom_buffer(aspect_ratio: str = "16:9") -> tuple[int, int]:
        """Devuelve (ancho, alto) para el búfer intermedio de zoom según el aspect ratio."""
        if aspect_ratio == "9:16":
            return 1440, 2560
        return 2560, 1440

    # --- YouTube API ---
    YOUTUBE_CLIENT_SECRET_FILE: str = os.getenv("YOUTUBE_CLIENT_SECRET_FILE", "client_secrets.json")
    YOUTUBE_TOKEN_FILE: str = os.getenv("YOUTUBE_TOKEN_FILE", "token.json")
    YOUTUBE_PRIVACY_STATUS: Literal["private", "unlisted", "public"] = os.getenv( # type: ignore
        "YOUTUBE_PRIVACY_STATUS", "private"
    ).lower()

    # --- Instagram Reels (Meta Graph API) ---
    INSTAGRAM_ACCESS_TOKEN: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    INSTAGRAM_BUSINESS_ACCOUNT_ID: str = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")

    # --- TikTok Content Posting API ---
    TIKTOK_ACCESS_TOKEN: str = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    TIKTOK_CREATOR_ID: str = os.getenv("TIKTOK_CREATOR_ID", "")

    # --- Webhooks Multi-Plataforma (Metricool, Buffer, Make, n8n) ---
    SOCIAL_WEBHOOK_URL: str = os.getenv("SOCIAL_WEBHOOK_URL", "")

    # --- Buffer GraphQL API (YouTube, Instagram, TikTok) ---
    BUFFER_ACCESS_TOKEN: str = os.getenv("BUFFER_ACCESS_TOKEN", "")
    BUFFER_SHARE_MODE: str = os.getenv("BUFFER_SHARE_MODE", "shareNow")

    # Archivos clave de salida
    SCRIPT_JSON_PATH = ASSETS_DIR / "script.json"
    ALIGNED_SCENES_PATH = ASSETS_DIR / "aligned_scenes.json"
    NARRATION_AUDIO_PATH = AUDIO_DIR / "narration.mp3"
    SUBTITLES_SRT_PATH = SUBTITLES_DIR / "subtitles.srt"
    FINAL_VIDEO_PATH = OUTPUT_DIR / "video_final.mp4"


settings = Settings()
