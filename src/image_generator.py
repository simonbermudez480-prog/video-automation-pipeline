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
7. Wikimedia Commons (archivo histórico real)
Los candidatos se auditan por lote con Gemini Vision (src/quality_gate.py); ninguno se aprueba sin auditoría visual.
"""
import hashlib
import os
import re
import shutil
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from typing import Callable, List, Optional
import requests

from src.config import settings
from src.logger import logger
from src.quality_gate import audit_images_batch, find_duplicates, load_manifest, save_manifest
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


def _generate_with_google_imagen(prompt: str, output_path: Path, aspect_ratio: str = "16:9") -> bool:
    """Genera imagen en resolución nativa 16:9 o 9:16 usando Google Imagen 3."""
    valid_ratio = "9:16" if aspect_ratio == "9:16" else "16:9"
    logger.info("Generando imagen con Google Imagen 3 (Formato: {})...", valid_ratio)
    try:
        from google import genai
        from google.genai import types

        api_key = settings.IMAGE_API_KEY or settings.GEMINI_API_KEY
        client = genai.Client(api_key=api_key, http_options={"timeout": 25000})

        result = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=valid_ratio,
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


def _generate_with_fal(prompt: str, output_path: Path, aspect_ratio: str = "16:9") -> bool:
    """Genera imagen usando Fal.ai (Flux Schnell) en 16:9 o 9:16."""
    fal_size = "portrait_16_9" if aspect_ratio == "9:16" else "landscape_16_9"
    logger.info("Generando imagen con Fal.ai Flux (Formato: {})...", fal_size)
    url = "https://fal.run/fal-ai/flux/schnell"
    headers = {
        "Authorization": f"Key {settings.IMAGE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "image_size": fal_size,
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


def _build_cohesive_prompt(
    base_prompt: str,
    visual_contract: Optional[object] = None,
    shot_type: Optional[str] = None,
    aspect_ratio: str = "9:16",
) -> str:
    """
    Combina el prompt de la escena con la biblia visual global (VisualContract)
    garantizando coherencia de paleta, iluminación y estilo cinematográfico.
    Sanitiza activamente contra el 'prompt poisoning' eliminando palabras ambiguas como 'portrait'.
    """
    if not visual_contract:
        return base_prompt

    style_anchor = getattr(visual_contract, "art_style", "")
    palette = getattr(visual_contract, "color_palette", "")
    lighting = getattr(visual_contract, "lighting_atmosphere", "")
    era = getattr(visual_contract, "era_setting", "")

    components = [base_prompt.rstrip(". ")]
    if era and era.lower() not in base_prompt.lower():
        components.append(f"Era: {era}")
    if shot_type and shot_type.replace("_", " ") not in base_prompt.lower():
        components.append(f"Cinematography: {shot_type.replace('_', ' ')}")
    if style_anchor and style_anchor.lower() not in base_prompt.lower():
        components.append(f"Aesthetic: {style_anchor}")
    if palette and palette.lower() not in base_prompt.lower():
        components.append(f"Color palette: {palette}")
    if lighting and lighting.lower() not in base_prompt.lower():
        components.append(f"Lighting: {lighting}")

    # Directivas estrictas anti-hallucination / anti-poisoning según el tipo de plano
    if shot_type in ("environmental_wide", "macro_detail"):
        components.append("uninhabited scene, empty surroundings, no humans, no people, inanimate subject, clean archival focus")
    elif shot_type == "silhouette_backlight":
        components.append("shadow silhouette from behind, back view, no frontal face visible")
    elif shot_type == "over_the_shoulder":
        components.append("over the shoulder camera angle, looking away from camera, anonymous back perspective")

    ratio_tag = (
        "vertical 9:16 framing, mobile safe zone, full height composition"
        if aspect_ratio == "9:16"
        else "cinematic 16:9 widescreen"
    )
    components.append(f"{ratio_tag}, authentic documentary film still, 35mm fine grain, no text, no captions, no watermark")

    # Limpieza final de términos tóxicos de encuadre (singular y plural)
    raw_prompt = ". ".join(components)
    sanitized = re.sub(r"\bportraits?\b", "cinematic framing", raw_prompt, flags=re.IGNORECASE)
    return sanitized


def _generate_with_pollinations_flux(
    prompt: str,
    output_path: Path,
    aspect_ratio: str = "16:9",
    seed: Optional[int] = None,
) -> bool:
    """
    Intenta generar imagen cinemática vía Pollinations AI:
    Soporta clave de API para modelos premium y fallback a modelo estándar en 16:9 o 9:16 con semilla consistente.
    Aplica desinfección estricta de prompts contra el envenenamiento por palabras de encuadre humano.
    """
    # Desinfectar cualquier remanente de 'portrait' o 'portraits' para evitar que Flux pinte rostros/mujeres
    clean_prompt = re.sub(r"\bportraits?\b", "cinematic framing", prompt, flags=re.IGNORECASE)
    clean_prompt = re.sub(r"[^\w\s,.:;-]", " ", clean_prompt)
    clean_prompt = " ".join(clean_prompt.split()[:65])
    encoded = urllib.parse.quote(clean_prompt)

    target_w, target_h = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
    seed_param = f"&seed={seed}" if seed is not None else ""

    api_key = getattr(settings, "POLLINATIONS_API_KEY", "") or (
        settings.IMAGE_API_KEY if settings.IMAGE_API_KEY and not settings.IMAGE_API_KEY.startswith("tu_clave") else ""
    )

    headers = dict(BROWSER_HEADERS)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        url = f"https://image.pollinations.ai/prompt/{encoded}?model=flux&width={target_w}&height={target_h}{seed_param}&nologo=true"
    else:
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={target_w}&height={target_h}{seed_param}&nologo=true"

    try:
        logger.info("Intentando generación vía Pollinations ({}) [{}] (seed: {})...", aspect_ratio, f"{target_w}x{target_h}", seed or "auto")
        resp = requests.get(url, headers=headers, timeout=22)
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


_WIKIMEDIA_HEADERS = {"User-Agent": "EducationalVideoBot/1.0 (educational; open-source documentary)"}


@lru_cache(maxsize=256)
def _wikimedia_search(query: str, target_width: int) -> tuple[str, ...]:
    """Busca imágenes JPEG/PNG en Wikimedia Commons y retorna sus URLs (en caché por sesión)."""
    url = (
        f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
        f"&gsrsearch={urllib.parse.quote(query)}&gsrnamespace=6&format=json"
        f"&prop=imageinfo&iiprop=url|mime&iiurlwidth={target_width}"
    )
    try:
        resp = requests.get(url, headers=_WIKIMEDIA_HEADERS, timeout=12)
        if resp.status_code != 200:
            return ()
        pages = sorted(resp.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    except Exception as e:
        logger.warning("Fallo al consultar Wikimedia Commons ('{}'): {}", query, e)
        return ()
    urls = []
    for page in pages:
        info = page.get("imageinfo", [{}])[0]
        img_url = info.get("thumburl") or info.get("url")
        mime = info.get("mime", "")
        if img_url and ("image/jpeg" in mime or "image/png" in mime):
            urls.append(img_url)
    return tuple(urls)


def _fetch_from_wikimedia_commons(prompt: str, output_path: Path, keywords: Optional[str] = None, aspect_ratio: str = "16:9", index: int = 0) -> bool:
    """
    Descarga el candidato número `index` de Wikimedia Commons (fotografías históricas, mapas, archivos).
    Ideal para historia, guerras, biografías y ciencia.
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

    queries_to_try = [query]
    words = query.split()
    if len(words) > 3:
        queries_to_try.append(" ".join(words[:3]))

    target_width = 1080 if aspect_ratio == "9:16" else 1920
    urls: list[str] = []
    for q in queries_to_try:
        urls += [u for u in _wikimedia_search(q, target_width) if u not in urls]
        if len(urls) > index:
            break
    if index >= len(urls):
        return False

    logger.info("Descargando candidato #{} de Wikimedia Commons para '{}'...", index + 1, query)
    try:
        dl = requests.get(urls[index], headers=_WIKIMEDIA_HEADERS, timeout=15)
        if dl.status_code == 200 and len(dl.content) > 10000:
            output_path.write_bytes(dl.content)
            _normalize_image_to_resolution(output_path, aspect_ratio)
            return True
    except Exception as e:
        logger.warning("Fallo al descargar de Wikimedia Commons: {}", e)
    return False


