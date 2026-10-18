"""
Módulo de Control de Calidad Visual previo a la publicación (Fase 15 / FR-12).
Provee:
1. Auditoría por lote con Gemini Vision: una sola llamada evalúa todas las escenas.
2. Detección de fondos procedurales (degradados) y de imágenes duplicadas (dHash).
3. Hoja de contacto para revisión humana.
4. Veredicto de bloqueo de publicación (gate).
"""
import io
import json
import os
import re
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
MAX_MERGED_SCENES = 2  # escenas sin imagen válida que pueden extender la imagen anterior
DUPLICATE_MAX_COLOR_DIFF = 12  # diferencia media por canal (0-255) en miniatura 16x16
AUDIT_BATCH_SIZE = 16
# Resolución enviada al revisor: a 432x768 las marcas de agua tenues (ej. "©Old World Auctions") desaparecían
AUDIT_IMAGE_SIZE = (864, 1536)

_VISION_LOCK = threading.Lock()
_LAST_VISION_CALL = 0.0
_EXHAUSTED_VISION_MODELS: set[str] = set()
_NO_JSON_MODE_MODELS: set[str] = set()
_DISCOVERED_VISION_MODELS: Optional[list[str]] = None
_VISION_MODEL_PATTERN = re.compile(r"^(gemini-[\w.-]*flash[\w.-]*|gemma-[\w.-]+)$")
_VISION_MODEL_EXCLUDE = re.compile(r"image|tts|audio|live|transcribe|banana")
TRANSIENT_RETRY_WAIT = 5


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

SOURCE_KINDS = {
    "wikimedia_topic": "archive", "wikimedia_scene": "archive", "openverse": "archive", "nasa": "archive",
    "pexels": "stock",
    "fal": "ai", "imagen": "ai", "pollinations": "ai",
}


