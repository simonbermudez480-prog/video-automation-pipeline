"""
Módulo de Procesamiento de Audio, Detección de Silencios y Alineación Temporal.
Utiliza:
1. faster-whisper para transcripción local con timestamps por palabra y segmento.
2. pydub para análisis de duración y detección de pausas/silencios naturales.
3. Generación y exportación de subtítulos sincronizados en formato .srt.
"""
import difflib
import math
import re
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

from pydub import AudioSegment
from pydub.silence import detect_silence

from src.config import settings
from src.logger import logger
from src.script_generator import Scene


def format_timestamp_srt(seconds: float) -> str:
    """Convierte segundos a formato estándar SRT: HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis = 0
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def get_audio_info_and_silences(
    audio_path: Path,
    min_silence_len_ms: int = 250,
    silence_thresh_offset_db: float = 14.0,
) -> Tuple[float, List[Tuple[float, float]]]:
    """
    Analiza el archivo de audio con pydub.
    Devuelve la duración total en segundos y la lista de intervalos de silencio [(start_s, end_s)].
    """
    logger.info("Analizando propiedades acústicas y silencios de: {}", audio_path)
    audio = AudioSegment.from_file(str(audio_path))
    total_duration_s = len(audio) / 1000.0

    silence_thresh = audio.dBFS - silence_thresh_offset_db
    # Evitar umbrales absurdamente bajos si el audio es muy silencioso
    silence_thresh = max(silence_thresh, -50.0)

    silences_ms = detect_silence(
        audio,
        min_silence_len=min_silence_len_ms,
        silence_thresh=silence_thresh,
    )

    silences_s = [(start / 1000.0, end / 1000.0) for start, end in silences_ms]
    logger.info(
        "Duración total del audio: {:.2f}s | Silencios/pausas detectadas: {}",
        total_duration_s,
        len(silences_s),
    )
    return total_duration_s, silences_s


def transcribe_audio_with_whisper(audio_path: Path) -> List[Dict[str, Any]]:
    """
    Ejecuta transcripción local rápida usando faster-whisper con marcas por palabra.
    """
    beam_size = getattr(settings, "WHISPER_BEAM_SIZE", 1)
    logger.info(
        "Iniciando transcripción con faster-whisper (Modelo: {}, Device: {}, Beam: {})...",
        settings.WHISPER_MODEL,
        settings.WHISPER_DEVICE,
        beam_size,
    )
    from faster_whisper import WhisperModel

    # Cargar modelo en modo CPU optimizado o CUDA según configuración
    compute_type = "int8" if settings.WHISPER_DEVICE == "cpu" else "float16"
    model = WhisperModel(
        settings.WHISPER_MODEL,
        device=settings.WHISPER_DEVICE,
        compute_type=compute_type,
    )

    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        beam_size=beam_size,
        vad_filter=False,
    )

    extracted_segments = []
    for seg in segments:
        words = []
        if seg.words:
            for w in seg.words:
                words.append({
                    "word": w.word.strip(),
                    "start": float(w.start),
                    "end": float(w.end),
                    "probability": float(w.probability),
                })
        extracted_segments.append({
            "text": seg.text.strip(),
            "start": float(seg.start),
            "end": float(seg.end),
            "words": words,
        })

    logger.success(
        "Transcripción finalizada (Idioma detectado: {}, confianza: {:.2f}, segmentos: {})",
        info.language,
        info.language_probability,
        len(extracted_segments),
    )
    return extracted_segments


def _clean_word(word: str) -> str:
    """Limpia puntuación y normaliza a minúsculas para matching."""
    return re.sub(r"[^\w]", "", word.lower())


def _find_best_silence_cut(target_time: float, silences: List[Tuple[float, float]], window: float = 0.6) -> float:
    """
    Busca si existe un intervalo de silencio cercano al tiempo objetivo.
    Si existe, ajusta el corte al punto medio del silencio.
    """
    for start, end in silences:
        if (start - window) <= target_time <= (end + window):
            # Centrar el corte en el silencio para transición impecable
            return (start + end) / 2.0
    return target_time


def align_scenes(
    scenes: List[Scene],
    whisper_segments: List[Dict[str, Any]],
    silences: List[Tuple[float, float]],
    total_duration: float,
) -> List[Scene]:
    """
    Sincroniza la lista de escenas del guion con los timestamps de Whisper y silencios de pydub.
    Calcula start_time, end_time y duration exactos para cada escena.
    """
    logger.info("Alineando {} escenas con los timestamps del audio...", len(scenes))
    if not scenes:
        return []

    # Extraer todas las palabras con timestamp de Whisper
    all_words = []
    for seg in whisper_segments:
        all_words.extend(seg.get("words", []))

    num_scenes = len(scenes)

    # Si por alguna razón Whisper no detectó palabras, usar división proporcional de seguridad
    if not all_words:
        logger.warning("No se obtuvieron palabras individuales de Whisper. Usando alineación proporcional.")
        total_chars = sum(len(s.narration_text) for s in scenes)
        current_time = 0.0
        for idx, scene in enumerate(scenes):
            ratio = len(scene.narration_text) / max(total_chars, 1)
            duration = ratio * total_duration
            scene.start_time = round(current_time, 3)
            scene.end_time = round(total_duration if idx == num_scenes - 1 else current_time + duration, 3)
            scene.duration = round(scene.end_time - scene.start_time, 3)
            current_time = scene.end_time
        return scenes

    # Alineación por coincidencia secuencial de texto
    word_cursor = 0
    total_whisper_words = len(all_words)
    current_start = 0.0

    for idx, scene in enumerate(scenes):
        scene.start_time = round(current_start, 3)

        if idx == num_scenes - 1:
            # La última escena siempre termina al final del audio
            scene.end_time = round(total_duration, 3)
            scene.duration = round(scene.end_time - scene.start_time, 3)
            break

        # Contar cuántas palabras tiene esta escena
        scene_words = [_clean_word(w) for w in scene.narration_text.split() if _clean_word(w)]
        needed_words = len(scene_words)

        # Avanzar el cursor de palabras proporcional o por coincidencia
        matched_end_time = None
        target_index = min(word_cursor + needed_words - 1, total_whisper_words - 1)

        if target_index >= 0 and target_index < total_whisper_words:
            matched_end_time = all_words[target_index]["end"]
            word_cursor = target_index + 1
        else:
            # Si se excede el cursor, usar extrapolación
            progress_ratio = (idx + 1) / num_scenes
            matched_end_time = progress_ratio * total_duration

        # Ajustar el corte al silencio más cercano si está en el entorno
        snapped_cut = _find_best_silence_cut(matched_end_time, silences)
        
        # Garantizar que el corte sea estrictamente posterior al inicio
        min_allowed = current_start + 1.0  # Al menos 1 segundo por escena
        actual_cut = max(snapped_cut, min_allowed)
        actual_cut = min(actual_cut, total_duration - (num_scenes - idx - 1) * 1.0)

        scene.end_time = round(actual_cut, 3)
        scene.duration = round(scene.end_time - scene.start_time, 3)
        current_start = scene.end_time

    # Verificación de integridad
    for sc in scenes:
        logger.info(
            "Escena #{:02d}: [{:6.2f}s -> {:6.2f}s] (Duración: {:5.2f}s) | '{}...'",
            sc.scene_id,
            sc.start_time or 0.0,
            sc.end_time or 0.0,
            sc.duration or 0.0,
            sc.narration_text[:35],
        )

    return scenes


def align_scene_script_words(
    narration_text: str,
    scene_start: float,
    scene_end: float,
    whisper_words: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Alinea las palabras exactas del guion original con las marcas temporales
    detectadas por Whisper dentro del intervalo de la escena.
    Garantiza que el texto de los subtítulos sea 100% fiel al guion original,
    incluso si Whisper transcribió erróneamente palabras extranjeras o complejas.
    """
    raw_words = narration_text.strip().split()
    if not raw_words:
        return []

    # Normalización para matching léxico tolerante (sin signos ni mayúsculas)
    norm_raw = [re.sub(r"[^\w]", "", w.lower()) for w in raw_words]
    norm_wh = [re.sub(r"[^\w]", "", w.get("word", "").lower()) for w in whisper_words]

    aligned = [{"text": w, "start": None, "end": None} for w in raw_words]

    if whisper_words:
        matcher = difflib.SequenceMatcher(None, norm_raw, norm_wh)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    aligned[i]["start"] = whisper_words[j]["start"]
                    aligned[i]["end"] = whisper_words[j]["end"]
            elif tag == "replace":
                if j2 > j1:
                    span_start = whisper_words[j1]["start"]
                    span_end = whisper_words[j2 - 1]["end"]
                    span_dur = max(0.2, span_end - span_start)
                    n_items = i2 - i1
                    for idx, i in enumerate(range(i1, i2)):
                        aligned[i]["start"] = span_start + (idx / n_items) * span_dur
                        aligned[i]["end"] = span_start + ((idx + 1) / n_items) * span_dur

    # Interpolación robusta para palabras sin timestamp asignado
    last_t = scene_start
    for idx, item in enumerate(aligned):
        if item["start"] is None:
            next_t = scene_end
            for nxt in aligned[idx + 1 :]:
                if nxt["start"] is not None:
                    next_t = nxt["start"]
                    break
            item["start"] = max(last_t, scene_start)
            item["end"] = min(next_t, item["start"] + 0.35)
        if item["end"] < item["start"] + 0.1:
            item["end"] = item["start"] + 0.15
        last_t = item["end"]

    return aligned


