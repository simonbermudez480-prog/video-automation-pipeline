"""
Módulo de Control de Calidad Visual previo a la publicación (Fase 15 / FR-12).
Provee:
1. Auditoría por lote con Gemini Vision: una sola llamada evalúa todas las escenas.
2. Detección de fondos procedurales (degradados) y de imágenes duplicadas (dHash).
3. Hoja de contacto para revisión humana.
4. Veredicto de bloqueo de publicación (gate).
"""
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageStat

from src.config import settings
from src.logger import logger

MANIFEST_NAME = "image_manifest.json"
DUPLICATE_MAX_DISTANCE = 5
DUPLICATE_MAX_COLOR_DIFF = 12  # diferencia media por canal (0-255) en miniatura 16x16
AUDIT_BATCH_SIZE = 16
QA_ISSUES = ("UNWANTED_HUMAN", "WATERMARK_OR_TEXT", "ABSURD_DISSONANCE", "ANACHRONISM")

_VISION_LOCK = threading.Lock()
_LAST_VISION_CALL = 0.0
_EXHAUSTED_VISION_MODELS: set[str] = set()


# ---------------------------------------------------------------------------
# Detección local (sin API)
# ---------------------------------------------------------------------------

def is_procedural_placeholder(image_path: Path) -> bool:
    """Detecta el fondo procedural de salvaguarda: filas casi uniformes y rango tonal mínimo."""
    with Image.open(image_path) as im:
        gray = im.convert("L").resize((54, 96))
    lo, hi = gray.getextrema()
    if hi - lo > 60:
        return False
    row_stddevs = [ImageStat.Stat(gray.crop((0, y, 54, y + 1))).stddev[0] for y in range(96)]
    return sum(row_stddevs) / len(row_stddevs) < 1.5


def dhash(image_path: Path, size: int = 8) -> int:
    """Hash perceptual por diferencias: imágenes casi idénticas producen hashes cercanos."""
    with Image.open(image_path) as im:
        gray = im.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    px = list(gray.getdata())
    bits = 0
    for r in range(size):
        for c in range(size):
            left = px[r * (size + 1) + c]
            right = px[r * (size + 1) + c + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def _color_thumb(image_path: Path) -> list[int]:
    with Image.open(image_path) as im:
        return list(im.convert("RGB").resize((16, 16)).tobytes())


def find_duplicates(image_paths: dict[int, Path]) -> dict[int, int]:
    """
    Retorna {escena_duplicada: escena_original}. Un par es duplicado si su dHash es cercano
    Y sus colores coinciden (evita confundir cielos o fondos lisos distintos, cuyo dHash es casi nulo).
    """
    hashes = {idx: dhash(p) for idx, p in image_paths.items()}
    thumbs = {idx: _color_thumb(p) for idx, p in image_paths.items()}
    duplicates: dict[int, int] = {}
    ordered = sorted(hashes)
    for i, a in enumerate(ordered):
        if a in duplicates:
            continue
        for b in ordered[i + 1:]:
            if b in duplicates or bin(hashes[a] ^ hashes[b]).count("1") > DUPLICATE_MAX_DISTANCE:
                continue
            color_diff = sum(abs(x - y) for x, y in zip(thumbs[a], thumbs[b])) / len(thumbs[a])
            if color_diff <= DUPLICATE_MAX_COLOR_DIFF:
                duplicates[b] = a
    return duplicates


# ---------------------------------------------------------------------------
# Auditoría por lote con Gemini Vision
# ---------------------------------------------------------------------------

def _build_batch_prompt(items: list[dict], era: str) -> str:
    lines = [
        "You are an uncompromising QA inspector for a historical/educational documentary video.",
        f"Global era/setting of the video: \"{era or 'unspecified'}\".",
        "You will receive several candidate images, each preceded by its label 'IMAGE <n>'.",
        "For each image, check its own scene context below and evaluate 4 disqualifiers:",
        "1. UNWANTED_HUMAN: accidental, modern or out-of-context people (any human is forbidden in environmental_wide or macro_detail shots).",
        "2. WATERMARK_OR_TEXT: visible watermarks, stock logos, URLs, subtitles or modern branding.",
        "3. ABSURD_DISSONANCE: the image does not tangibly or atmospherically depict the scene (e.g. pets, houseplants, beaches, modern cities for a historical battle).",
        "4. ANACHRONISM: clothing, weapons, vehicles or objects clearly from a different era than the scene.",
        "",
        "Scene contexts:",
    ]
    for it in items:
        lines.append(
            f"- IMAGE {it['idx']}: shot_type='{it.get('shot_type') or 'unspecified'}'; "
            f"narration (Spanish)=\"{it.get('narration', '')}\"; intended subject=\"{it.get('prompt', '')[:300]}\""
        )
    lines += [
        "",
        "Output strictly JSON with one verdict per image:",
        '{"verdicts": [{"scene": <n>, "approved": true|false, "reason": "brief explanation in Spanish", '
        '"detected_issues": ["UNWANTED_HUMAN"|"WATERMARK_OR_TEXT"|"ABSURD_DISSONANCE"|"ANACHRONISM"]}]}',
    ]
    return "\n".join(lines)


def _call_vision(contents: list) -> Optional[dict]:
    """Llama a la cascada de modelos de visión. Retorna None si todos están agotados o caídos."""
    global _LAST_VISION_CALL
    from google import genai

    client = genai.Client(api_key=settings.GEMINI_API_KEY, http_options={"timeout": 60000})
    with _VISION_LOCK:
        for model in settings.get_gemini_vision_candidates():
            if model in _EXHAUSTED_VISION_MODELS:
                continue
            elapsed = time.time() - _LAST_VISION_CALL
            if elapsed < 1.2:
                time.sleep(1.2 - elapsed)
            _LAST_VISION_CALL = time.time()
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config={"response_mime_type": "application/json"},
                )
                return json.loads(resp.text or "{}")
            except Exception as e:
                msg = str(e)
                if "RESOURCE_EXHAUSTED" in msg or "per_day" in msg or "PerDay" in msg or "quota" in msg.lower():
                    logger.warning("Modelo de visión '{}' agotó su cuota. Marcado como no disponible.", model)
                    _EXHAUSTED_VISION_MODELS.add(model)
                else:
                    logger.warning("Fallo de auditoría por lote con '{}': {}. Probando siguiente...", model, msg[:200])
    return None


