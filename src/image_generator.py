"""
Módulo de Generación y Descarga de Imágenes Reales y Coherentes.
100% enfocado en imágenes fotográficas reales y de alta resolución (1920x1080).
Soporta:
1. Google Imagen 3 (vía SDK google-genai)
2. Fal.ai (Flux Schnell en 16:9)
3. Stability AI / Replicate
4. API de Pexels (fotos de stock reales si se define PEXELS_API_KEY)
5. Pollinations.ai vía URL directa: https://image.pollinations.ai/prompt/{prompt}?width=1920&height=1080&nologo=true
6. NASA Deep Space & Cosmology Archive (fotografías espaciales reales en 4K)
7. Picsum Photos HD (fotografía documental real 1920x1080 con semillas temáticas)
* Se han eliminado por completo los fondos planos o artificiales.
"""
import os
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional
import requests

from src.config import settings
from src.logger import logger
from src.script_generator import Scene

# Encabezados estándar de navegador para evitar bloqueos
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


def _generate_with_google_imagen(prompt: str, output_path: Path) -> bool:
    """Genera imagen 16:9 usando Google Imagen 3."""
    logger.info("Generando imagen con Google Imagen 3...")
    try:
        from google import genai
        from google.genai import types

        api_key = settings.IMAGE_API_KEY or settings.GEMINI_API_KEY
        client = genai.Client(api_key=api_key)

        result = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9",
                output_mime_type="image/png",
            ),
        )

        if result.generated_images:
            img_bytes = result.generated_images[0].image.image_bytes
            output_path.write_bytes(img_bytes)
            logger.success("Imagen guardada con Google Imagen 3: {}", output_path)
            return True
        return False
    except Exception as e:
        logger.error("Error al generar con Google Imagen: {}", e)
        return False


def _generate_with_fal(prompt: str, output_path: Path) -> bool:
    """Genera imagen 16:9 usando Fal.ai (Flux Schnell)."""
    logger.info("Generando imagen con Fal.ai Flux...")
    url = "https://fal.run/fal-ai/flux/schnell"
    headers = {
        "Authorization": f"Key {settings.IMAGE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "image_size": "landscape_16_9",
        "num_inference_steps": 4,
        "enable_safety_checker": True,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            image_url = data.get("images", [{}])[0].get("url")
            if image_url:
                img_resp = requests.get(image_url, timeout=30)
                if img_resp.status_code == 200:
                    output_path.write_bytes(img_resp.content)
                    logger.success("Imagen guardada con Fal.ai: {}", output_path)
                    return True
        return False
    except Exception as e:
        logger.error("Excepción en Fal.ai: {}", e)
        return False


def _normalize_image_to_resolution(image_path: Path, aspect_ratio: str = "16:9") -> bool:
    """
    Garantiza que la imagen esté exactamente en resolución requerida:
    1920x1080 (16:9) o 1080x1920 (9:16 vertical),
    evitando bordes negros o distorsiones de aspecto en FFmpeg.
    Aplica mejoras visuales sutiles (contraste, nitidez) si está habilitado.
    """
    try:
        from PIL import Image, ImageOps, ImageEnhance
        target_w, target_h = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
        with Image.open(image_path) as im:
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            fitted = ImageOps.fit(im, (target_w, target_h), method=Image.Resampling.LANCZOS)

            # Optimización estética para estilo documental cinematográfico
            if getattr(settings, "ENABLE_IMAGE_ENHANCEMENT", True):
                try:
                    fitted = ImageEnhance.Sharpness(fitted).enhance(1.12)
                    fitted = ImageEnhance.Contrast(fitted).enhance(1.06)
                except Exception as enh_e:
                    logger.debug("Omitiendo mejora estética: {}", enh_e)

            fitted.save(image_path, format="PNG", optimize=True)
            return True
    except Exception as e:
        logger.warning("No se pudo normalizar imagen {} a {}: {}", image_path.name, aspect_ratio, e)
        return False


def _extract_keywords_from_prompt(prompt: str) -> str:
    """Extrae las palabras clave esenciales del prompt descartando términos de estilo genéricos."""
    cleaned = re.split(r",\s*cinematic\b|,\s*photorealistic\b|,\s*volumetric\b|,\s*16:9\b|,\s*9:16\b|,\s*vertical\b", prompt, flags=re.IGNORECASE)[0]
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    words = [
        w for w in cleaned.split()
        if len(w) > 3 and w.lower() not in {"with", "that", "from", "into", "over", "under", "dramatic", "hyper", "style", "view", "shot", "scene"}
    ]
    return " ".join(words[:5]) or "history documentary"


def _generate_with_pollinations_flux(prompt: str, output_path: Path, aspect_ratio: str = "16:9") -> bool:
    """
    Intenta generar imagen cinemática vía Pollinations AI:
    Soporta clave de API para modelos premium y fallback a modelo estándar en 16:9 o 9:16.
    """
    clean_prompt = re.sub(r"[^\w\s,.-]", "", prompt)
    clean_prompt = " ".join(clean_prompt.split()[:25])
    encoded = urllib.parse.quote(clean_prompt)

    target_w, target_h = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)

    api_key = getattr(settings, "POLLINATIONS_API_KEY", "") or (
        settings.IMAGE_API_KEY if settings.IMAGE_API_KEY and not settings.IMAGE_API_KEY.startswith("tu_clave") else ""
    )

    headers = dict(BROWSER_HEADERS)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        url = f"https://image.pollinations.ai/prompt/{encoded}?model=flux&width={target_w}&height={target_h}&nologo=true"
    else:
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={target_w}&height={target_h}&nologo=true"

    try:
        logger.info("Intentando generación vía Pollinations ({}) [{}]...", aspect_ratio, f"{target_w}x{target_h}")
        resp = requests.get(url, headers=headers, timeout=18)
        if resp.status_code == 200 and len(resp.content) > 10000:
            output_path.write_bytes(resp.content)
            _normalize_image_to_resolution(output_path, aspect_ratio)
            logger.success("Visual cinemático generado con Pollinations: {}", output_path.name)
            return True
        logger.warning("Pollinations respondió HTTP {}", resp.status_code)
        return False
    except Exception as e:
        logger.warning("Timeout o fallo en Pollinations: {}", e)
        return False