def _build_batch_prompt(items: list[dict], era: str, topic: str = "") -> str:
    lines = [
        "You are a rigorous QA inspector for a historical/educational documentary video.",
        f"Video topic: \"{topic or 'unspecified'}\". Global era/setting: \"{era or 'unspecified'}\".",
        "You will receive several candidate images, each preceded by its label 'IMAGE <n>'.",
        "Each image has a SOURCE type. Apply the rules for its source:",
        "",
        "WATERMARKS (all sources, check first): scan every image carefully, including its edges, for watermarks that may be faint,",
        "  semi-transparent, small or repeated in a diagonal/tiled pattern: '©' notices, auction houses or dealers, stock agencies",
        "  (Alamy, Getty, Shutterstock, iStock...), photographer or museum stamps added later, URLs. Any such watermark → reject (WATERMARK_OR_TEXT).",
        "  Printed text that belongs to the original historical item (map labels, banknote text, document text) is NOT a watermark.",
        "",
        "ARCHIVE (real historical material from a public archive: photographs, and also period paintings, portraits,",
        "  engravings, maps, banknotes and documents; before the 1840s there is no photography, so these are the expected archive material):",
        "- Judge it against the NARRATION and the historical event/topic, NOT against the exact camera framing of the intended subject.",
        "- Approve it if it plausibly shows the event, its place, its people, its objects or its era. A related photo of the same event is acceptable even if it shows a different moment.",
        "- People from the period are expected and fine. Black-and-white, grain, low resolution or old damage are fine.",
        "- Later photos of the SAME real place or object (ruins, memorials, containment structures, the place today) are correct, not anachronisms,",
        "  when the narration talks about the aftermath, consequences, legacy or how the place is now.",
        "- Reject: photos from a clearly different era, country or conflict (ANACHRONISM); unrelated subjects (ABSURD_DISSONANCE);",
        "  collages, multi-panel montages, memes or modern graphics (COLLAGE); maps or text documents when the narration describes an action (ABSURD_DISSONANCE);",
        "  watermarks or overlaid modern text (WATERMARK_OR_TEXT).",
        "",
        "STOCK (a contemporary stock photo):",
        "- Only acceptable for timeless subjects that fit the narration: landscapes, nature, animals, generic old objects,",
        "  or present-day photos of the SAME real place when the narration talks about the aftermath, legacy or the place today.",
        "- Reject any modern element: modern people, clothing, vehicles, weapons, equipment or buildings (ANACHRONISM);",
        "  people when the scene does not call for them (UNWANTED_HUMAN); unrelated subjects (ABSURD_DISSONANCE); watermarks (WATERMARK_OR_TEXT);",
        "  visible text that is gibberish, invented or misspelled (WATERMARK_OR_TEXT).",
        "",
        "AI (an AI-generated image): apply strict rules.",
        "- It must depict the intended subject. Any human is forbidden in environmental_wide or macro_detail shots (UNWANTED_HUMAN).",
        "- Reject anachronisms, unrelated subjects, distorted anatomy or faces, watermarks or text.",
        "- Read any visible lettering (signs, posters, documents, labels, coins): if it is gibberish, invented words or misspelled names,",
        "  reject it (WATERMARK_OR_TEXT) even if the rest of the image fits the scene.",
        "",
        "Scene contexts:",
    ]
    for it in items:
        source = it.get("source_kind") or "unknown"
        title = f"; archive title=\"{it['source_title']}\"" if it.get("source_title") else ""
        if source == "archive":
            # El "sujeto previsto" describe un encuadre pensado para IA; para archivo solo cuentan narración y hecho
            lines.append(f"- IMAGE {it['idx']}: SOURCE=ARCHIVE{title}; narration (Spanish)=\"{it.get('narration', '')}\"")
            continue
        lines.append(
            f"- IMAGE {it['idx']}: SOURCE={source.upper()}{title}; shot_type='{it.get('shot_type') or 'unspecified'}'; "
            f"narration (Spanish)=\"{it.get('narration', '')}\"; intended subject=\"{it.get('prompt', '')[:300]}\""
        )
    lines += [
        "",
        "Also rate 'impact' from 1 to 10 for every image: how striking and instantly understandable it would be as the",
        "FIRST frame of a vertical video on a phone (a big, clear, recognizable subject, strong contrast, emotion or surprise = high;",
        "dark, empty, generic or cluttered = low).",
        "",
        "Output strictly JSON with one verdict per image:",
        '{"verdicts": [{"scene": <n>, "approved": true|false, "impact": <1-10>, "reason": "brief explanation in Spanish", '
        '"detected_issues": ["UNWANTED_HUMAN"|"WATERMARK_OR_TEXT"|"ABSURD_DISSONANCE"|"ANACHRONISM"|"COLLAGE"]}]}',
    ]
    return "\n".join(lines)


def _model_rank(name: str) -> tuple:
    """Orden de preferencia: flash antes que flash-lite y gemma; versión más reciente primero."""
    family = 2 if name.startswith("gemma") else (1 if "lite" in name else 0)
    version = re.search(r"(\d+(?:\.\d+)?)", name)
    return (family, -float(version.group(1)) if version else 0.0, name)


def get_vision_models(client) -> list[str]:
    """
    Modelos de visión a probar, en orden. Con GEMINI_VISION_MODELS en .env se usa esa lista tal cual;
    si no, los preferidos de la configuración y después todos los modelos gratuitos multimodales
    que la API ofrezca (cada uno tiene su propia cuota diaria).
    """
    global _DISCOVERED_VISION_MODELS
    if os.getenv("GEMINI_VISION_MODELS"):
        return settings.get_gemini_vision_candidates()
    if _DISCOVERED_VISION_MODELS is None:
        found: list[str] = []
        try:
            for m in client.models.list():
                name = m.name.removeprefix("models/")
                if ("generateContent" in (m.supported_actions or [])
                        and _VISION_MODEL_PATTERN.match(name) and not _VISION_MODEL_EXCLUDE.search(name)):
                    found.append(name)
        except Exception as e:
            logger.warning("No se pudo listar modelos de visión: {}", e)
        preferred = settings.get_gemini_vision_candidates()
        _DISCOVERED_VISION_MODELS = preferred + sorted((n for n in found if n not in preferred), key=_model_rank)
        logger.info("Modelos de visión disponibles ({}): {}", len(_DISCOVERED_VISION_MODELS), ", ".join(_DISCOVERED_VISION_MODELS))
    return _DISCOVERED_VISION_MODELS