def audit_images_batch(items: list[dict], era: str = "") -> Optional[dict[int, tuple[bool, str, list[str]]]]:
    """
    Audita varias escenas con UNA llamada de visión por lote (máx. AUDIT_BATCH_SIZE imágenes).
    items: [{"idx": int, "path": Path, "narration": str, "prompt": str, "shot_type": str}]
    Retorna {idx: (aprobada, motivo, problemas)} o None si la visión no está disponible (fail-closed).
    """
    if not items:
        return {}
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY no configurada: las imágenes quedan sin auditar.")
        return None

    results: dict[int, tuple[bool, str, list[str]]] = {}
    for start in range(0, len(items), AUDIT_BATCH_SIZE):
        batch = items[start:start + AUDIT_BATCH_SIZE]
        contents: list = [_build_batch_prompt(batch, era)]
        for it in batch:
            with Image.open(it["path"]) as im:
                thumb = im.convert("RGB")
                thumb.thumbnail((432, 768))
            contents += [f"IMAGE {it['idx']}:", thumb]

        logger.info("Auditoría visual por lote: {} imagen(es) en una sola llamada...", len(batch))
        data = _call_vision(contents)
        if data is None:
            logger.warning("Visión no disponible (fail-closed): {} imagen(es) quedan sin auditar.", len(batch))
            return None

        by_scene = {}
        for v in data.get("verdicts", []):
            try:
                by_scene[int(v.get("scene"))] = v
            except (TypeError, ValueError):
                continue
        for it in batch:
            v = by_scene.get(it["idx"])
            if v is None:
                results[it["idx"]] = (False, "Sin veredicto del auditor para esta imagen", ["NO_VERDICT"])
                continue
            approved = bool(v.get("approved", False))
            issues = [str(i) for i in v.get("detected_issues", [])]
            results[it["idx"]] = (approved, str(v.get("reason", "")), issues)
            log = logger.info if approved else logger.warning
            log("[QA Lote] Escena #{:03d} {}: {}", it["idx"], "APROBADA" if approved else f"RECHAZADA ({', '.join(issues)})", v.get("reason", ""))
    return results