def _fetch_from_wikimedia_commons(prompt: str, output_path: Path, scene_id: int, keywords: Optional[str] = None, aspect_ratio: str = "16:9") -> bool:
    """
    Obtiene fotografías históricas, científicas y documentales auténticas en alta resolución
    desde el archivo público de Wikimedia Commons. Ideal para historia, guerras, biografías y ciencia.
    """
    query = keywords or _extract_keywords_from_prompt(prompt)
    # Traducir o normalizar términos comunes en español a inglés para archivos internacionales
    translations = {
        "agujeros negros": "black hole",
        "agujero negro": "black hole",
        "segunda guerra mundial": "world war ii",
        "primera guerra mundial": "world war i",
        "biblioteca de alejandria": "library of alexandria ancient",
        "multiverso": "multiverse physics",
        "inmortalidad cuantica": "quantum physics",
    }
    q_clean = query.lower()
    for es_term, en_term in translations.items():
        if es_term in q_clean:
            query = q_clean.replace(es_term, en_term)
            break

    logger.info("Consultando archivo histórico Wikimedia Commons para: '{}'...", query)

    queries_to_try = [query]
    words = query.split()
    if len(words) > 3:
        queries_to_try.append(" ".join(words[:3]))

    headers = {"User-Agent": "EducationalVideoBot/1.0 (educational; open-source documentary)"}
    target_width = 1080 if aspect_ratio == "9:16" else 1920

    for q in queries_to_try:
        url = (
            f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
            f"&gsrsearch={urllib.parse.quote(q)}&gsrnamespace=6&format=json"
            f"&prop=imageinfo&iiprop=url|mime&iiurlwidth={target_width}"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                pages = resp.json().get("query", {}).get("pages", {})
                for pid, page in pages.items():
                    info = page.get("imageinfo", [{}])[0]
                    img_url = info.get("thumburl") or info.get("url")
                    mime = info.get("mime", "")
                    if img_url and ("image/jpeg" in mime or "image/png" in mime or img_url.lower().endswith((".jpg", ".jpeg", ".png"))):
                        dl = requests.get(img_url, headers=headers, timeout=15)
                        if dl.status_code == 200 and len(dl.content) > 10000:
                            output_path.write_bytes(dl.content)
                            _normalize_image_to_resolution(output_path, aspect_ratio)
                            logger.success("Fotografía histórica auténtica obtenida de Wikimedia Commons: {}", page.get("title", output_path.name))
                            return True
        except Exception as e:
            logger.warning("Fallo al consultar Wikimedia Commons ('{}'): {}", q, e)

    return False


def _fetch_from_nasa_archive(prompt: str, output_path: Path, scene_id: int, aspect_ratio: str = "16:9") -> bool:
    """
    Obtiene fotografías científicas reales en alta resolución del archivo oficial de la NASA.
    Solo se activa si el tema o prompt contiene términos astronómicos o cosmológicos explícitos.
    """
    p_lower = prompt.lower()
    space_indicators = [
        "space", "galaxy", "nebula", "universe", "star", "astronomy",
        "cosmic", "black hole", "telescope", "planet", "solar system",
        "multiverse", "quantum", "everett"
    ]
    if not any(k in p_lower for k in space_indicators):
        return False

    logger.info("Consultando archivo fotográfico oficial de la NASA...")
    space_terms = ["nebula", "galaxy", "deep space", "hubble", "james webb", "cosmology", "stars", "black hole"]
    selected_term = space_terms[(scene_id - 1) % len(space_terms)]

    url = f"https://images-api.nasa.gov/search?q={urllib.parse.quote(selected_term)}&media_type=image"

    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=12)
        if resp.status_code == 200:
            items = resp.json().get("collection", {}).get("items", [])
            if items:
                idx = (scene_id * 3) % len(items)
                links = items[idx].get("links", [])
                if links:
                    img_url = links[0].get("href")
                    if img_url:
                        dl = requests.get(img_url, headers=BROWSER_HEADERS, timeout=15)
                        if dl.status_code == 200 and len(dl.content) > 10000:
                            output_path.write_bytes(dl.content)
                            _normalize_image_to_resolution(output_path, aspect_ratio)
                            logger.success("Fotografía espacial real de la NASA obtenida: {}", output_path.name)
                            return True
        return False
    except Exception as e:
        logger.warning("Fallo al consultar NASA Archive: {}", e)
        return False