def _classify_vision_error(msg: str) -> str:
    """'daily' (cuota del día agotada), 'bad_request' (petición no aceptada) o 'transient' (por minuto / saturado)."""
    if "PerDay" in msg or "per_day" in msg.lower() or "limit: 0" in msg:
        return "daily"
    if "400" in msg or "INVALID_ARGUMENT" in msg or "404" in msg or "NOT_FOUND" in msg:
        return "bad_request"
    return "transient"


def _parse_json_text(text: str) -> Optional[dict]:
    """Extrae el objeto JSON de una respuesta, aunque venga envuelta en texto o bloques de código."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                pass
    return None


def _call_vision(contents: list) -> Optional[dict]:
    """
    Recorre los modelos de visión hasta obtener una respuesta JSON. Retorna None si ninguno responde.
    Cuota diaria agotada o petición no aceptada: el modelo se descarta para la sesión.
    Límite por minuto o saturación: un reintento tras TRANSIENT_RETRY_WAIT segundos y luego el siguiente modelo.
    Modelos sin modo JSON (p. ej. Gemma): se repite sin response_mime_type y se extrae el JSON del texto.
    """
    global _LAST_VISION_CALL
    from google import genai

    client = genai.Client(api_key=settings.GEMINI_API_KEY, http_options={"timeout": 90000})
    with _VISION_LOCK:
        for model in get_vision_models(client):
            if model in _EXHAUSTED_VISION_MODELS:
                continue
            use_json = model not in _NO_JSON_MODE_MODELS
            transient_retried = False
            while True:
                elapsed = time.time() - _LAST_VISION_CALL
                if elapsed < 1.2:
                    time.sleep(1.2 - elapsed)
                _LAST_VISION_CALL = time.time()
                try:
                    config = {"response_mime_type": "application/json"} if use_json else None
                    resp = client.models.generate_content(model=model, contents=contents, config=config)
                    data = _parse_json_text(resp.text)
                    if data is not None:
                        logger.info("Auditoría visual resuelta con '{}'.", model)
                        return data
                    logger.warning("Respuesta de '{}' sin JSON válido. Probando siguiente...", model)
                    break
                except Exception as e:
                    msg = str(e)
                    kind = _classify_vision_error(msg)
                    if kind == "daily":
                        logger.warning("Modelo de visión '{}' agotó su cuota diaria. Descartado para esta sesión.", model)
                        _EXHAUSTED_VISION_MODELS.add(model)
                        break
                    if kind == "bad_request" and use_json:
                        use_json = False
                        _NO_JSON_MODE_MODELS.add(model)
                        continue
                    if kind == "bad_request":
                        logger.warning("Modelo '{}' no acepta la auditoría ({}). Descartado para esta sesión.", model, msg[:120])
                        _EXHAUSTED_VISION_MODELS.add(model)
                        break
                    if not transient_retried:
                        transient_retried = True
                        logger.info("Modelo '{}' saturado o con límite por minuto; reintento en {}s...", model, TRANSIENT_RETRY_WAIT)
                        time.sleep(TRANSIENT_RETRY_WAIT)
                        continue
                    logger.warning("Modelo '{}' sigue no disponible ({}). Probando siguiente...", model, msg[:120])
                    break
    return None


def _jpeg_part(path: Path):
    """
    Miniatura en JPEG para la revisión visual. Si se pasa la imagen de PIL, el SDK la envía en PNG (~4 veces más
    pesada) y con conexiones lentas la subida del lote agota el tiempo de espera (FR-19.7).
    """
    from google.genai import types

    with Image.open(path) as im:
        thumb = im.convert("RGB")
    thumb.thumbnail(AUDIT_IMAGE_SIZE)
    buf = io.BytesIO()
    thumb.save(buf, "JPEG", quality=85)
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")


def audit_images_batch(items: list[dict], era: str = "", topic: str = "") -> Optional[dict[int, tuple[bool, str, list[str], int]]]:
    """
    Audita varias escenas con UNA llamada de visión por lote (máx. AUDIT_BATCH_SIZE imágenes).
    items: [{"idx": int, "path": Path, "narration": str, "prompt": str, "shot_type": str,
             "source_kind": "archive"|"stock"|"ai", "source_title": str}]
    Retorna {idx: (aprobada, motivo, problemas, impacto 1-10)} o None si la visión no está disponible (fail-closed).
    """
    if not items:
        return {}
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY no configurada: las imágenes quedan sin auditar.")
        return None

    results: dict[int, tuple[bool, str, list[str], int]] = {}
    for start in range(0, len(items), AUDIT_BATCH_SIZE):
        batch = items[start:start + AUDIT_BATCH_SIZE]
        contents: list = [_build_batch_prompt(batch, era, topic)]
        for it in batch:
            contents += [f"IMAGE {it['idx']}:", _jpeg_part(it["path"])]

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
                results[it["idx"]] = (False, "Sin veredicto del auditor para esta imagen", ["NO_VERDICT"], 0)
                continue
            approved = bool(v.get("approved", False))
            issues = [str(i) for i in v.get("detected_issues", [])]
            try:
                impact = max(0, min(10, int(v.get("impact", 0))))
            except (TypeError, ValueError):
                impact = 0
            results[it["idx"]] = (approved, str(v.get("reason", "")), issues, impact)
            log = logger.info if approved else logger.warning
            log("[QA Lote] Escena #{:03d} {}: {}", it["idx"], "APROBADA" if approved else f"RECHAZADA ({', '.join(issues)})", v.get("reason", ""))
    return results


Verdict = tuple[bool, str, list[str], int]
_JUDGMENT_ISSUES = {"ANACHRONISM", "ABSURD_DISSONANCE"}


def is_doubtful(verdict: Verdict, source_kind: str) -> bool:
    """
    Veredicto dudoso (FR-19.9): aprobada pese a señalar algún problema, o foto de archivo rechazada solo por
    criterios de juicio (época o relación con la narración), donde el revisor suele cambiar de opinión.
    """
    approved, _, issues, _ = verdict
    if approved:
        return bool(issues)
    return source_kind == "archive" and bool(issues) and set(issues) <= _JUDGMENT_ISSUES


def vote_on_doubtful(items: list[dict], verdicts: dict[int, Verdict], era: str = "", topic: str = "") -> dict[int, Verdict]:
    """
    Voto por mayoría solo para los veredictos dudosos: una segunda opinión y, si no coincide, una tercera.
    Si falta la tercera con un empate, gana el rechazo (fail-closed). Las imágenes claras no gastan más cuota.
    """
    doubtful = [it for it in items if it["idx"] in verdicts and is_doubtful(verdicts[it["idx"]], it.get("source_kind") or "")]
    if not doubtful:
        return verdicts
    logger.info("Segunda opinión para {} imagen(es) dudosa(s): {}", len(doubtful), ", ".join(f"#{it['idx']}" for it in doubtful))
    second = audit_images_batch(doubtful, era=era, topic=topic) or {}
    split = [it for it in doubtful if it["idx"] in second and second[it["idx"]][0] != verdicts[it["idx"]][0]]
    third = (audit_images_batch(split, era=era, topic=topic) or {}) if split else {}

    result = dict(verdicts)
    for it in doubtful:
        i = it["idx"]
        votes = [v for v in (verdicts[i], second.get(i), third.get(i)) if v is not None]
        approvals = sum(1 for v in votes if v[0])
        winner = approvals * 2 > len(votes)
        result[i] = next(v for v in votes if v[0] == winner)
        if winner != verdicts[i][0]:
            logger.info("Escena #{:03d}: la mayoría ({}/{}) cambia el veredicto a {}.", i, max(approvals, len(votes) - approvals),
                        len(votes), "APROBADA" if winner else "RECHAZADA")
    return result


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
    merges: dict[int, int] = field(default_factory=dict)  # {escena sin imagen válida: escena aprobada que se extiende}
    unaudited: set[int] = field(default_factory=set)  # escenas que solo fallan por falta de revisión visual


def evaluate_gate(image_paths: list[Path], manifest: dict) -> GateResult:
    """
    Aplica FR-12 y FR-14.6: decide si el video puede publicarse automáticamente.
    Una escena sin imagen válida (fondo procedural, duplicada o sin aprobación visual) se fusiona con la
    escena válida anterior, hasta MAX_MERGED_SCENES por video y nunca la primera. Si se supera, el video se bloquea.
    """
    reasons: list[str] = []
    paths = {i: p for i, p in enumerate(image_paths, start=1)}
    problems: dict[int, str] = {}

    for i, p in paths.items():
        if is_procedural_placeholder(p):
            problems[i] = "fondo procedural"
    duplicates = find_duplicates({i: p for i, p in paths.items() if i not in problems})
    for dup, orig in duplicates.items():
        problems[dup] = f"duplicada de la escena {orig}"
    scenes = manifest.get("scenes", {})
    for i in paths:
        status = scenes.get(str(i), {}).get("audit", "unaudited")
        if status not in ("approved", "disabled") and i not in problems:
            problems[i] = status

    merges: dict[int, int] = {}
    detail = ", ".join(f"{i}:{why}" for i, why in sorted(problems.items()))
    if 1 in problems:
        reasons.append(f"La primera escena no tiene imagen válida ({problems[1]}). Escenas con problemas: {detail}")
    elif len(problems) > MAX_MERGED_SCENES:
        reasons.append(f"{len(problems)} escenas sin imagen válida (máximo fusionable: {MAX_MERGED_SCENES}): {detail}")
    else:
        for i in sorted(problems):
            merges[i] = max(j for j in paths if j < i and j not in problems)

    unaudited = {i for i, why in problems.items() if why == "unaudited"}
    return GateResult(passed=not reasons, reasons=reasons, failing_scenes=set(problems), merges=merges, unaudited=unaudited)


def choose_opening_image(image_paths: list[Path], manifest: dict, merges: dict[int, int], min_gain: int = 2) -> Optional[Path]:
    """
    Imagen para el plano de apertura (FR-17.2): la de mayor impacto entre las escenas aprobadas y no fusionadas,
    solo si supera a la escena 1 por al menos `min_gain` puntos. Si no, la apertura usa la propia escena 1.
    """
    scenes = manifest.get("scenes", {})

    def impact(i: int) -> int:
        e = scenes.get(str(i), {})
        return int(e.get("impact") or 0) if e.get("audit") in ("approved", "disabled") else -1

    candidates = [i for i in range(1, len(image_paths) + 1) if i not in merges and impact(i) >= 0]
    if not candidates:
        return None
    best = max(candidates, key=impact)
    if best != 1 and impact(best) >= impact(1) + min_gain:
        logger.info("Apertura con la escena #{:03d} (impacto {}) en lugar de la #001 (impacto {}).", best, impact(best), impact(1))
        return image_paths[best - 1]
    return None


def build_contact_sheet(
    image_paths: list[Path], output_path: Path, failing: set[int] = frozenset(), cols: int = 7, merged: set[int] = frozenset()
) -> Path:
    """Genera una hoja de contacto numerada: verde = válida, naranja = se fusiona con la anterior, rojo = bloquea."""
    tile_w, tile_h, border = 216, 384, 6
    rows = (len(image_paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), (0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=32)
    for n, path in enumerate(image_paths, start=1):
        x, y = ((n - 1) % cols) * tile_w, ((n - 1) // cols) * tile_h
        with Image.open(path) as im:
            sheet.paste(im.convert("RGB").resize((tile_w, tile_h)), (x, y))
        color = (240, 150, 30) if n in merged else (220, 40, 40) if n in failing else (40, 190, 80)
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
    build_contact_sheet(image_paths, contact_sheet_path, result.failing_scenes, merged=set(result.merges))
    for scene, target in sorted(result.merges.items()):
        logger.warning("Escena #{:03d} sin imagen válida: se extiende la imagen de la escena #{:03d}.", scene, target)
    if result.passed:
        logger.success("Control de calidad visual SUPERADO. Hoja de contacto: {}", contact_sheet_path)
    else:
        logger.error("Control de calidad visual FALLIDO. Hoja de contacto: {}", contact_sheet_path)
        for r in result.reasons:
            logger.error("  - {}", r)
    return result