@lru_cache(maxsize=256)
def _pexels_search(query: str, orientation: str) -> tuple[str, ...]:
    """Busca en Pexels API y retorna las URLs de las fotos (en caché por sesión)."""
    api_key = getattr(settings, "PEXELS_API_KEY", "") or os.getenv("PEXELS_API_KEY", "")
    headers = {"Authorization": api_key, "User-Agent": "EducationalVideoBot/1.0 (educational documentary video)"}
    orient_param = f"&orientation={orientation}" if orientation else ""
    url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}{orient_param}&per_page=5"
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return ()
        photos = resp.json().get("photos", [])
    except Exception as e:
        logger.debug("Error en búsqueda Pexels ('{}'): {}", query, e)
        return ()
    urls = []
    for p in photos:
        src = p.get("src", {})
        img_url = src.get("large2x") or src.get("large") or src.get("portrait") or src.get("original")
        if img_url:
            urls.append(img_url)
    return tuple(urls)


def _fetch_from_pexels(prompt: str, keywords: str, output_path: Path, aspect_ratio: str = "16:9", index: int = 0) -> bool:
    """
    Descarga el candidato número `index` de Pexels usando una cascada de consultas
    (específica -> simplificada -> sin filtro de orientación). La auditoría se hace por lote después.
    """
    api_key = getattr(settings, "PEXELS_API_KEY", "") or os.getenv("PEXELS_API_KEY", "")
    if not api_key:
        logger.debug("Pexels API key no configurada (PEXELS_API_KEY). Saltando Pexels.")
        return False

    # 1. Construir cascada inteligente de términos de búsqueda
    primary_query = (keywords or "").strip()
    extracted_prompt_query = _extract_keywords_from_prompt(prompt)

    query_candidates: list[str] = []
    if primary_query:
        query_candidates.append(primary_query)
        words = primary_query.split()
        if len(words) > 2:
            query_candidates.append(" ".join(words[:2]))
            query_candidates.append(" ".join(words[-2:]))

    if extracted_prompt_query and extracted_prompt_query not in query_candidates:
        query_candidates.append(extracted_prompt_query)

    # 2. Estrategias escalonadas: consulta principal y secundaria en la orientación objetivo, luego orientación abierta
    target_orientation = "portrait" if aspect_ratio == "9:16" else "landscape"
    search_strategies: list[tuple[str, str]] = []
    if query_candidates:
        search_strategies.append((query_candidates[0], target_orientation))
        if len(query_candidates) > 1:
            search_strategies.append((query_candidates[1], target_orientation))
        search_strategies.append((query_candidates[0], ""))

    urls: list[str] = []
    for query, orientation in search_strategies:
        urls += [u for u in _pexels_search(query, orientation) if u not in urls]
        if len(urls) > index:
            break
    if index >= len(urls):
        return False

    logger.info("Descargando candidato #{} de Pexels para '{}'...", index + 1, primary_query or extracted_prompt_query)
    try:
        dl = requests.get(urls[index], timeout=10)
        if dl.status_code == 200 and len(dl.content) > 10000:
            output_path.write_bytes(dl.content)
            _normalize_image_to_resolution(output_path, aspect_ratio)
            return True
    except Exception as e:
        logger.debug("Error descargando foto de Pexels: {}", e)
    return False