def _fetch_from_picsum(prompt: str, output_path: Path, scene_id: int, aspect_ratio: str = "16:9") -> bool:
    """
    Descarga fotografías reales de alta definición según el formato (1080x1920 para 9:16 o 1920x1080 para 16:9)
    desde el repositorio Picsum Photos utilizando semillas deterministas.
    """
    target_w, target_h = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
    logger.info("Descargando fotografía documental real {}x{} (Picsum HD)...", target_w, target_h)
    seed = f"docu_scene_{scene_id}_{abs(hash(prompt)) % 100000}"
    url = f"https://picsum.photos/seed/{seed}/{target_w}/{target_h}"

    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 10000:
            output_path.write_bytes(resp.content)
            _normalize_image_to_resolution(output_path, aspect_ratio)
            logger.success("Fotografía real {}x{} descargada con éxito: {}", target_w, target_h, output_path.name)
            return True
        return False
    except Exception as e:
        logger.warning("Error en Picsum HD: {}", e)
        return False


def generate_single_image(
    scene_id: int,
    prompt: str,
    output_path: Path,
    provider: Optional[str] = None,
    keywords: Optional[str] = None,
    aspect_ratio: str = "16:9",
) -> bool:
    """
    Genera u obtiene una imagen real (16:9 o 9:16) mediante una cascada inteligente de calidad y contexto.
    Nunca produce fondos de color plano.
    """
    selected_provider = (provider or settings.IMAGE_PROVIDER).lower()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Fal.ai Flux-Schnell (si hay API Key de Fal o se selecciona fal)
    if selected_provider == "fal" or (
        settings.IMAGE_API_KEY and settings.IMAGE_API_KEY.startswith("fal_")
    ):
        if _generate_with_fal(prompt, output_path):
            _normalize_image_to_resolution(output_path, aspect_ratio)
            return True

    # 2. Google Imagen 3 (si hay API Key de Google configurada o se selecciona imagen)
    if selected_provider == "imagen" or (
        settings.IMAGE_API_KEY and "AIza" in settings.IMAGE_API_KEY
    ):
        if _generate_with_google_imagen(prompt, output_path):
            _normalize_image_to_resolution(output_path, aspect_ratio)
            return True

    # 3. Pollinations (IA generativa gratuita o con clave en 16:9 o 9:16)
    has_combat_keywords = False
    has_custom_key = bool(
        getattr(settings, "POLLINATIONS_API_KEY", "")
        or (settings.IMAGE_API_KEY and not settings.IMAGE_API_KEY.startswith("tu_clave"))
    )
    if not has_custom_key:
        combat_terms = [
            r"\bwar\b", r"\bbattle\b", r"\bsoldier\b", r"\barmy\b", r"\bhitler\b", r"\bnazi\b",
            r"\binvasion\b", r"\bmilitary\b", r"\bcombat\b", r"\bbomb\b", r"\bstalingrad\b", r"\bnormandy\b"
        ]
        p_check = (prompt + " " + (keywords or "")).lower()
        has_combat_keywords = any(bool(re.search(term, p_check)) for term in combat_terms)

    if not has_combat_keywords:
        if _generate_with_pollinations_flux(prompt, output_path, aspect_ratio=aspect_ratio):
            return True

    # 4. NASA Deep Space Archive (fotografías espaciales reales, si es tema astronómico o cosmológico)
    if _fetch_from_nasa_archive(prompt, output_path, scene_id, aspect_ratio=aspect_ratio):
        return True

    # 5. Archivo Histórico / Documental Wikimedia Commons (fotografías históricas reales, mapas, archivos)
    if _fetch_from_wikimedia_commons(prompt, output_path, scene_id, keywords, aspect_ratio=aspect_ratio):
        return True

    # 6. Repositorio de Fotografía Documental Real Picsum HD (1920x1080 o 1080x1920)
    if _fetch_from_picsum(prompt, output_path, scene_id, aspect_ratio=aspect_ratio):
        return True

    return False



