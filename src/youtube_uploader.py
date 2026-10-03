"""
Módulo de Publicación Automatizada en YouTube.
Utiliza la API oficial de Google:
- google-api-python-client
- google-auth-oauthlib
- google-auth-httplib2

Soporta subida reanudable (resumable upload) y modos de privacidad:
- private (por defecto para revisión previa segura)
- unlisted
- public
"""
import os
import time
from pathlib import Path
from typing import List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from src.config import settings
from src.logger import logger

# Alcance requerido para subir videos a YouTube
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_authenticated_service(
    client_secrets_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
):
    """
    Gestiona la autenticación OAuth 2.0 y retorna el cliente oficial de YouTube.
    Si ya existe token.json, lo reutiliza y refresca automáticamente.
    """
    secrets_file = client_secrets_path or Path(settings.YOUTUBE_CLIENT_SECRET_FILE)
    token_file = token_path or Path(settings.YOUTUBE_TOKEN_FILE)

    credentials = None

    if token_file.exists():
        logger.info("Cargando credenciales existentes desde: {}", token_file)
        try:
            credentials = Credentials.from_authorized_user_file(str(token_file), YOUTUBE_SCOPES)
        except Exception as e:
            logger.warning("No se pudo cargar token existente: {}. Reautenticando...", e)
            credentials = None

    # Refrescar si está expirado
    if credentials and credentials.expired and credentials.refresh_token:
        logger.info("Refrescando token de acceso expirado...")
        try:
            credentials.refresh(Request())
            with open(token_file, "w", encoding="utf-8") as f:
                f.write(credentials.to_json())
        except Exception as e:
            logger.warning("Error al refrescar credenciales: {}. Se solicitará nuevo inicio de sesión.", e)
            credentials = None

    # Si no hay credenciales válidas, iniciar flujo interactivo
    if not credentials or not credentials.valid:
        if not secrets_file.exists():
            raise FileNotFoundError(
                f"No se encontró el archivo de credenciales de YouTube: '{secrets_file}'.\n"
                "Para habilitar la subida automática a YouTube:\n"
                "1. Entra a Google Cloud Console (https://console.cloud.google.com/)\n"
                "2. Habilita 'YouTube Data API v3'.\n"
                "3. Crea credenciales de tipo 'OAuth 2.0 Client IDs' (Tipo: Aplicación de escritorio / Desktop App).\n"
                f"4. Descarga el JSON y guárdalo en la raíz como '{secrets_file.name}'."
            )

        logger.info("Iniciando flujo de autorización en el navegador...")
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), YOUTUBE_SCOPES)
        credentials = flow.run_local_server(port=0)

        # Guardar credenciales para próximas ejecuciones
        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(credentials.to_json())
        logger.success("Credenciales OAuth guardadas exitosamente en: {}", token_file)

    return build("youtube", "v3", credentials=credentials)


def upload_video_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: List[str],
    privacy_status: Optional[str] = None,
    category_id: str = "27",  # 27 = Educación en YouTube
) -> str:
    """
    Sube un video a YouTube con carga reanudable y reporte de progreso.
    Devuelve la URL directa del video (ej: https://youtu.be/xxxx).
    """
    if not video_path.exists():
        raise FileNotFoundError(f"El archivo de video a subir no existe: {video_path}")

    selected_privacy = (privacy_status or settings.YOUTUBE_PRIVACY_STATUS).lower()
    if selected_privacy not in ["private", "unlisted", "public"]:
        logger.warning("Estado de privacidad '{}' inválido. Usando 'private'.", selected_privacy)
        selected_privacy = "private"

    logger.info("Preparando subida de video a YouTube...")
    logger.info("Título: {}", title)
    logger.info("Privacidad: {}", selected_privacy)

    youtube = get_authenticated_service()

    # Construir metadatos del video
    body = {
        "snippet": {
            "title": title[:100],  # Límite estricto de YouTube: 100 caracteres
            "description": description[:5000],  # Límite de descripción
            "tags": tags[:50],  # Máximo de tags recomendados
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": selected_privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    # Carga de medios en trozos de 4MB para evitar desconexiones
    media = MediaFileUpload(
        str(video_path),
        chunksize=4 * 1024 * 1024,
        resumable=True,
        mimetype="video/mp4",
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    logger.info("Iniciando transferencia de bytes hacia YouTube...")
    response = None
    retry_count = 0
    max_retries = 5

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info("Progreso de subida a YouTube: {}%", progress)
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                retry_count += 1
                if retry_count > max_retries:
                    raise
                wait_time = 2 ** retry_count
                logger.warning("Error de servidor {}. Reintentando en {}s...", e.resp.status, wait_time)
                time.sleep(wait_time)
            else:
                logger.error("Error HTTP irrecuperable al subir video: {}", e)
                raise
        except Exception as e:
            retry_count += 1
            if retry_count > max_retries:
                raise
            wait_time = 2 ** retry_count
            logger.warning("Error de conexión {}. Reintentando en {}s...", e, wait_time)
            time.sleep(wait_time)

    video_id = response.get("id")
    video_url = f"https://youtu.be/{video_id}"
    logger.success("¡Video publicado exitosamente en YouTube!")
    logger.success("ID del video: {}", video_id)
    logger.success("Enlace: {}", video_url)
    return video_url