def _fetch_from_nasa_archive(prompt: str, output_path: Path, scene_id: int, aspect_ratio: str = "16:9") -> bool:
    """
    Obtiene fotografías científicas reales en alta resolución del archivo oficial de la NASA.
    Solo se activa si el tema o prompt contiene términos astronómicos o cosmológicos explícitos.
    """
    space_pattern = re.compile(
        r"\b(space|galaxy|galaxies|nebula|universe|stars?|astronomy|cosmic|black hole|telescope|planets?|solar system|multiverse|quantum|everett)\b",
        re.IGNORECASE
    )
    if not space_pattern.search(prompt):
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


def _generate_procedural_fallback_image(scene_id: int, prompt: str, output_path: Path, aspect_ratio: str = "16:9") -> bool:
    """
    Genera un fondo procedural (gradiente oscuro) como último recurso para que el montaje no se rompa.
    El control de calidad (src/quality_gate.py) lo detecta y bloquea la publicación.
    """
    try:
        from PIL import Image, ImageDraw
        target_w, target_h = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
        img = Image.new("RGB", (target_w, target_h), (12, 16, 24))
        draw = ImageDraw.Draw(img)

        # Paletas documentales oscuras y elegantes según el ID de la escena
        color_palettes = [
            ((15, 23, 42), (30, 41, 59)),    # Slate dark
            ((24, 24, 27), (39, 39, 42)),    # Zinc dark
            ((10, 18, 30), (20, 35, 60)),    # Deep ocean
            ((28, 15, 19), (45, 20, 25)),    # Dark mahogany
            ((18, 22, 25), (32, 44, 48)),    # Deep teal
            ((25, 20, 15), (42, 32, 22)),    # Amber bronze dark
        ]
        top_col, bot_col = color_palettes[scene_id % len(color_palettes)]

        for y in range(target_h):
            factor = y / float(target_h)
            r = int(top_col[0] * (1 - factor) + bot_col[0] * factor)
            g = int(top_col[1] * (1 - factor) + bot_col[1] * factor)
            b = int(top_col[2] * (1 - factor) + bot_col[2] * factor)
            draw.line([(0, y), (target_w, y)], fill=(r, g, b))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, format="PNG")
        logger.warning("Fondo procedural generado como salvaguarda para escena #{:03d}: {}", scene_id, output_path.name)
        return True
    except Exception as e:
        logger.error("Error al generar fondo procedural: {}", e)
        return False