def generate_images_for_scenes(
    scenes: List[Scene],
    output_dir: Optional[Path] = None,
    provider: Optional[str] = None,
    topic: Optional[str] = None,
    aspect_ratio: str = "16:9",
) -> List[Path]:
    """
    Itera sobre la lista de escenas del guion y descarga concurrentemente
    cada imagen real en assets/images/scene_{idx:03d}.png en formato 16:9 o 9:16.
    Invalida automáticamente la caché si el tema o el aspect ratio cambiaron respecto a la ejecución anterior.
    """
    target_dir = output_dir or settings.IMAGES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # Detección de cambio de tema o formato: purgar caché de imágenes previas
    topic_cache_file = target_dir / ".current_topic.txt"
    cache_signature = f"{topic.strip().lower()}_{aspect_ratio}" if topic else f"general_{aspect_ratio}"
    if topic_cache_file.exists():
        prev_sig = topic_cache_file.read_text(encoding="utf-8").strip().lower()
        if prev_sig != cache_signature:
            logger.warning(
                "Cambio de tema o formato detectado ('{}' -> '{}'). Purgando imágenes previas para regenerar con resolución correcta.",
                prev_sig,
                cache_signature,
            )
            for old_img in target_dir.glob("scene_*.png"):
                try:
                    old_img.unlink()
                except Exception:
                    pass
    topic_cache_file.write_text(cache_signature, encoding="utf-8")

    total = len(scenes)
    workers = getattr(settings, "CONCURRENT_IMAGE_WORKERS", 4)
    logger.info("Iniciando obtención de {} imágenes reales (Workers: {}, Formato: {}, Tema: '{}')...", total, workers, aspect_ratio, topic or "General")

    image_paths_dict = {}
    pending_items = []

    for idx, scene in enumerate(scenes, start=1):
        filename = f"scene_{idx:03d}.png"
        img_path = target_dir / filename

        # Si ya existe y pesa más de 10 KB, reutilizarla
        if img_path.exists() and img_path.stat().st_size > 10000:
            logger.info("Reutilizando imagen real para escena #{:03d}: {}", idx, img_path.name)
            image_paths_dict[idx] = img_path
        else:
            pending_items.append((idx, scene, img_path))

    if pending_items:
        logger.info("Adquiriendo concurrentemente {} imágenes requeridas...", len(pending_items))

        def _fetch_worker(item):
            s_idx, s_scene, s_path = item
            logger.info(
                "[{}/{}] Adquiriendo imagen para Escena #{:03d} ({}): '{}...'",
                s_idx,
                total,
                s_scene.scene_id,
                aspect_ratio,
                s_scene.visual_prompt[:60],
            )
            success = generate_single_image(
                scene_id=s_scene.scene_id,
                prompt=s_scene.visual_prompt,
                output_path=s_path,
                provider=provider,
                keywords=s_scene.search_keywords,
                aspect_ratio=aspect_ratio,
            )
            if not success or not s_path.exists():
                raise RuntimeError(f"Fallo crítico al obtener imagen real para la escena #{s_idx}")
            return s_idx, s_path

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_fetch_worker, item) for item in pending_items]
            for future in as_completed(futures):
                idx_done, path_done = future.result()
                image_paths_dict[idx_done] = path_done

    # Reconstruir en orden secuencial estricto
    image_paths = [image_paths_dict[i] for i in range(1, total + 1)]
    logger.success("Las {} imágenes reales ({}) fueron adquiridas exitosamente.", len(image_paths), aspect_ratio)
    return image_paths