def generate_ground_truth_subtitles_srt(
    scenes: List[Scene],
    whisper_segments: List[Dict[str, Any]],
    output_path: Path,
) -> Path:
    """
    Genera subtítulos .srt a partir del GUION ORIGINAL alineado acústicamente con Whisper.
    100% libre de alucinaciones o errores ortográficos de transcripción.
    Respeta mayúsculas, comas, puntos y nombres propios originales.
    """
    logger.info("Generando subtítulos Ground-Truth desde guion original: {}", output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Extraer todas las palabras con timestamp de Whisper
    all_whisper_words = []
    for seg in whisper_segments:
        if seg.get("words"):
            all_whisper_words.extend(seg["words"])

    srt_entries = []
    entry_counter = 1

    for sc in scenes:
        s_start = sc.start_time or 0.0
        s_end = sc.end_time or (s_start + (sc.duration or 5.0))

        # Filtrar palabras de Whisper en la ventana de esta escena (+- 0.8s margen)
        scene_wh_words = [
            w for w in all_whisper_words
            if (s_start - 0.8) <= w.get("start", 0.0) <= (s_end + 0.8)
        ]

        aligned_words = align_scene_script_words(
            narration_text=sc.narration_text,
            scene_start=s_start,
            scene_end=s_end,
            whisper_words=scene_wh_words,
        )

        if not aligned_words:
            continue

        # Agrupar palabras en frases legibles (3-5 palabras, respetando pausas de puntuación)
        chunks = []
        current_chunk = []

        for w_info in aligned_words:
            current_chunk.append(w_info)
            txt = w_info["text"]
            ends_clause = any(txt.endswith(p) for p in [",", ".", ";", ":", "!", "?", "—", "..."])
            if (len(current_chunk) >= 4) or (ends_clause and len(current_chunk) >= 2) or (len(current_chunk) >= 6):
                chunks.append(current_chunk)
                current_chunk = []

        if current_chunk:
            chunks.append(current_chunk)

        # Formatear cada chunk a SRT
        for chunk in chunks:
            c_start = chunk[0]["start"]
            c_end = chunk[-1]["end"]

            # Garantizar al menos 0.8s en pantalla para lectura cómoda
            if c_end - c_start < 0.8:
                c_end = c_start + 0.8

            c_text = " ".join([w["text"] for w in chunk]).strip()
            if not c_text:
                continue

            srt_entries.append(
                f"{entry_counter}\n"
                f"{format_timestamp_srt(c_start)} --> {format_timestamp_srt(c_end)}\n"
                f"{c_text}\n"
            )
            entry_counter += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries))

    logger.success("Subtítulos Ground-Truth .srt exportados exitosamente ({} bloques).", len(srt_entries))
    return output_path