# Máximo de candidatos por fuente para cada escena
_SOURCE_LIMITS = {"fal": 1, "imagen": 1, "pollinations": 2, "pexels": 4, "nasa": 1, "wikimedia": 4}
MAX_AUDIT_ROUNDS = 4


def _build_source_plan(
    scene: Scene,
    provider: Optional[str],
    aspect_ratio: str,
    visual_contract: Optional[object],
    topic_seed: Optional[int],
) -> list[tuple[str, Callable[[Path, int], bool]]]:
    """
    Define el orden de fuentes para una escena. Cada fuente descarga su candidato número `index`
    sin auditarlo: la auditoría visual se hace después, por lote (src/quality_gate.py).
    """
    selected_provider = (provider or settings.IMAGE_PROVIDER).lower()
    shot_type = scene.shot_type or "macro_detail"
    prompt = scene.visual_prompt
    keywords = scene.search_keywords or ""
    cohesive_prompt = _build_cohesive_prompt(prompt, visual_contract, shot_type=shot_type, aspect_ratio=aspect_ratio)
    scene_seed = (topic_seed + scene.scene_id * 31) if topic_seed is not None else None

    plan: list[tuple[str, Callable[[Path, int], bool]]] = []

    # 1. Fal.ai Flux-Schnell (si hay API Key de Fal o se selecciona fal)
    if selected_provider == "fal" or (settings.IMAGE_API_KEY and settings.IMAGE_API_KEY.startswith("fal_")):
        plan.append(("fal", lambda out, i: _generate_with_fal(cohesive_prompt, out, aspect_ratio=aspect_ratio)
                     and _normalize_image_to_resolution(out, aspect_ratio)))

    # 2. Google Imagen (si hay API Key de Google configurada o se selecciona imagen)
    if selected_provider == "imagen" or (settings.IMAGE_API_KEY and "AIza" in settings.IMAGE_API_KEY):
        plan.append(("imagen", lambda out, i: _generate_with_google_imagen(cohesive_prompt, out, aspect_ratio=aspect_ratio)
                     and _normalize_image_to_resolution(out, aspect_ratio)))

    # 3. Pollinations: sin clave, los temas bélicos se omiten (el modelo gratuito los degrada)
    has_custom_key = bool(
        getattr(settings, "POLLINATIONS_API_KEY", "")
        or (settings.IMAGE_API_KEY and not settings.IMAGE_API_KEY.startswith("tu_clave"))
    )
    combat_terms = [
        r"\bwar\b", r"\bbattle\b", r"\bsoldier\b", r"\barmy\b", r"\bhitler\b", r"\bnazi\b",
        r"\binvasion\b", r"\bmilitary\b", r"\bcombat\b", r"\bbomb\b", r"\bstalingrad\b", r"\bnormandy\b"
    ]
    p_check = (cohesive_prompt + " " + keywords).lower()
    if has_custom_key or not any(re.search(term, p_check) for term in combat_terms):
        remedy_prompt = f"{cohesive_prompt}, uninhabited scene, absolutely no humans, no people, clean frame, no watermarks, no logos"

        def _pollinations(out: Path, i: int) -> bool:
            if i == 0:
                return _generate_with_pollinations_flux(cohesive_prompt, out, aspect_ratio=aspect_ratio, seed=scene_seed)
            remedy_seed = (scene_seed + 101 * i) if scene_seed is not None else None
            return _generate_with_pollinations_flux(remedy_prompt, out, aspect_ratio=aspect_ratio, seed=remedy_seed)

        plan.append(("pollinations", _pollinations))

    # 4. Pexels API (fotografía real contextual)
    plan.append(("pexels", lambda out, i: _fetch_from_pexels(prompt, keywords, out, aspect_ratio=aspect_ratio, index=i)))

    # 5. NASA (solo temas astronómicos)
    plan.append(("nasa", lambda out, i: _fetch_from_nasa_archive(prompt, out, scene.scene_id, aspect_ratio=aspect_ratio)))

    # 6. Wikimedia Commons (archivo histórico real)
    plan.append(("wikimedia", lambda out, i: _fetch_from_wikimedia_commons(prompt, out, keywords, aspect_ratio=aspect_ratio, index=i)))

    return plan


