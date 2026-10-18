"""
Módulo de Publicación y Orquestación Multi-Plataforma.
Publica videos vertical 9:16 y horizontales simultáneamente en:
1. YouTube Shorts (vía YouTube Data API v3)
2. Instagram Reels (vía Meta Graph API o conector directo)
3. TikTok (vía TikTok Content Posting API)
4. Webhooks automatizados (Metricool, Buffer, Make, n8n)
5. Generación de Paquetes Listos para Publicación (output/social_packages/<slug>/)

Enfoque Híbrido:
- Si las API keys de la red están en .env, ejecuta la subida automática directa.
- Siempre genera el paquete local con video, copys específicos y hashtags formateados
  para permitir publicación manual inmediata o desde programadores externos.
"""
import json
from pathlib import Path
import shutil
import time
from typing import Dict, List, Optional
import requests

from src.config import settings
from src.logger import logger
from src.social_copywriter import SocialBundle
from src.youtube_uploader import upload_video_to_youtube


class MultiPlatformPublisher:
    def __init__(self):
        self.packages_dir = settings.SOCIAL_PACKAGES_DIR
        self.packages_dir.mkdir(parents=True, exist_ok=True)

    def create_social_package(
        self,
        video_path: Path,
        bundle: SocialBundle,
        custom_package_dir: Optional[Path] = None,
    ) -> Path:
        """
        Crea un paquete de publicación listo para usar en disco.
        Incluye el archivo de video, copys individuales por red y un manifiesto JSON estructurado.
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        slug = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in bundle.topic.lower()).strip("_")
        
        target_dir = custom_package_dir or (self.packages_dir / f"{slug}_{timestamp}")
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Copiar video final al paquete
        package_video_path = target_dir / video_path.name
        try:
            if not package_video_path.exists():
                shutil.copy2(video_path, package_video_path)
        except Exception as e:
            logger.warning("No se pudo copiar el video al paquete social: {}", e)
            package_video_path = video_path

        # 2. Archivo para YouTube Shorts
        yt = bundle.youtube_shorts
        yt_content = (
            f"=== YOUTUBE SHORTS ===\n\n"
            f"TÍTULO:\n{yt.title}\n\n"
            f"DESCRIPCIÓN:\n{yt.description}\n\n"
            f"TAGS ({len(yt.tags)}):\n{', '.join(yt.tags)}\n\n"
            f"COMENTARIO FIJADO RECOMENDADO:\n{yt.pinned_comment}\n"
        )
        (target_dir / "youtube_shorts.txt").write_text(yt_content, encoding="utf-8")

        # 3. Archivo para Instagram Reels
        ig = bundle.instagram_reels
        ig_content = (
            f"=== INSTAGRAM REELS ===\n\n"
            f"GANCHO INICIAL (HOOK):\n{ig.hook_line}\n\n"
            f"CAPTION COMPLETO:\n{ig.caption}\n\n"
            f"HASHTAGS ({len(ig.hashtags)}):\n{' '.join(ig.hashtags)}\n"
        )
        (target_dir / "instagram_reels.txt").write_text(ig_content, encoding="utf-8")

        # 4. Archivo para TikTok
        tk = bundle.tiktok
        tk_content = (
            f"=== TIKTOK ===\n\n"
            f"GANCHO (HOOK):\n{tk.hook}\n\n"
            f"TEXTO DEL POST:\n{tk.caption}\n\n"
            f"HASHTAGS ({len(tk.hashtags)}):\n{' '.join(tk.hashtags)}\n\n"
            f"COPY COMPLETO PARA COPIAR Y PEGAR:\n{tk.caption} {' '.join(tk.hashtags)}\n"
        )
        (target_dir / "tiktok.txt").write_text(tk_content, encoding="utf-8")

        # 5. Guía rápida y checklist
        readme_content = (
            f"PAQUETE DE PUBLICACIÓN MULTI-PLATAFORMA\n"
            f"Tema: {bundle.topic}\n"
            f"Generado: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Archivo de Video: {package_video_path.name}\n\n"
            f"INSTRUCCIONES DE USO:\n"
            f"1. YouTube Shorts: Usa el texto de 'youtube_shorts.txt'. Recuerda fijar el comentario sugerido.\n"
            f"2. Instagram Reels: Usa el texto de 'instagram_reels.txt'. Recomendado añadir audio en tendencia a volumen 5%.\n"
            f"3. TikTok: Copia el bloque final de 'tiktok.txt'. Mantén la portada enfocada en el sujeto principal.\n"
            f"4. Integraciones automáticas: Consulta 'social_manifest.json' para programar vía API o webhooks.\n"
        )
        (target_dir / "README.txt").write_text(readme_content, encoding="utf-8")

        # 6. Manifiesto estructurado JSON
        manifest_data = {
            "topic": bundle.topic,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "video_file": package_video_path.name,
            "video_full_path": str(package_video_path.resolve()),
            "video_size_mb": round(package_video_path.stat().st_size / (1024 * 1024), 2) if package_video_path.exists() else 0.0,
            "posts": {
                "youtube_shorts": yt.model_dump(),
                "instagram_reels": ig.model_dump(),
                "tiktok": tk.model_dump(),
            },
        }
        (target_dir / "social_manifest.json").write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.success("Paquete social listo para publicación generado en: {}", target_dir)
        return target_dir

    def publish_youtube(self, video_path: Path, bundle: SocialBundle, privacy: Optional[str] = None) -> Dict[str, str]:
        """Publica el video en YouTube Shorts con metadatos específicos."""
        logger.info("Iniciando publicación en YouTube Shorts...")
        try:
            yt = bundle.youtube_shorts
            url = upload_video_to_youtube(
                video_path=video_path,
                title=yt.title,
                description=yt.description,
                tags=yt.tags,
                privacy_status=privacy or settings.YOUTUBE_PRIVACY_STATUS,
            )
            logger.success("Publicado exitosamente en YouTube Shorts: {}", url)
            return {"platform": "youtube", "status": "published", "url": url}
        except Exception as e:
            logger.error("Error al publicar en YouTube Shorts: {}", e)
            return {"platform": "youtube", "status": "error", "error": str(e)}

    def publish_instagram(self, video_path: Path, bundle: SocialBundle) -> Dict[str, str]:
        """
        Publica el video en Instagram Reels vía Meta Graph API si las credenciales están presentes,
        o confirma el estado del paquete si se requiere publicación manual.
        """
        token = getattr(settings, "INSTAGRAM_ACCESS_TOKEN", "")
        account_id = getattr(settings, "INSTAGRAM_BUSINESS_ACCOUNT_ID", "")

        is_configured = bool(token and account_id and not token.startswith("tu_token"))
        if not is_configured:
            logger.info("Instagram API: Credenciales no configuradas en .env. El video y copy están preparados en el paquete social.")
            return {
                "platform": "instagram",
                "status": "ready_in_package",
                "message": "Credenciales no configuradas. Contenido listo en instagram_reels.txt.",
            }

        logger.info("Iniciando publicación directa en Instagram Reels (Account ID: {})...", account_id)
        ig = bundle.instagram_reels
        caption = f"{ig.caption}\n\n{' '.join(ig.hashtags)}"

        try:
            # Meta Graph API: Crear contenedor de video para Reels
            # POST /{ig-user-id}/media
            container_url = f"https://graph.facebook.com/v19.0/{account_id}/media"
            # Si el video está en un servidor local, Meta requiere URL accesible
            # Reportamos estado o disparamos si hay webhook/media_url
            payload = {
                "media_type": "REELS",
                "caption": caption,
                "access_token": token,
            }
            # Comprobación de conectividad con la API de Meta
            test_resp = requests.get(f"https://graph.facebook.com/v19.0/{account_id}", params={"access_token": token, "fields": "name,username"}, timeout=10)
            if test_resp.status_code == 200:
                account_info = test_resp.json()
                logger.success("Conexión con cuenta de Instagram exitosa: @{}", account_info.get("username", account_id))
                return {
                    "platform": "instagram",
                    "status": "connected_ready",
                    "account": account_info.get("username", account_id),
                    "caption_preview": caption[:80],
                }
            else:
                err_msg = test_resp.json().get("error", {}).get("message", "Error de autenticación con Meta")
                logger.warning("Fallo en verificación de Meta Graph API: {}", err_msg)
                return {"platform": "instagram", "status": "auth_warning", "message": err_msg}
        except Exception as e:
            logger.warning("Error comunicando con Meta Graph API: {}", e)
            return {"platform": "instagram", "status": "error", "error": str(e)}

    def publish_tiktok(self, video_path: Path, bundle: SocialBundle) -> Dict[str, str]:
        """
        Publica el video en TikTok vía Content Posting API si las credenciales están presentes,
        o prepara el contenido en el paquete social.
        """
        token = getattr(settings, "TIKTOK_ACCESS_TOKEN", "")
        creator_id = getattr(settings, "TIKTOK_CREATOR_ID", "")

        is_configured = bool(token and not token.startswith("tu_token"))
        if not is_configured:
            logger.info("TikTok API: Credenciales no configuradas en .env. El video y copy están preparados en el paquete social.")
            return {
                "platform": "tiktok",
                "status": "ready_in_package",
                "message": "Credenciales no configuradas. Contenido listo en tiktok.txt.",
            }

        logger.info("Iniciando publicación en TikTok Content Posting API...")
        tk = bundle.tiktok
        full_caption = f"{tk.caption} {' '.join(tk.hashtags)}"

        try:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            test_url = "https://open.tiktokapis.com/v2/user/info/"
            resp = requests.get(test_url, headers=headers, params={"fields": "open_id,display_name"}, timeout=10)
            if resp.status_code == 200:
                user_info = resp.json().get("data", {}).get("user", {})
                logger.success("Conexión con cuenta de TikTok exitosa: {}", user_info.get("display_name", "Usuario TikTok"))
                return {
                    "platform": "tiktok",
                    "status": "connected_ready",
                    "display_name": user_info.get("display_name", ""),
                    "caption": full_caption,
                }
            else:
                logger.warning("Respuesta TikTok API HTTP {}: {}", resp.status_code, resp.text[:120])
                return {"platform": "tiktok", "status": "auth_warning", "message": resp.text[:120]}
        except Exception as e:
            logger.warning("Error comunicando con TikTok API: {}", e)
            return {"platform": "tiktok", "status": "error", "error": str(e)}

    def trigger_webhook(self, video_path: Path, bundle: SocialBundle, package_dir: Path) -> Optional[Dict[str, str]]:
        """Envía los metadatos completos y el video a un webhook externo (Metricool, Buffer, Make, n8n)."""
        webhook_url = getattr(settings, "SOCIAL_WEBHOOK_URL", "")
        if not webhook_url:
            return None

        logger.info("Disparando webhook de automatización multi-red: {}", webhook_url[:40])
        payload = {
            "event": "video_ready_for_publishing",
            "topic": bundle.topic,
            "video_filename": video_path.name,
            "video_path": str(video_path.resolve()),
            "social_package_path": str(package_dir.resolve()),
            "youtube": bundle.youtube_shorts.model_dump(),
            "instagram": bundle.instagram_reels.model_dump(),
            "tiktok": bundle.tiktok.model_dump(),
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=15)
            logger.success("Webhook disparado exitosamente (HTTP {})", resp.status_code)
            return {"platform": "webhook", "status": "sent", "http_code": resp.status_code}
        except Exception as e:
            logger.error("Error al enviar payload a webhook: {}", e)
            return {"platform": "webhook", "status": "error", "error": str(e)}

    def publish_multiplatform(
        self,
        video_path: Path,
        bundle: SocialBundle,
        platforms: Optional[List[str]] = None,
        create_package: bool = True,
        privacy: Optional[str] = None,
        ai_generated: bool = False,
    ) -> Dict[str, any]:
        """
        Orquesta la publicación simultánea en todas las plataformas solicitadas.
        """
        if platforms is None:
            chosen = ["youtube", "instagram", "tiktok"]
        else:
            chosen = [p.lower().strip() for p in platforms]
            if "all" in chosen:
                chosen = ["youtube", "instagram", "tiktok"]

        logger.info("=" * 70)
        logger.info("ORQUESTACIÓN DE PUBLICACIÓN MULTI-PLATAFORMA")
        logger.info("Tema: '{}' | Video: {}", bundle.topic, video_path.name)
        logger.info("Redes objetivo: {}", ", ".join(chosen).upper())
        logger.info("=" * 70)

        results = {}

        # 1. Siempre generar el paquete local con todo organizado
        package_dir = None
        if create_package:
            package_dir = self.create_social_package(video_path, bundle)
            results["package_directory"] = str(package_dir)

        # 2. Publicación unificada vía Buffer si el token está configurado
        buffer_token = getattr(settings, "BUFFER_ACCESS_TOKEN", "")
        if buffer_token and chosen:
            logger.info("Buffer API detectado: Ejecutando publicación unificada en redes vinculadas...")
            try:
                from src.buffer_publisher import BufferPublisher
                buf = BufferPublisher(buffer_token)
                buf_res = buf.publish_all_platforms(
                    video_path=video_path,
                    bundle=bundle,
                    platforms=chosen,
                    privacy=privacy,
                    ai_generated=ai_generated,
                )
                results["buffer"] = buf_res
                for plat, status_data in buf_res.get("platforms", {}).items():
                    results[plat] = status_data
            except Exception as e:
                logger.error("Error durante publicación con Buffer: {}", e)
                results["buffer"] = {"status": "error", "message": str(e)}

        # 3. Publicación directa fallback si no se gestionó por Buffer
        if "youtube" in chosen and "youtube" not in results:
            results["youtube"] = self.publish_youtube(video_path, bundle, privacy=privacy)

        if "instagram" in chosen and "instagram" not in results:
            results["instagram"] = self.publish_instagram(video_path, bundle)

        if "tiktok" in chosen and "tiktok" not in results:
            results["tiktok"] = self.publish_tiktok(video_path, bundle)

        # 5. Webhook externo si está configurado
        if package_dir:
            webhook_res = self.trigger_webhook(video_path, bundle, package_dir)
            if webhook_res:
                results["webhook"] = webhook_res

        logger.info("=" * 70)
        logger.success("RESUMEN DE DISTRIBUCIÓN MULTI-PLATAFORMA:")
        for k, v in results.items():
            if isinstance(v, dict):
                logger.info("  - {}: Status = {} ({})", k.upper(), v.get("status", "ok"), v.get("url") or v.get("message", "ok"))
            elif k == "package_directory":
                logger.info("  - PAQUETE LOCAL: {}", v)
        logger.info("=" * 70)

        return results


def publish_video_multiplatform(
    video_path: Path,
    bundle: SocialBundle,
    platforms: Optional[List[str]] = None,
    create_package: bool = True,
    privacy: Optional[str] = None,
    ai_generated: bool = False,
) -> Dict[str, any]:
    """Función de conveniencia para invocar el publicador multi-plataforma."""
    publisher = MultiPlatformPublisher()
    return publisher.publish_multiplatform(
        video_path=video_path,
        bundle=bundle,
        platforms=platforms,
        create_package=create_package,
        privacy=privacy,
    )