def generate_subtitles_srt(
    whisper_segments: List[Dict[str, Any]],
    output_path: Path,
    scenes: Optional[List[Scene]] = None,
) -> Path:
    """
    Genera el archivo de subtítulos .srt. Si se proporcionan las escenas del guion,
    utiliza alineación Ground-Truth (100% fiel al guion original).
    """
    if scenes:
        return generate_ground_truth_subtitles_srt(scenes, whisper_segments, output_path)

    logger.info("Generando archivo de subtítulos desde Whisper (fallback): {}", output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    srt_entries = []
    entry_counter = 1

    for seg in whisper_segments:
        text = seg["text"].strip()
        words = seg.get("words", [])

        if words and len(words) > 5:
            chunk_size = 4
            for i in range(0, len(words), chunk_size):
                chunk = words[i : i + chunk_size]
                c_start = chunk[0]["start"]
                c_end = chunk[-1]["end"]
                if c_end - c_start < 0.6:
                    c_end = c_start + 0.6
                c_text = " ".join([w["word"] for w in chunk]).strip()

                srt_entries.append(
                    f"{entry_counter}\n"
                    f"{format_timestamp_srt(c_start)} --> {format_timestamp_srt(c_end)}\n"
                    f"{c_text}\n"
                )
                entry_counter += 1
        else:
            srt_entries.append(
                f"{entry_counter}\n"
                f"{format_timestamp_srt(seg['start'])} --> {format_timestamp_srt(seg['end'])}\n"
                f"{text}\n"
            )
            entry_counter += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries))

    logger.success("Subtítulos .srt exportados exitosamente ({} bloques).", len(srt_entries))
    return output_path


def process_audio_and_align(
    audio_path: Path,
    scenes: List[Scene],
    srt_output_path: Path = None,
) -> Tuple[List[Scene], Path]:
    """
    Orquesta la extracción de timestamps, detección de silencios,
    alineación de escenas y generación del archivo de subtítulos Ground-Truth.
    """
    srt_dest = srt_output_path or settings.SUBTITLES_SRT_PATH
    
    total_duration, silences = get_audio_info_and_silences(audio_path)
    whisper_segments = transcribe_audio_with_whisper(audio_path)
    
    aligned_scenes = align_scenes(scenes, whisper_segments, silences, total_duration)
    srt_file = generate_subtitles_srt(whisper_segments, srt_dest, scenes=aligned_scenes)

    return aligned_scenes, srt_file

