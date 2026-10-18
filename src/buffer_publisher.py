"""
Módulo de Integración Oficial y Publicación con Buffer GraphQL API.
Permite publicar simultáneamente videos verticales (Shorts, Reels, TikTok) en:
1. YouTube Shorts (con título, descripción, categoría y privacidad)
2. Instagram Reels (con gancho, caption completo, feed habilitado y hashtags)
3. TikTok (con copy viral y hashtags de tendencia)

El usuario solo provee su BUFFER_ACCESS_TOKEN y este módulo descubre automáticamente
los canales conectados y ejecuta las publicaciones con sus metadatos específicos.
"""
import os
from pathlib import Path
import time
from typing import Dict, List, Optional
import requests

from src.config import settings
from src.logger import logger
from src.social_copywriter import SocialBundle

BUFFER_GRAPHQL_ENDPOINT = "https://api.buffer.com"


import subprocess

def _get_upload_ready_video(video_path: Path) -> Path:
    """
    Si el video supera los 22 MB, genera una versión ligera en 720x1280 (vertical)
    manteniendo la relación de aspecto 9:16 y subtítulos legibles para asegurar
    una subida rápida y evitar timeouts de red.
    """
    size_mb = video_path.stat().st_size / (1024 * 1024)
    if size_mb <= 22:
        return video_path

    opt_path = video_path.parent / f"{video_path.stem}_web.mp4"
    if opt_path.exists() and _is_readable_video(opt_path):
        return opt_path
    opt_path.unlink(missing_ok=True)  # restos de un intento fallido (p. ej. disco lleno)

    logger.info("Optimizando peso del video ({:.2f} MB) para transferencia fluida hacia Buffer...", size_mb)
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", "scale=720:1280",
        "-c:v", "libx264", "-crf", "26", "-preset", "fast",
        "-c:a", "aac", "-b:a", "96k",
        str(opt_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and _is_readable_video(opt_path):
            new_mb = opt_path.stat().st_size / (1024 * 1024)
            logger.success("Video optimizado para entrega web: {:.2f} MB ({:.1f}% menor)", new_mb, (1 - new_mb / size_mb) * 100)
            return opt_path
        logger.warning("No se pudo comprimir video para subida: {}", res.stderr.decode(errors="ignore")[-300:])
    except Exception as e:
        logger.warning("No se pudo comprimir video para subida: {}", e)
    opt_path.unlink(missing_ok=True)

    return video_path


def _is_readable_video(path: Path) -> bool:
    """True si FFmpeg puede leer la duración del archivo (descarta MP4 truncados)."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    return probe.returncode == 0 and bool(probe.stdout.strip())


def _cdn_repo() -> str:
    return os.getenv("GITHUB_CDN_REPO", "") or "simonbermudez480-prog/video-assets"


def _upload_to_github_api(target_path: Path, token: str) -> Optional[str]:
    """
    Sube el video al repo de alojamiento con la API de contenidos de GitHub y un token limitado a ese repo
    (GITHUB_CDN_TOKEN). No necesita 'gh' ni una copia local del repo.
    """
    import base64
    repo = _cdn_repo()
    dest_filename = f"{target_path.stem}.mp4"
    api_url = f"https://api.github.com/repos/{repo}/contents/{dest_filename}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    try:
        payload = {
            "message": f"Upload {dest_filename} for Buffer delivery",
            "content": base64.b64encode(target_path.read_bytes()).decode("ascii"),
            "branch": "main",
        }
        existing = requests.get(api_url, headers=headers, params={"ref": "main"}, timeout=30)
        if existing.status_code == 200:
            payload["sha"] = existing.json().get("sha")
        resp = requests.put(api_url, headers=headers, json=payload, timeout=300)
        if resp.status_code not in (200, 201):
            logger.warning("GitHub API rechazó la subida (HTTP {}): {}", resp.status_code, resp.text[:200])
            return None
        direct_url = f"https://raw.githubusercontent.com/{repo}/main/{dest_filename}"
        for _ in range(12):  # el archivo tarda unos segundos en estar disponible en raw.githubusercontent.com
            if requests.head(direct_url, timeout=20).status_code == 200:
                break
            time.sleep(5)
        logger.success("Video hosteado en GitHub (API con token) para Buffer: {}", direct_url)
        return direct_url
    except Exception as e:
        logger.warning("Fallo al subir con la API de GitHub: {}", e)
        return None


def _upload_to_github_cdn(target_path: Path) -> Optional[str]:
    """
    Sube el video al repositorio público de alojamiento (por defecto 'video-assets') para obtener una URL directa
    de raw.githubusercontent.com, que Buffer acepta sin bloqueos. Con GITHUB_CDN_TOKEN usa la API de GitHub;
    si no, usa 'gh' CLI con la sesión iniciada y un clon local del repo.
    """
    token = os.getenv("GITHUB_CDN_TOKEN", "")
    if token:
        return _upload_to_github_api(target_path, token)
    try:
        import shutil
        gh_path = shutil.which("gh")
        if not gh_path:
            return None

        cdn_dir = settings.TEMP_DIR / "video_assets_cdn"
        if not cdn_dir.exists():
            res_clone = subprocess.run(
                ["gh", "repo", "clone", _cdn_repo(), str(cdn_dir)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if res_clone.returncode != 0 and not cdn_dir.exists():
                return None
        else:
            subprocess.run(["git", "-C", str(cdn_dir), "pull", "origin", "main"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        dest_filename = f"{target_path.stem}.mp4"
        dest_file = cdn_dir / dest_filename
        shutil.copy2(target_path, dest_file)

        subprocess.run(["git", "-C", str(cdn_dir), "add", dest_filename], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "-C", str(cdn_dir), "commit", "-m", f"Upload {dest_filename} for Buffer delivery"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        push_res = subprocess.run(["git", "-C", str(cdn_dir), "push", "origin", "main"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if push_res.returncode == 0:
            direct_url = f"https://raw.githubusercontent.com/{_cdn_repo()}/main/{dest_filename}"
            logger.success("Video hosteado en GitHub CDN para Buffer: {}", direct_url)
            return direct_url
    except Exception as e:
        logger.warning("Fallo al alojar en GitHub CDN (intentando alternativa): {}", e)

    return None


def upload_video_to_public_host(video_path: Path) -> str:
    """
    Sube el video a un servicio de almacenamiento temporal público con HTTPS directo,
    cumpliendo con el requerimiento de Buffer de acceder al archivo vía URL.
    """
    target_path = _get_upload_ready_video(video_path)
    logger.info("Alojando video ({:.2f} MB) para entrega a Buffer...", target_path.stat().st_size / (1024 * 1024))

    # 1. Intento primario: GitHub CDN oficial del usuario (100% compatible con Buffer, sin bloqueos)
    gh_url = _upload_to_github_cdn(target_path)
    if gh_url:
        return gh_url

    ua_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # 2. Intento secundario: Litterbox (catbox.moe con retención de 24 horas)
    try:
        logger.info("Enviando archivo a Litterbox (24h)...")
        with open(target_path, "rb") as f:
            data = {"reqtype": "fileupload", "time": "24h"}
            files = {"fileToUpload": (f"{target_path.stem}.mp4", f, "video/mp4")}
            resp = requests.post(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data=data,
                files=files,
                headers=ua_headers,
                timeout=300
            )
        if resp.status_code == 200 and resp.text.startswith("http"):
            direct_url = resp.text.strip()
            logger.success("Video hosteado temporalmente en Litterbox: {}", direct_url)
            return direct_url
    except Exception as e:
        logger.warning("Fallo al subir a Litterbox: {}. Intentando alternativa...", e)

    # 3. Intento terciario: Tempfile CDN
    try:
        logger.info("Enviando archivo a Tempfile CDN...")
        with open(target_path, "rb") as f:
            resp = requests.post(
                "https://tempfile.org/api/upload/local",
                files={"files": (f"{target_path.stem}.mp4", f, "video/mp4")},
                timeout=300
            )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") and data.get("files"):
                fid = data["files"][0]["id"]
                direct_url = f"https://tempfile.org/{fid}/download?name=video.mp4"
                logger.success("Video hosteado en Tempfile CDN: {}", direct_url)
                return direct_url
    except Exception as e:
        logger.warning("Fallo al subir a Tempfile CDN: {}", e)

    raise RuntimeError("No fue posible alojar el video en un servidor temporal público para Buffer.")


class BufferPublisher:
    """Gestiona la publicación automatizada en múltiples redes a través de Buffer GraphQL API."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or getattr(settings, "BUFFER_ACCESS_TOKEN", "")
        if not self.token:
            raise ValueError("No se ha configurado BUFFER_ACCESS_TOKEN en el entorno ni en Settings.")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self._cached_channels: Optional[Dict[str, Dict[str, str]]] = None

    def _post_with_retry(self, json_data: dict, timeout: int = 45, max_retries: int = 3) -> requests.Response:
        """Envía una petición POST a Buffer GraphQL con reintentos automáticos ante cortes SSL o conexión."""
        for attempt in range(max_retries):
            try:
                resp = requests.post(BUFFER_GRAPHQL_ENDPOINT, headers=self.headers, json=json_data, timeout=timeout)
                return resp
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt == max_retries - 1:
                    logger.error("Error persistente al conectar con Buffer API tras {} intentos: {}", max_retries, e)
                    raise
                logger.warning(
                    "Fallo transitorio de conexión con Buffer API (intento {}/{}): {}. Reintentando en 2.5s...",
                    attempt + 1, max_retries, e
                )
                time.sleep(2.5)

    def get_channels(self) -> Dict[str, Dict[str, str]]:
        """Descubre automáticamente los canales y cuentas vinculadas en la organización de Buffer."""
        if self._cached_channels is not None:
            return self._cached_channels

        q_org = """
        query {
          account {
            id
            email
            organizations {
              id
              name
            }
          }
        }
        """
        resp = self._post_with_retry(json_data={"query": q_org}, timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(f"Error al conectar con Buffer API (HTTP {resp.status_code}): {resp.text}")

        data = resp.json()
        orgs = data.get("data", {}).get("account", {}).get("organizations", [])
        if not orgs:
            raise RuntimeError(f"No se encontraron organizaciones para la cuenta de Buffer: {resp.text}")

        org_id = orgs[0]["id"]

        q_channels = f"""
        query {{
          channels(input: {{ organizationId: "{org_id}" }}) {{
            id
            name
            service
            serviceId
            displayName
          }}
        }}
        """
        resp_ch = self._post_with_retry(json_data={"query": q_channels}, timeout=20)
        channels_list = resp_ch.json().get("data", {}).get("channels", [])

        discovered = {}
        for ch in channels_list:
            service = ch.get("service", "").lower()
            discovered[service] = ch

        self._cached_channels = discovered
        logger.info("Canales detectados en Buffer: {}", ", ".join(discovered.keys()).upper())
        return discovered

    def _execute_create_post(self, variables: dict) -> Dict[str, any]:
        """Ejecuta la mutación createPost en Buffer GraphQL."""
        mutation = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            __typename
            ... on PostActionSuccess {
              post {
                id
                status
                text
              }
            }
            ... on InvalidInputError {
              message
            }
            ... on LimitReachedError {
              message
            }
            ... on UnauthorizedError {
              message
            }
            ... on UnexpectedError {
              message
            }
          }
        }
        """
        resp = self._post_with_retry(
            json_data={"query": mutation, "variables": variables},
            timeout=45
        )
        data = resp.json()
        result = data.get("data", {}).get("createPost", {})
        typename = result.get("__typename", "")

        if typename == "PostActionSuccess":
            post_data = result.get("post", {})
            return {
                "status": "success",
                "post_id": post_data.get("id"),
                "post_status": post_data.get("status"),
                "message": "Publicado exitosamente en Buffer",
            }
        else:
            err_msg = result.get("message") or f"Error GraphQL: {typename}"
            return {
                "status": "error",
                "message": err_msg,
            }

    def publish_youtube(
        self,
        channel_id: str,
        video_url: str,
        bundle: SocialBundle,
        share_mode: str = "shareNow",
        privacy: str = "public"
    ) -> Dict[str, any]:
        """Publica el video en YouTube Shorts con metadatos optimizados."""
        logger.info("Buffer: Enviando video a YouTube Shorts...")
        yt = bundle.youtube_shorts
        description_text = (
            f"{yt.description}\n\n"
            f"🔔 Suscríbete para más contenido diario.\n"
            f"{' '.join([f'#{t.replace(' ', '')}' for t in yt.tags[:6]])}"
        )

        valid_privacy = privacy if privacy in ["public", "private", "unlisted"] else "public"
        mode_val = "shareNow" if share_mode == "shareNow" else "addToQueue"
        save_draft = (share_mode == "draft")

        variables = {
            "input": {
                "channelId": channel_id,
                "text": description_text,
                "mode": mode_val,
                "schedulingType": "automatic",
                "saveToDraft": save_draft,
                "needsApproval": False,
                "assets": [{"video": {"url": video_url}}],
                "metadata": {
                    "youtube": {
                        "title": yt.title,
                        "privacy": valid_privacy,
                        "categoryId": "27"  # Educación
                    }
                }
            }
        }
        res = self._execute_create_post(variables)
        res["title"] = yt.title
        return res

    def publish_instagram(
        self,
        channel_id: str,
        video_url: str,
        bundle: SocialBundle,
        share_mode: str = "shareNow"
    ) -> Dict[str, any]:
        """Publica el video en Instagram Reels con caption completo y hashtags."""
        logger.info("Buffer: Enviando video a Instagram Reels...")
        ig = bundle.instagram_reels
        full_caption = f"{ig.caption}\n\n{' '.join(ig.hashtags)}"

        mode_val = "shareNow" if share_mode == "shareNow" else "addToQueue"
        save_draft = (share_mode == "draft")

        variables = {
            "input": {
                "channelId": channel_id,
                "text": full_caption,
                "mode": mode_val,
                "schedulingType": "automatic",
                "saveToDraft": save_draft,
                "needsApproval": False,
                "assets": [{"video": {"url": video_url}}],
                "metadata": {
                    "instagram": {
                        "shouldShareToFeed": True,
                        "type": "reel",
                        # Instagram es la única de las 3 redes que acepta primer comentario por la API de Buffer
                        **({"firstComment": bundle.youtube_shorts.pinned_comment} if bundle.youtube_shorts.pinned_comment else {}),
                    }
                }
            }
        }
        res = self._execute_create_post(variables)
        ig_meta = variables["input"]["metadata"]["instagram"]
        if res.get("status") != "success" and "firstComment" in ig_meta and "paid plan" in str(res.get("message", "")).lower():
            # El plan gratuito de Buffer no admite primer comentario: sin este reintento se pierde todo el post
            logger.warning("Buffer: el primer comentario requiere plan de pago; publicando Instagram sin él...")
            ig_meta.pop("firstComment")
            res = self._execute_create_post(variables)
        res["hook"] = ig.hook_line
        return res

    def publish_tiktok(
        self,
        channel_id: str,
        video_url: str,
        bundle: SocialBundle,
        share_mode: str = "shareNow"
    ) -> Dict[str, any]:
        """Publica el video en TikTok con copy corto y hashtags virales."""
        logger.info("Buffer: Enviando video a TikTok...")
        tk = bundle.tiktok
        full_caption = f"{tk.caption} {' '.join(tk.hashtags)}"

        mode_val = "shareNow" if share_mode == "shareNow" else "addToQueue"
        save_draft = (share_mode == "draft")

        variables = {
            "input": {
                "channelId": channel_id,
                "text": full_caption,
                "mode": mode_val,
                "schedulingType": "automatic",
                "saveToDraft": save_draft,
                "needsApproval": False,
                "assets": [{"video": {"url": video_url}}],
                "metadata": {
                    "tiktok": {
                        "title": tk.hook
                    }
                }
            }
        }
        res = self._execute_create_post(variables)
        res["hook"] = tk.hook
        return res

    def publish_all_platforms(
        self,
        video_path: Path,
        bundle: SocialBundle,
        platforms: Optional[List[str]] = None,
        share_mode: Optional[str] = None,
        privacy: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Orquesta la subida pública del video y publica automáticamente en todas las
        redes solicitadas conectadas en Buffer.
        """
        selected_mode = share_mode or getattr(settings, "BUFFER_SHARE_MODE", "shareNow")
        selected_privacy = privacy or getattr(settings, "YOUTUBE_PRIVACY_STATUS", "public")

        target_platforms = [p.lower() for p in (platforms or ["youtube", "instagram", "tiktok"])]
        if "all" in target_platforms:
            target_platforms = ["youtube", "instagram", "tiktok"]

        channels = self.get_channels()
        video_url = upload_video_to_public_host(video_path)

        results = {
            "video_public_url": video_url,
            "mode": selected_mode,
            "platforms": {}
        }

        # 1. YouTube Shorts
        if "youtube" in target_platforms:
            if "youtube" in channels:
                yt_id = channels["youtube"]["id"]
                res = self.publish_youtube(yt_id, video_url, bundle, share_mode=selected_mode, privacy=selected_privacy)
                results["platforms"]["youtube"] = res
                if res.get("status") == "success":
                    logger.success("Buffer -> YouTube Shorts publicado exitosamente! (Post ID: {})", res.get("post_id"))
                else:
                    logger.error("Buffer -> Error publicando en YouTube Shorts: {}", res.get("message"))
            else:
                logger.warning("No se encontró canal de YouTube conectado en tu cuenta de Buffer.")
                results["platforms"]["youtube"] = {"status": "not_connected", "message": "Canal no conectado en Buffer"}

        # 2. Instagram Reels
        if "instagram" in target_platforms:
            if "instagram" in channels:
                ig_id = channels["instagram"]["id"]
                res = self.publish_instagram(ig_id, video_url, bundle, share_mode=selected_mode)
                results["platforms"]["instagram"] = res
                if res.get("status") == "success":
                    logger.success("Buffer -> Instagram Reels publicado exitosamente! (Post ID: {})", res.get("post_id"))
                else:
                    logger.error("Buffer -> Error publicando en Instagram Reels: {}", res.get("message"))
            else:
                logger.warning("No se encontró cuenta de Instagram conectada en tu cuenta de Buffer.")
                results["platforms"]["instagram"] = {"status": "not_connected", "message": "Cuenta no conectada en Buffer"}

        # 3. TikTok
        if "tiktok" in target_platforms:
            if "tiktok" in channels:
                tk_id = channels["tiktok"]["id"]
                res = self.publish_tiktok(tk_id, video_url, bundle, share_mode=selected_mode)
                results["platforms"]["tiktok"] = res
                if res.get("status") == "success":
                    logger.success("Buffer -> TikTok publicado exitosamente! (Post ID: {})", res.get("post_id"))
                else:
                    logger.error("Buffer -> Error publicando en TikTok: {}", res.get("message"))
            else:
                logger.warning("No se encontró cuenta de TikTok conectada en tu cuenta de Buffer.")
                results["platforms"]["tiktok"] = {"status": "not_connected", "message": "Cuenta no conectada en Buffer"}

        return results
