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
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from typing import Callable, List, Optional
import requests

from src.config import settings
from src.logger import logger
from src.quality_gate import SOURCE_KINDS, audit_images_batch, find_duplicates, load_manifest, save_manifest
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


MAX_CROP_RATIO = 1.25  # por encima, recortar perdería demasiado: se usa fondo desenfocado


def _fit_with_blurred_background(im, target_w: int, target_h: int):
    """Coloca la imagen completa (ajustada al ancho o alto) sobre una versión desenfocada y oscurecida de sí misma."""
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    background = ImageOps.fit(im, (target_w, target_h), method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(radius=40))
    background = ImageEnhance.Brightness(background).enhance(0.55)
    foreground = ImageOps.contain(im, (target_w, target_h), method=Image.Resampling.LANCZOS)
    background.paste(foreground, ((target_w - foreground.width) // 2, (target_h - foreground.height) // 2))
    return background


def _normalize_image_to_resolution(image_path: Path, aspect_ratio: str = "16:9") -> bool:
    """
    Garantiza que la imagen esté exactamente en resolución requerida:
    1920x1080 (16:9) o 1080x1920 (9:16 vertical), sin bordes negros ni distorsión.
    Si el formato de origen difiere mucho (ej. foto horizontal de archivo en video vertical),
    la coloca completa sobre un fondo desenfocado en vez de recortar el centro.
    Aplica mejoras visuales sutiles (contraste, nitidez) si está habilitado.
    """
    try:
        from PIL import Image, ImageOps, ImageEnhance
        target_w, target_h = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            src_ratio, dst_ratio = im.width / im.height, target_w / target_h
            if max(src_ratio, dst_ratio) / min(src_ratio, dst_ratio) > MAX_CROP_RATIO:
                fitted = _fit_with_blurred_background(im, target_w, target_h)
            else:
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


def _pollinations_key() -> str:
    """Clave de Pollinations: POLLINATIONS_API_KEY o, si no, IMAGE_API_KEY cuando no es el valor de ejemplo."""
    return getattr(settings, "POLLINATIONS_API_KEY", "") or (
        settings.IMAGE_API_KEY if settings.IMAGE_API_KEY and not settings.IMAGE_API_KEY.startswith("tu_clave") else ""
    )


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

    # Sin clave, Pollinations entrega un modelo básico con marca de agua que el control siempre rechaza
    api_key = _pollinations_key()
    if not api_key:
        return False
    headers = dict(BROWSER_HEADERS)
    headers["Authorization"] = f"Bearer {api_key}"
    # API con clave (sk_): cobra del saldo de Pollen; FLUX schnell ~0,002 Pollen por imagen
    url = f"https://gen.pollinations.ai/image/{encoded}?model=flux&width={target_w}&height={target_h}{seed_param}&nologo=true"

    try:
        logger.info("Intentando generación vía Pollinations ({}) [{}] (seed: {})...", aspect_ratio, f"{target_w}x{target_h}", seed or "auto")
        resp = requests.get(url, headers=headers, timeout=90)
        if resp.status_code == 200 and len(resp.content) > 10000:
            output_path.write_bytes(resp.content)
            _normalize_image_to_resolution(output_path, aspect_ratio)
            logger.success("Visual cinemático generado con Pollinations: {}", output_path.name)
            return True
        if resp.status_code == 402:
            logger.warning("Pollinations: saldo de Pollen insuficiente (HTTP 402).")
        else:
            logger.warning("Pollinations respondió HTTP {}", resp.status_code)
        return False
    except Exception as e:
        logger.warning("Timeout o fallo en Pollinations: {}", e)
        return False


_WIKIMEDIA_HEADERS = {"User-Agent": "EducationalVideoBot/1.0 (educational; open-source documentary)"}
_BLOCKED_LICENSE = re.compile(r"\b(NC|ND)\b|non-?commercial|no derivatives", re.IGNORECASE)
_ARCHIVE_TRANSLATIONS = {
    "agujeros negros": "black hole",
    "agujero negro": "black hole",
    "segunda guerra mundial": "world war ii",
    "primera guerra mundial": "world war i",
    "biblioteca de alejandria": "library of alexandria ancient",
    "multiverso": "multiverse physics",
    "inmortalidad cuantica": "quantum physics",
}


def _strip_html(value: str) -> str:
    value = re.sub(r'<span style="display: ?none;?">.*?</span>', "", value or "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip()


@lru_cache(maxsize=256)
def _wikimedia_search(query: str, target_width: int) -> tuple[dict, ...]:
    """
    Busca imágenes JPEG/PNG en Wikimedia Commons con autor y licencia (en caché por sesión).
    Descarta licencias no comerciales (NC), sin obras derivadas (ND) o sin licencia declarada.
    """
    url = (
        f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
        f"&gsrsearch={urllib.parse.quote(query)}&gsrnamespace=6&gsrlimit=10&format=json"
        f"&prop=imageinfo&iiprop=url|mime|extmetadata&iiurlwidth={target_width}"
        f"&iiextmetadatafilter=LicenseShortName|Artist|LicenseUrl|AttributionRequired"
    )
    try:
        resp = requests.get(url, headers=_WIKIMEDIA_HEADERS, timeout=12)
        if resp.status_code != 200:
            return ()
        pages = sorted(resp.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    except Exception as e:
        logger.warning("Fallo al consultar Wikimedia Commons ('{}'): {}", query, e)
        return ()
    results = []
    for page in pages:
        info = page.get("imageinfo", [{}])[0]
        img_url = info.get("thumburl") or info.get("url")
        mime = info.get("mime", "")
        md = info.get("extmetadata", {})
        license_name = _strip_html(md.get("LicenseShortName", {}).get("value", ""))
        if not img_url or not ("image/jpeg" in mime or "image/png" in mime):
            continue
        if not license_name or _BLOCKED_LICENSE.search(license_name):
            continue
        results.append({
            "url": img_url,
            "title": page.get("title", ""),
            "page_url": info.get("descriptionurl", ""),
            "author": _strip_html(md.get("Artist", {}).get("value", "")) or "Autor desconocido",
            "license": license_name,
            "license_url": md.get("LicenseUrl", {}).get("value", ""),
            "attribution_required": md.get("AttributionRequired", {}).get("value", "true") != "false",
        })
    return tuple(results)


def _scene_archive_queries(
    prompt: str,
    keywords: Optional[str],
    decade: Optional[str],
    archive_queries: Optional[list[str]] = None,
    places: Optional[list[str]] = None,
) -> list[str]:
    """
    Consultas por escena, de más específica a más general: las consultas de archivo del guion,
    las palabras clave con la década, sin ella, simplificadas, y por último lugar + década de la época.
    """
    query = (keywords or _extract_keywords_from_prompt(prompt)).strip()
    q_clean = query.lower()
    for es_term, en_term in _ARCHIVE_TRANSLATIONS.items():
        if es_term in q_clean:
            query = q_clean.replace(es_term, en_term)
            break
    queries = [q.strip() for q in (archive_queries or []) if q and q.strip()]
    if decade and decade not in query and not re.search(r"\b1[0-9]{3}s?\b", query):
        queries.append(f"{query} {decade}")
    queries.append(query)
    words = query.split()
    if len(words) > 3:
        queries.append(" ".join(words[:3]))
    for place in places or []:
        queries.append(f"{place} {decade}" if decade else place)
    return list(dict.fromkeys(queries))


def _era_places(era: str) -> list[str]:
    """Lugares mencionados en era_setting (partes sin años), ej. 'Western Australian Outback'."""
    parts = [p.strip() for p in era.split(",")]
    return [p for p in parts if p and not re.search(r"\d", p)][:2]


def _download_candidate(meta: dict, output_path: Path, aspect_ratio: str, headers: Optional[dict] = None) -> Optional[dict]:
    try:
        dl = requests.get(meta["url"], headers=headers, timeout=15)
        if dl.status_code == 200 and len(dl.content) > 10000:
            output_path.write_bytes(dl.content)
            _normalize_image_to_resolution(output_path, aspect_ratio)
            return meta
    except Exception as e:
        logger.warning("Fallo al descargar candidato {}: {}", meta.get("url", "")[:80], e)
    return None


def _fetch_from_archive(
    search: Callable[[str], tuple[dict, ...]],
    label: str,
    queries: list[tuple[str, int]],
    output_path: Path,
    aspect_ratio: str = "16:9",
    index: int = 0,
) -> Optional[dict]:
    """
    Descarga el candidato número `index` de un archivo combinando varias consultas.
    queries: [(consulta, rotación)]; la rotación reparte entre escenas los resultados de una consulta genérica
    para que no todas empiecen por la misma foto. Retorna los metadatos (autor, licencia) o None.
    """
    candidates: list[dict] = []
    for q, rotate in queries:
        found = list(search(q))
        if rotate and found:
            k = rotate % len(found)
            found = found[k:] + found[:k]
        seen = {c["url"] for c in candidates}
        candidates += [c for c in found if c["url"] not in seen]
        if len(candidates) > index:
            break
    if index >= len(candidates):
        return None
    meta = candidates[index]
    logger.info("Descargando de {}: {} ({})", label, meta["title"], meta["license"])
    return _download_candidate(meta, output_path, aspect_ratio, headers=_WIKIMEDIA_HEADERS)


def _fetch_from_wikimedia_commons(queries: list[tuple[str, int]], output_path: Path, aspect_ratio: str = "16:9", index: int = 0) -> Optional[dict]:
    target_width = 1080 if aspect_ratio == "9:16" else 1920
    return _fetch_from_archive(lambda q: _wikimedia_search(q, target_width), "Wikimedia Commons", queries, output_path, aspect_ratio, index)


_OPENVERSE_PUBLIC_DOMAIN = {"cc0", "pdm"}


@lru_cache(maxsize=256)
def _openverse_search(query: str) -> tuple[dict, ...]:
    """
    Busca en Openverse (Flickr Commons, bibliotecas y museos; sin cuenta) solo licencias que permiten
    uso comercial y modificación. Límite anónimo ~20 peticiones/min: ante 429 se espera y se reintenta una vez.
    """
    url = (
        f"https://api.openverse.org/v1/images/?q={urllib.parse.quote(query)}"
        f"&license_type=commercial,modification&page_size=10"
    )
    data = None
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=_WIKIMEDIA_HEADERS, timeout=20)
            if resp.status_code == 429 and attempt == 0:
                time.sleep(4)
                continue
            if resp.status_code == 200:
                data = resp.json()
            break
        except Exception as e:
            logger.warning("Fallo al consultar Openverse ('{}'): {}", query, e)
            break
    if not data:
        return ()
    results = []
    for x in data.get("results", []):
        if not x.get("url") or (x.get("filetype") or "jpg").lower() not in ("jpg", "jpeg", "png"):
            continue
        lic = (x.get("license") or "").lower()
        license_name = "Dominio público" if lic in _OPENVERSE_PUBLIC_DOMAIN else f"CC {lic.upper()} {x.get('license_version') or ''}".strip()
        results.append({
            "url": x["url"],
            "title": x.get("title") or "",
            "page_url": x.get("foreign_landing_url") or "",
            "author": x.get("creator") or "Autor desconocido",
            "license": license_name,
            "license_url": x.get("license_url") or "",
            "attribution_required": lic not in _OPENVERSE_PUBLIC_DOMAIN,
        })
    return tuple(results)


def _fetch_from_openverse(queries: list[tuple[str, int]], output_path: Path, aspect_ratio: str = "16:9", index: int = 0) -> Optional[dict]:
    return _fetch_from_archive(_openverse_search, "Openverse", queries, output_path, aspect_ratio, index)


@lru_cache(maxsize=256)
def _pexels_search(query: str, orientation: str) -> tuple[dict, ...]:
    """Busca en Pexels API y retorna las fotos con su autor (en caché por sesión)."""
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
    results = []
    for p in photos:
        src = p.get("src", {})
        img_url = src.get("large2x") or src.get("large") or src.get("portrait") or src.get("original")
        if img_url:
            results.append({
                "url": img_url,
                "title": p.get("alt", ""),
                "page_url": p.get("url", ""),
                "author": p.get("photographer", ""),
                "license": "Pexels License",
                "license_url": "https://www.pexels.com/license/",
                "attribution_required": False,
            })
    return tuple(results)


def _fetch_from_pexels(prompt: str, keywords: str, output_path: Path, aspect_ratio: str = "16:9", index: int = 0) -> Optional[dict]:
    """
    Descarga el candidato número `index` de Pexels usando una cascada de consultas
    (específica -> simplificada -> sin filtro de orientación). La auditoría se hace por lote después.
    """
    api_key = getattr(settings, "PEXELS_API_KEY", "") or os.getenv("PEXELS_API_KEY", "")
    if not api_key:
        logger.debug("Pexels API key no configurada (PEXELS_API_KEY). Saltando Pexels.")
        return None

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

    candidates: list[dict] = []
    for query, orientation in search_strategies:
        seen = {c["url"] for c in candidates}
        candidates += [c for c in _pexels_search(query, orientation) if c["url"] not in seen]
        if len(candidates) > index:
            break
    if index >= len(candidates):
        return None

    logger.info("Descargando candidato #{} de Pexels para '{}'...", index + 1, primary_query or extracted_prompt_query)
    return _download_candidate(candidates[index], output_path, aspect_ratio)


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
_SOURCE_LIMITS = {
    "wikimedia_topic": 4, "wikimedia_scene": 5, "openverse": 4, "pexels": 3, "nasa": 1,
    "fal": 1, "imagen": 1, "pollinations": 2,
}
MAX_AUDIT_ROUNDS = 8  # cada ronda prueba un candidato por escena pendiente y cuesta una llamada de visión

FetchFn = Callable[[Path, int], Optional[dict]]


def _ai_meta(provider_name: str, ok: bool) -> Optional[dict]:
    return {"title": "", "author": provider_name, "license": "Generada por IA", "attribution_required": False} if ok else None


def _build_source_plan(
    scene: Scene,
    provider: Optional[str],
    aspect_ratio: str,
    visual_contract: Optional[object],
    topic_seed: Optional[int],
) -> list[tuple[str, FetchFn]]:
    """
    Define el orden de fuentes para una escena: archivo real primero (Wikimedia por tema, Wikimedia y Openverse por escena),
    luego stock (Pexels), NASA y por último IA. Cada fuente descarga su candidato número `index`
    sin auditarlo (la auditoría visual se hace después, por lote) y retorna sus metadatos de autor/licencia.
    """
    selected_provider = (provider or settings.IMAGE_PROVIDER).lower()
    shot_type = scene.shot_type or "macro_detail"
    prompt = scene.visual_prompt
    keywords = scene.search_keywords or ""
    cohesive_prompt = _build_cohesive_prompt(prompt, visual_contract, shot_type=shot_type, aspect_ratio=aspect_ratio)
    scene_seed = (topic_seed + scene.scene_id * 31) if topic_seed is not None else None

    era = getattr(visual_contract, "era_setting", "") or ""
    year = re.search(r"\b(1[0-9]{3})s?\b", era)
    decade = f"{int(year.group(1)) // 10 * 10}s" if year else None
    topic_terms = (getattr(visual_contract, "archive_search_terms", None) or "").strip()

    plan: list[tuple[str, FetchFn]] = []

    # 1. Wikimedia por tema: fotos reales del hecho (ej. "Emu War"), primero combinadas con la escena
    if topic_terms:
        scene_words = " ".join(keywords.split()[:2])
        topic_queries = [(f"{topic_terms} {scene_words}".strip(), 0), (topic_terms, scene.scene_id - 1)]
        plan.append(("wikimedia_topic", lambda out, i: _fetch_from_wikimedia_commons(topic_queries, out, aspect_ratio, index=i)))

    # 2. Wikimedia y Openverse por escena: consultas del guion, palabras clave con década y lugar + década
    scene_queries = [
        (q, 0) for q in _scene_archive_queries(prompt, keywords, decade, scene.archive_queries, _era_places(era))
    ]
    plan.append(("wikimedia_scene", lambda out, i: _fetch_from_wikimedia_commons(scene_queries, out, aspect_ratio, index=i)))
    plan.append(("openverse", lambda out, i: _fetch_from_openverse(scene_queries, out, aspect_ratio, index=i)))

    # 3. Pexels API (stock contemporáneo: útil para paisajes y objetos atemporales)
    plan.append(("pexels", lambda out, i: _fetch_from_pexels(prompt, keywords, out, aspect_ratio=aspect_ratio, index=i)))

    # 4. NASA (solo temas astronómicos)
    plan.append(("nasa", lambda out, i: {"title": "", "author": "NASA", "license": "NASA (dominio público)", "attribution_required": False}
                 if _fetch_from_nasa_archive(prompt, out, scene.scene_id, aspect_ratio=aspect_ratio) else None))

    # 5. Fal.ai Flux-Schnell (si hay API Key de Fal o se selecciona fal)
    if selected_provider == "fal" or (settings.IMAGE_API_KEY and settings.IMAGE_API_KEY.startswith("fal_")):
        plan.append(("fal", lambda out, i: _ai_meta("Fal.ai Flux", bool(
            _generate_with_fal(cohesive_prompt, out, aspect_ratio=aspect_ratio) and _normalize_image_to_resolution(out, aspect_ratio)))))

    # 6. Google Imagen (si hay API Key de Google configurada o se selecciona imagen)
    if selected_provider == "imagen" or (settings.IMAGE_API_KEY and "AIza" in settings.IMAGE_API_KEY):
        plan.append(("imagen", lambda out, i: _ai_meta("Google Imagen", bool(
            _generate_with_google_imagen(cohesive_prompt, out, aspect_ratio=aspect_ratio) and _normalize_image_to_resolution(out, aspect_ratio)))))

    # 7. Pollinations (FLUX) solo con clave: sin ella las imágenes traen marca de agua y siempre se rechazan
    if _pollinations_key():
        remedy_prompt = f"{cohesive_prompt}, uninhabited scene, absolutely no humans, no people, clean frame, no watermarks, no logos"

        def _pollinations(out: Path, i: int) -> Optional[dict]:
            if i == 0:
                ok = _generate_with_pollinations_flux(cohesive_prompt, out, aspect_ratio=aspect_ratio, seed=scene_seed)
            else:
                remedy_seed = (scene_seed + 101 * i) if scene_seed is not None else None
                ok = _generate_with_pollinations_flux(remedy_prompt, out, aspect_ratio=aspect_ratio, seed=remedy_seed)
            return _ai_meta("Pollinations", ok)

        plan.append(("pollinations", _pollinations))

    return plan


def _fetch_next_candidate(state: dict, output_path: Path) -> Optional[str]:
    """
    Descarga el siguiente candidato del plan de fuentes de la escena.
    Retorna el nombre de la fuente (y deja sus metadatos en state["meta"]) o None si no quedan candidatos.
    """
    plan = state["plan"]
    while state["pos"] < len(plan):
        name, fetch = plan[state["pos"]]
        tries = state["tries"].get(name, 0)
        if tries >= _SOURCE_LIMITS[name]:
            state["pos"] += 1
            continue
        state["tries"][name] = tries + 1
        try:
            meta = fetch(output_path, tries)
        except Exception as e:
            logger.warning("Fuente '{}' falló para escena #{:03d}: {}", name, state["idx"], e)
            meta = None
        if meta is not None and output_path.exists() and output_path.stat().st_size > 10000:
            state["meta"] = meta
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
    topic_label = (getattr(visual_contract, "archive_search_terms", None) or topic or "") if visual_contract else (topic or "")
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
        if entries[idx].get("audit") in ("rejected", "duplicate"):
            to_fetch.append(idx)  # se continúa la cascada donde quedó (ver "cascade" más abajo)
        elif entries[idx].get("audit") != "approved":
            to_audit.add(idx)

    paths = {idx: target_dir / f"scene_{idx:03d}.png" for idx in range(1, total + 1)}
    topic_seed = int(hashlib.sha1(topic.lower().strip().encode("utf-8")).hexdigest(), 16) % 500000 if topic else 12345
    states = {}
    for idx in to_fetch:
        plan = _build_source_plan(scenes[idx - 1], provider, aspect_ratio, visual_contract, topic_seed)
        state = {"idx": idx, "pos": 0, "tries": {}, "plan": plan}
        saved = entries[idx].get("cascade")
        if saved:
            # Reanudar: misma fuente y mismos candidatos ya probados, para no repetir los rechazados
            names = [name for name, _ in plan]
            state["pos"] = names.index(saved["source"]) if saved.get("source") in names else 0
            state["tries"] = dict(saved.get("tries", {}))
            state["meta"] = entries[idx].get("credit")
        states[idx] = state

    def _fetch_worker(idx: int) -> tuple[int, Optional[str]]:
        scene = scenes[idx - 1]
        state = states.setdefault(
            idx, {"idx": idx, "pos": 0, "tries": {}, "plan": _build_source_plan(scene, provider, aspect_ratio, visual_contract, topic_seed)}
        )
        logger.info("[{}/{}] Buscando candidato para Escena #{:03d} (Plano: '{}'): '{}...'", idx, total, idx, scene.shot_type, scene.visual_prompt[:60])
        source = _fetch_next_candidate(state, paths[idx])
        if source is None and state.get("meta") is not None:
            return idx, "keep"  # sin más candidatos: se conserva el último para revisión humana
        if source is None:
            _generate_procedural_fallback_image(idx, scene.visual_prompt, paths[idx], aspect_ratio=aspect_ratio)
        return idx, source

    vision_down = False
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
                        entries[idx].update(source=source, credit=states[idx]["meta"], audit="pending", reason="", issues=[])
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
            elif vision_down:
                for i in to_audit:
                    entries[i].update(audit="unaudited", reason="Visión no disponible (fail-closed)")
            else:
                items = [
                    {"idx": i, "path": paths[i], "narration": scenes[i - 1].narration_text,
                     "prompt": scenes[i - 1].visual_prompt, "shot_type": scenes[i - 1].shot_type,
                     "source_kind": SOURCE_KINDS.get(entries[i].get("source") or "", "unknown"),
                     "source_title": (entries[i].get("credit") or {}).get("title", "") if SOURCE_KINDS.get(entries[i].get("source") or "") == "archive" else ""}
                    for i in sorted(to_audit)
                ]
                verdicts = audit_images_batch(items, era=era, topic=topic_label)
                if verdicts is None:
                    # Sin visión no se audita más, pero se siguen reemplazando duplicados
                    vision_down = True
                    verdicts = {}
                    for i in to_audit:
                        entries[i].update(audit="unaudited", reason="Visión no disponible (fail-closed)")
                for i, (approved, reason, issues) in verdicts.items():
                    entries[i].update(audit="approved" if approved else "rejected", reason=reason, issues=issues)
                    if not approved:
                        retry.add(i)
        to_audit = set()

        # Solo se re-intentan escenas cuya cascada aún tiene candidatos
        to_fetch = sorted(i for i in retry if i not in states or states[i]["pos"] < len(states[i]["plan"]))
        if not to_fetch:
            break

    for i, state in states.items():
        plan = state["plan"]
        entries[i]["cascade"] = {
            "source": plan[state["pos"]][0] if state["pos"] < len(plan) else None,
            "tries": state["tries"],
        }
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