# ---------------------------------------------------------------------------
# Manifiesto, hoja de contacto y gate de publicación
# ---------------------------------------------------------------------------

def load_manifest(images_dir: Path) -> dict:
    path = images_dir / MANIFEST_NAME
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Manifiesto de imágenes ilegible ({}): {}", path, e)
    return {"scenes": {}}


def save_manifest(images_dir: Path, manifest: dict) -> None:
    (images_dir / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    failing_scenes: set[int] = field(default_factory=set)


def evaluate_gate(image_paths: list[Path], manifest: dict) -> GateResult:
    """Aplica FR-12.1 y FR-12.2: decide si el video puede publicarse automáticamente."""
    reasons: list[str] = []
    failing: set[int] = set()
    paths = {i: p for i, p in enumerate(image_paths, start=1)}

    placeholders = [i for i, p in paths.items() if is_procedural_placeholder(p)]
    hook_placeholders = [i for i in placeholders if i <= 3]
    if hook_placeholders:
        reasons.append(f"Fondo procedural en el gancho (escenas {hook_placeholders})")
    if len(placeholders) > 1:
        reasons.append(f"{len(placeholders)} fondos procedurales en total (escenas {placeholders})")
    failing.update(placeholders if (hook_placeholders or len(placeholders) > 1) else [])

    duplicates = find_duplicates({i: p for i, p in paths.items() if i not in placeholders})
    if duplicates:
        pairs = ", ".join(f"{dup}={orig}" for dup, orig in sorted(duplicates.items()))
        reasons.append(f"Imágenes duplicadas (escena=original): {pairs}")
        failing.update(duplicates)

    scenes = manifest.get("scenes", {})
    not_approved = []
    for i in paths:
        status = scenes.get(str(i), {}).get("audit", "unaudited")
        if status not in ("approved", "disabled"):
            not_approved.append(f"{i}:{status}")
            failing.add(i)
    if not_approved:
        reasons.append(f"Escenas sin aprobación visual: {', '.join(not_approved)}")

    return GateResult(passed=not reasons, reasons=reasons, failing_scenes=failing)


def build_contact_sheet(image_paths: list[Path], output_path: Path, failing: set[int] = frozenset(), cols: int = 7) -> Path:
    """Genera una hoja de contacto numerada; las escenas con problemas llevan borde rojo."""
    tile_w, tile_h, border = 216, 384, 6
    rows = (len(image_paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), (0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=32)
    for n, path in enumerate(image_paths, start=1):
        x, y = ((n - 1) % cols) * tile_w, ((n - 1) // cols) * tile_h
        with Image.open(path) as im:
            sheet.paste(im.convert("RGB").resize((tile_w, tile_h)), (x, y))
        color = (220, 40, 40) if n in failing else (40, 190, 80)
        draw.rectangle([x, y, x + tile_w - 1, y + tile_h - 1], outline=color, width=border)
        draw.rectangle([x + border, y + border, x + 70, y + 46], fill=(0, 0, 0))
        draw.text((x + 12, y + 8), f"#{n}", fill=(255, 255, 255), font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path


def run_quality_gate(image_paths: list[Path], contact_sheet_path: Path) -> GateResult:
    """Evalúa el gate con el manifiesto de la carpeta de imágenes y genera la hoja de contacto."""
    manifest = load_manifest(image_paths[0].parent) if image_paths else {"scenes": {}}
    result = evaluate_gate(image_paths, manifest)
    build_contact_sheet(image_paths, contact_sheet_path, result.failing_scenes)
    if result.passed:
        logger.success("Control de calidad visual SUPERADO. Hoja de contacto: {}", contact_sheet_path)
    else:
        logger.error("Control de calidad visual FALLIDO. Hoja de contacto: {}", contact_sheet_path)
        for r in result.reasons:
            logger.error("  - {}", r)
    return result