def _fetch_next_candidate(state: dict, output_path: Path) -> Optional[str]:
    """Descarga el siguiente candidato del plan de fuentes de la escena. Retorna el nombre de la fuente o None."""
    plan = state["plan"]
    while state["pos"] < len(plan):
        name, fetch = plan[state["pos"]]
        tries = state["tries"].get(name, 0)
        if tries >= _SOURCE_LIMITS[name]:
            state["pos"] += 1
            continue
        state["tries"][name] = tries + 1
        try:
            ok = bool(fetch(output_path, tries))
        except Exception as e:
            logger.warning("Fuente '{}' falló para escena #{:03d}: {}", name, state["idx"], e)
            ok = False
        if ok and output_path.exists() and output_path.stat().st_size > 10000:
            return name
        state["pos"] += 1  # fuente caída o sin más resultados: pasar a la siguiente
    return None


def _prompt_signature(scene: Scene, aspect_ratio: str) -> str:
    return hashlib.sha1(f"{aspect_ratio}|{scene.visual_prompt}".encode("utf-8")).hexdigest()[:16]


def generate_images_for_scenes(
    scenes: List[Scene],
    output_dir: Optional[Path] = None,
    provider: Optional[str] = None,
    topic: Optional[str] = None,
    aspect_ratio: str = "16:9",
    visual_contract: Optional[object] = None,
) -> List[Path]:
    """
    Obtiene una imagen por escena en assets/images/scene_{idx:03d}.png (16:9 o 9:16):
    1. Reutiliza imágenes en caché solo si el prompt de la escena no cambió (firma por escena).
    2. Descarga candidatos de la cascada de fuentes sin auditar.
    3. Descarta duplicados y audita todo el lote con UNA llamada de visión por ronda.
    4. Re-intenta solo las escenas rechazadas, hasta MAX_AUDIT_ROUNDS rondas.
    El estado de cada escena queda en image_manifest.json para el control de calidad previo a publicar.
    """
    target_dir = output_dir or settings.IMAGES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    total = len(scenes)
    workers = getattr(settings, "CONCURRENT_IMAGE_WORKERS", 4)
    qa_enabled = getattr(settings, "ENABLE_IMAGE_QA_GATEKEEPER", True)
    era = getattr(visual_contract, "era_setting", "") if visual_contract else ""
    logger.info("Iniciando obtención de {} imágenes (Workers: {}, Formato: {}, Tema: '{}')...", total, workers, aspect_ratio, topic or "General")

    manifest = load_manifest(target_dir)
    cache_manifest = load_manifest(settings.IMAGES_DIR) if target_dir != settings.IMAGES_DIR else manifest
    entries: dict[int, dict] = {}
    to_fetch: list[int] = []
    to_audit: set[int] = set()

    for idx, scene in enumerate(scenes, start=1):
        filename = f"scene_{idx:03d}.png"
        img_path = target_dir / filename
        sig = _prompt_signature(scene, aspect_ratio)
        cached = manifest["scenes"].get(str(idx), {})
        shared = cache_manifest["scenes"].get(str(idx), {})
        shared_path = settings.IMAGES_DIR / filename

        if img_path.exists() and img_path.stat().st_size > 10000 and cached.get("prompt_sig") == sig:
            logger.info("Reutilizando imagen en caché para escena #{:03d} (auditoría previa: {})", idx, cached.get("audit"))
            entries[idx] = cached
        elif shared_path.exists() and shared_path.stat().st_size > 10000 and shared.get("prompt_sig") == sig:
            shutil.copy2(shared_path, img_path)
            logger.info("Reutilizando imagen de assets/images/ para escena #{:03d} (auditoría previa: {})", idx, shared.get("audit"))
            entries[idx] = dict(shared)
        else:
            entries[idx] = {"prompt_sig": sig, "source": None, "audit": "pending", "reason": "", "issues": []}
            to_fetch.append(idx)
            continue
        if entries[idx].get("audit") != "approved":
            to_audit.add(idx)

    paths = {idx: target_dir / f"scene_{idx:03d}.png" for idx in range(1, total + 1)}
    topic_seed = int(hashlib.sha1(topic.lower().strip().encode("utf-8")).hexdigest(), 16) % 500000 if topic else 12345
    states = {
        idx: {"idx": idx, "pos": 0, "tries": {}, "plan": _build_source_plan(scenes[idx - 1], provider, aspect_ratio, visual_contract, topic_seed)}
        for idx in to_fetch
    }

    def _fetch_worker(idx: int) -> tuple[int, Optional[str]]:
        scene = scenes[idx - 1]
        state = states.setdefault(
            idx, {"idx": idx, "pos": 0, "tries": {}, "plan": _build_source_plan(scene, provider, aspect_ratio, visual_contract, topic_seed)}
        )
        logger.info("[{}/{}] Buscando candidato para Escena #{:03d} (Plano: '{}'): '{}...'", idx, total, idx, scene.shot_type, scene.visual_prompt[:60])
        source = _fetch_next_candidate(state, paths[idx])
        if source is None and paths[idx].exists():
            return idx, "keep"  # sin más candidatos: se conserva el último para revisión humana
        if source is None:
            _generate_procedural_fallback_image(idx, scene.visual_prompt, paths[idx], aspect_ratio=aspect_ratio)
        return idx, source

    for round_no in range(1, MAX_AUDIT_ROUNDS + 1):
        if to_fetch:
            logger.info("Ronda {}/{}: descargando candidatos para {} escena(s)...", round_no, MAX_AUDIT_ROUNDS, len(to_fetch))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for future in as_completed([executor.submit(_fetch_worker, i) for i in to_fetch]):
                    idx, source = future.result()
                    if source == "keep":
                        continue
                    if source is None:
                        entries[idx].update(source="procedural", audit="no_source", reason="Ninguna fuente entregó un candidato", issues=[])
                    else:
                        entries[idx].update(source=source, audit="pending", reason="", issues=[])
                        to_audit.add(idx)

        # Duplicados: se conserva la primera aparición y se re-intentan las demás
        retry: set[int] = set()
        candidates = {i: p for i, p in paths.items() if entries[i]["audit"] != "no_source"}
        for dup, orig in find_duplicates(candidates).items():
            entries[dup].update(audit="duplicate", reason=f"Duplicado de la escena {orig}", issues=["DUPLICATE"])
            to_audit.discard(dup)
            retry.add(dup)

        if to_audit:
            if not qa_enabled:
                for i in to_audit:
                    entries[i].update(audit="disabled", reason="Auditoría de visión deshabilitada")
            else:
                items = [
                    {"idx": i, "path": paths[i], "narration": scenes[i - 1].narration_text,
                     "prompt": scenes[i - 1].visual_prompt, "shot_type": scenes[i - 1].shot_type}
                    for i in sorted(to_audit)
                ]
                verdicts = audit_images_batch(items, era=era)
                if verdicts is None:
                    for i in to_audit:
                        entries[i].update(audit="unaudited", reason="Visión no disponible (fail-closed)")
                    break
                for i, (approved, reason, issues) in verdicts.items():
                    entries[i].update(audit="approved" if approved else "rejected", reason=reason, issues=issues)
                    if not approved:
                        retry.add(i)
        to_audit = set()

        # Solo se re-intentan escenas cuya cascada aún tiene candidatos
        to_fetch = sorted(i for i in retry if i not in states or states[i]["pos"] < len(states[i]["plan"]))
        if not to_fetch:
            break

    manifest = {"topic": topic, "aspect_ratio": aspect_ratio, "scenes": {str(i): e for i, e in entries.items()}}
    save_manifest(target_dir, manifest)

    image_paths = [paths[i] for i in range(1, total + 1)]
    statuses = [e["audit"] for e in entries.values()]
    logger.info(
        "Imágenes listas: {} aprobadas, {} sin aprobar ({}).",
        statuses.count("approved") + statuses.count("disabled"),
        total - statuses.count("approved") - statuses.count("disabled"),
        ", ".join(f"#{i}:{e['audit']}" for i, e in sorted(entries.items()) if e["audit"] not in ("approved", "disabled")) or "ninguna",
    )
    return image_paths
