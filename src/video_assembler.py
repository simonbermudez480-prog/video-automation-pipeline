"""
Módulo de Montaje y Composición Audiovisual con FFmpeg.
Aplica:
1. Mapeo temporal exacto por escena a partir de los timestamps alineados.
2. Efecto dinámico Ken Burns de ALTO RANGO y VELOCIDAD (claramente perceptible y fluido).
3. Transiciones suaves de fundido cruzado (xfade de 0.5s) entre todas las escenas consecutivas.
4. Sincronización perfecta con la pista de audio de narración original.
5. Quemado de subtítulos con alto contraste y formato legible (WCAG).
6. Exportación en 1080p, 30 FPS.
"""
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from src.config import settings, ROOT_DIR
from src.logger import logger
from src.script_generator import Scene

TRANSITION_DURATION = 0.5  # Duración del fundido cruzado en segundos

# Apertura (FR-17): la mayoría de espectadores decide en el segundo 2
OPENING_DURATION = 1.2   # plano de apertura con acercamiento rápido antes de la escena 1
QUICK_CUT = 0.12         # corte casi seco entre la apertura y la escena 1
HOOK_DURATION = 2.6      # el texto de gancho se ve durante los primeros segundos
QUESTION_DURATION = 3.2  # la pregunta final se ve durante los últimos segundos

# Gradación uniforme por video (FR-13.2): unifica fotos de archivo, stock e IA en un mismo look
ARCHIVAL_ERA_CUTOFF = 1960  # épocas anteriores: look monocromo cálido, como las fotos de archivo
GRADE_FILTERS = {
    "archival": "hue=s=0,colorbalance=rs=0.10:gs=0.04:bs=-0.08:rm=0.08:gm=0.03:bm=-0.06,eq=contrast=1.08",
    "cinematic": "eq=saturation=0.82:contrast=1.05,colorbalance=rs=-0.04:bs=0.05:rh=0.05:bh=-0.04",
}
GRAIN_AND_VIGNETTE = "noise=alls=6:allf=t+u,vignette=PI/5"


def choose_look(visual_contract: Optional[object]) -> str:
    """Elige el look del video según la época del VisualContract."""
    era = getattr(visual_contract, "era_setting", "") or ""
    years = [int(y) for y in re.findall(r"\b(1[0-9]{3}|20[0-9]{2})s?\b", era)]
    return "archival" if years and min(years) < ARCHIVAL_ERA_CUTOFF else "cinematic"


def apply_scene_merges(scenes: List[Scene], image_paths: List[Path], merges: dict[int, int]) -> tuple[List[Scene], List[Path]]:
    """
    Fusiona cada escena sin imagen válida con la escena válida anterior (FR-14.6): la escena se quita del
    montaje y su duración se suma a la anterior, que queda más tiempo en pantalla. La narración no cambia.
    merges: {índice de escena (1-based): índice de la escena que se extiende}.
    """
    kept_scenes: List[Scene] = []
    kept_paths: List[Path] = []
    for idx, (scene, path) in enumerate(zip(scenes, image_paths), start=1):
        if idx in merges and kept_scenes:
            prev = kept_scenes[-1]
            kept_scenes[-1] = prev.model_copy(update={
                "duration": (prev.duration or 6.0) + (scene.duration or 6.0),
                "end_time": scene.end_time,
            })
            continue
        kept_scenes.append(scene)
        kept_paths.append(path)
    return kept_scenes, kept_paths


def _get_dynamic_ken_burns_filter(
    scene_index: int,
    num_frames: int,
    fps: int,
    resolution: str,
    look: Optional[str] = None,
    punch: bool = False,
) -> str:
    """
    Genera la cadena de filtros zoompan de FFmpeg con movimiento CONTINUO y fluido,
    adaptado tanto a formato 16:9 (horizontal) como 9:16 (vertical para Shorts/TikTok).
    punch=True: acercamiento rápido y marcado para el plano de apertura.
    """
    motion_type = scene_index % 5
    safe_frames = max(num_frames, 1)
    is_vertical = "1080x1920" in resolution or resolution == "1080x1920"

    if punch:
        buf_w, buf_h = (1440, 2560) if is_vertical else (2560, 1440)
        # Primer plano cerrado del centro (detalle) que se sigue cerrando; al cortar a la escena 1 el cambio se nota
        zoom_expr = f"1.70+0.20*(on/{safe_frames})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif is_vertical:
        buf_w, buf_h = 1440, 2560
        if motion_type == 0:
            # Zoom In vertical centrado
            zoom_expr = f"1.0+0.25*(on/{safe_frames})"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif motion_type == 1:
            # Zoom Out vertical suave
            zoom_expr = f"1.25-0.25*(on/{safe_frames})"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif motion_type == 2:
            # Paneo vertical fluido de Arriba hacia Abajo (Tilt Down)
            zoom_expr = f"1.15+0.05*(on/{safe_frames})"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = f"(on/{safe_frames})*(ih-ih/zoom)"
        elif motion_type == 3:
            # Paneo vertical fluido de Abajo hacia Arriba (Tilt Up)
            zoom_expr = f"1.15+0.05*(on/{safe_frames})"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = f"(1.0-(on/{safe_frames}))*(ih-ih/zoom)"
        else:
            # Zoom In con paneo diagonal
            zoom_expr = f"1.08+0.18*(on/{safe_frames})"
            x_expr = f"(on/{safe_frames})*(iw/2-(iw/zoom/2))"
            y_expr = f"(on/{safe_frames})*(ih/2-(ih/zoom/2))"
    else:
        buf_w, buf_h = 2560, 1440
        if motion_type == 0:
            # Zoom In horizontal hacia el centro
            zoom_expr = f"1.0+0.28*(on/{safe_frames})"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif motion_type == 1:
            # Zoom Out horizontal hacia afuera
            zoom_expr = f"1.28-0.28*(on/{safe_frames})"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif motion_type == 2:
            # Paneo horizontal de Izquierda a Derecha
            zoom_expr = f"1.18+0.08*(on/{safe_frames})"
            x_expr = f"(on/{safe_frames})*(iw-iw/zoom)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif motion_type == 3:
            # Paneo horizontal de Derecha a Izquierda
            zoom_expr = f"1.18+0.08*(on/{safe_frames})"
            x_expr = f"(1.0-(on/{safe_frames}))*(iw-iw/zoom)"
            y_expr = "ih/2-(ih/zoom/2)"
        else:
            # Paneo diagonal hacia el centro
            zoom_expr = f"1.08+0.20*(on/{safe_frames})"
            x_expr = f"(on/{safe_frames})*(iw/2-(iw/zoom/2))"
            y_expr = f"(on/{safe_frames})*(ih/2-(ih/zoom/2))"

    filter_graph = (
        f"scale={buf_w}:{buf_h}:force_original_aspect_ratio=increase,"
        f"crop={buf_w}:{buf_h},"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={num_frames}:s={resolution}:fps={fps},"
        + (f"{GRADE_FILTERS[look]},{GRAIN_AND_VIGNETTE}," if look else "")
        + "format=yuv420p"
    )
    return filter_graph



def render_scene_clip(
    image_path: Path,
    duration: float,
    output_clip_path: Path,
    scene_index: int,
    fps: int = 30,
    resolution: str = "1920x1080",
    threads: int = 2,
    look: Optional[str] = None,
    punch: bool = False,
) -> Path:
    """
    Renderiza un clip de video individual para una escena con efecto Ken Burns continuo.
    Usa preset ultrafast y CRF 16 para máxima velocidad con calidad visual impecable para el ensamble.
    """
    output_clip_path.parent.mkdir(parents=True, exist_ok=True)
    num_frames = max(round(duration * fps), fps)

    filter_graph = _get_dynamic_ken_burns_filter(scene_index, num_frames, fps, resolution, look=look, punch=punch)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(image_path),
        "-vf", filter_graph,
        "-frames:v", str(num_frames),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "16",
        "-threads", str(threads),
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        str(output_clip_path),
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logger.error("FFmpeg error al renderizar clip {}:\n{}", output_clip_path.name, result.stderr[-500:])
        raise RuntimeError(f"Error renderizando clip de escena: {output_clip_path.name}")

    return output_clip_path


def _ass_time(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    return f"{int(seconds // 3600)}:{int(seconds % 3600 // 60):02d}:{seconds % 60:05.2f}"


def _ass_text(text: str) -> str:
    return " ".join((text or "").replace("{", "(").replace("}", ")").replace("\\", "").split())


def write_overlay_ass(path: Path, hook_text: Optional[str], closing_question: Optional[str], total_duration: float, is_vertical: bool) -> Optional[Path]:
    """
    Crea un archivo ASS con el texto de gancho (inicio) y la pregunta final (cierre) en el tercio superior,
    lejos de los subtítulos (abajo) y de los botones de TikTok/Reels/Shorts (derecha y parte superior).
    """
    if not (hook_text or closing_question):
        return None
    play_x, play_y = (1080, 1920) if is_vertical else (1920, 1080)
    size, margin_v, margin_h = (74, 270, 130) if is_vertical else (64, 90, 200)
    # BorderStyle=3: caja casi opaca detrás del texto para contraste alto sobre cualquier imagen
    header = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {play_x}\nPlayResY: {play_y}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Hook,Arial,{size},&H00FFFFFF,&H00FFFFFF,&H26000000,&H26000000,-1,0,0,0,100,100,0,0,3,16,0,8,{margin_h},{margin_h},{margin_v},1\n"
        f"Style: Question,Arial,{size},&H0000D7FF,&H0000D7FF,&H26000000,&H26000000,-1,0,0,0,100,100,0,0,3,16,0,8,{margin_h},{margin_h},{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    if hook_text:
        events.append(f"Dialogue: 0,{_ass_time(0)},{_ass_time(HOOK_DURATION)},Hook,,0,0,0,,{{\\fad(0,200)}}{_ass_text(hook_text)}")
    if closing_question:
        start = max(total_duration - QUESTION_DURATION, HOOK_DURATION + 1.0)
        events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(total_duration + 2)},Question,,0,0,0,,{{\\fad(200,0)}}{_ass_text(closing_question)}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return path


def _ffmpeg_filter_path(path: Path) -> str:
    """Ruta para filtros de FFmpeg (subtitles/ass): relativa al proyecto si se puede, para evitar escapar 'C:'."""
    try:
        return path.resolve().relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return path.resolve().as_posix().replace(":", r"\:")


def assemble_video(
    scenes: List[Scene],
    image_paths: List[Path],
    audio_path: Path,
    subtitles_path: Optional[Path] = None,
    output_video_path: Optional[Path] = None,
    burn_subtitles: bool = True,
    aspect_ratio: str = "16:9",
    temp_dir: Optional[Path] = None,
    look: Optional[str] = None,
    hook_text: Optional[str] = None,
    closing_question: Optional[str] = None,
    opening_image: Optional[Path] = None,
    quick_open: bool = True,
) -> Path:
    """
    Ensambla el video final aplicando:
    1. Renderizado paralelo de clips individuales con Ken Burns dinámico (16:9 o 9:16 vertical).
    2. Apertura rápida (FR-17): ~1,2 s de acercamiento marcado (con opening_image, la imagen de mayor impacto)
       y corte casi seco a la escena 1; luego fundidos de 0,5 s entre escenas.
    3. Mapeo y mezcla con la pista de audio original.
    4. Quemado de subtítulos con alto contraste visual (WCAG AAA) y zona segura móvil en 9:16.
    5. Texto de gancho al inicio y pregunta final al cierre, en el tercio superior.
    6. Exportación multi-hilo acelerada a 1080p, 30 FPS.
    """
    final_output = output_video_path or settings.FINAL_VIDEO_PATH
    final_output.parent.mkdir(parents=True, exist_ok=True)
    working_temp_dir = temp_dir or settings.TEMP_DIR
    working_temp_dir.mkdir(parents=True, exist_ok=True)

    fps = settings.OUTPUT_FPS
    is_vertical = aspect_ratio == "9:16"
    resolution = "1080x1920" if is_vertical else "1920x1080"
    clip_workers = getattr(settings, "CONCURRENT_CLIP_WORKERS", 2)
    ffmpeg_preset = getattr(settings, "FFMPEG_PRESET", "veryfast")
    ffmpeg_crf = getattr(settings, "FFMPEG_CRF", "19")

    total_scenes = len(scenes)
    logger.info(
        "Iniciando montaje audiovisual optimizado de {} escenas (Formato: {}, Workers: {}, Preset: {}, CRF: {}, {} @ {}fps)...",
        total_scenes,
        aspect_ratio,
        clip_workers,
        ffmpeg_preset,
        ffmpeg_crf,
        resolution,
        fps,
    )

    if len(image_paths) < total_scenes:
        raise ValueError(f"Se requieren {total_scenes} imágenes pero solo hay {len(image_paths)}")

    # Plan de planos: (imagen, duración, índice de movimiento, ¿acercamiento rápido?) y fundido hacia el plano siguiente
    shots = [(img, scene.duration or 6.0, idx, False) for idx, (scene, img) in enumerate(zip(scenes, image_paths), start=1)]
    transitions = [TRANSITION_DURATION] * max(len(shots) - 1, 0)
    if quick_open and shots and shots[0][1] > OPENING_DURATION + 1.5:
        first_img, first_dur, first_idx, _ = shots[0]
        shots[0] = (first_img, first_dur - OPENING_DURATION, first_idx, False)
        shots.insert(0, (opening_image or first_img, OPENING_DURATION, 0, True))
        transitions.insert(0, QUICK_CUT)
        logger.info("Apertura rápida: {:.1f}s con {} y corte a la escena 1.", OPENING_DURATION,
                    "la imagen de mayor impacto" if opening_image else "un acercamiento a la escena 1")
    total_scenes = len(shots)
    total_duration = sum(s[1] for s in shots)

    # 1. Preparar lista de clips individuales a renderizar
    clip_render_tasks = []
    for idx, (img_path, base_duration, motion_idx, punch) in enumerate(shots, start=1):
        # Cada fundido empieza antes del cambio de plano, así que cada clip (también el último) se adelanta
        # y necesita durar TRANSITION_DURATION de más para terminar junto con la narración.
        render_duration = base_duration + TRANSITION_DURATION
        clip_path = working_temp_dir / f"clip_{idx:03d}.mp4"
        clip_render_tasks.append((idx, motion_idx, punch, img_path, base_duration, render_duration, clip_path))

    # Renderizado paralelo de clips con ThreadPoolExecutor
    logger.info("Renderizando clips dinámicos concurrentemente con {} workers...", clip_workers)
    clip_paths_dict = {}

    def _render_worker(task):
        idx, motion_idx, punch, img_path, base_dur, r_dur, clip_path = task
        logger.info(
            "[{}/{}] Renderizando clip {} (Duración base: {:.2f}s, Render: {:.2f}s)...",
            idx,
            total_scenes,
            "de apertura" if punch else f"Escena #{motion_idx:02d}",
            base_dur,
            r_dur,
        )
        render_scene_clip(img_path, r_dur, clip_path, motion_idx, fps, resolution, threads=2, look=look, punch=punch)
        return idx, clip_path

    with ThreadPoolExecutor(max_workers=clip_workers) as executor:
        futures = [executor.submit(_render_worker, task) for task in clip_render_tasks]
        for future in as_completed(futures):
            idx_done, path_done = future.result()
            clip_paths_dict[idx_done] = path_done

    clip_paths = [clip_paths_dict[i] for i in range(1, total_scenes + 1)]

    # 2. Construcción de comando FFmpeg con cadena de xfade
    logger.info("Construyendo grafo de transiciones xfade entre las {} escenas...", total_scenes)

    cmd = ["ffmpeg", "-y"]
    for clip in clip_paths:
        cmd.extend(["-i", str(clip)])

    audio_input_idx = len(clip_paths)
    cmd.extend(["-i", str(audio_path)])

    filter_complex_steps = []
    last_v = "0:v"
    cumulative_offset = 0.0

    if total_scenes > 1:
        for i in range(1, total_scenes):
            cumulative_offset += shots[i - 1][1]
            trans = transitions[i - 1]
            offset = max(0.1, round(cumulative_offset - trans, 3))
            out_v = f"v{i}"
            filter_complex_steps.append(
                f"[{last_v}][{i}:v]xfade=transition=fade:duration={trans:.2f}:offset={offset:.3f}[{out_v}]"
            )
            last_v = out_v
    else:
        last_v = "0:v"

    # 3. Quemado de subtítulos con alto contraste y zona segura según aspect ratio
    final_video_label = last_v
    if burn_subtitles and subtitles_path and subtitles_path.exists():
        rel_srt = _ffmpeg_filter_path(subtitles_path)

        if is_vertical:
            sub_play_res_x = 1080
            sub_play_res_y = 1920
            sub_margin_v = 360  # Zona segura para Shorts/TikTok/Reels en 1080x1920
            sub_font_size = 54
            sub_outline = 4.0
            sub_shadow = 2.0
        else:
            sub_play_res_x = 1920
            sub_play_res_y = 1080
            sub_margin_v = 70
            sub_font_size = 48
            sub_outline = 3.5
            sub_shadow = 2.0

        sub_filter = (
            f"subtitles='{rel_srt}':force_style="
            f"'PlayResX={sub_play_res_x},PlayResY={sub_play_res_y},"
            f"FontName=Arial,FontSize={sub_font_size},Bold=1,PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=3,"
            f"Outline={sub_outline},Shadow={sub_shadow},Alignment=2,MarginV={sub_margin_v}'"
        )
        filter_complex_steps.append(f"[{last_v}]{sub_filter}[vout]")
        final_video_label = "vout"
        logger.info("Añadiendo filtro de subtítulos de alto contraste ({}, PlayResY={}, MarginV={}): {}", aspect_ratio, sub_play_res_y, sub_margin_v, sub_filter[:75])

    # 4. Texto de gancho (inicio) y pregunta final (cierre) en el tercio superior
    overlay = write_overlay_ass(working_temp_dir / "overlay_texts.ass", hook_text, closing_question, total_duration, is_vertical)
    if overlay:
        filter_complex_steps.append(f"[{final_video_label}]ass='{_ffmpeg_filter_path(overlay)}'[vtext]")
        final_video_label = "vtext"
        logger.info("Texto en pantalla: gancho={!r} | pregunta final={!r}", hook_text, closing_question)

    # Red de seguridad: congelar el último frame para que el video nunca sea más corto que la narración;
    # -shortest recorta después al largo exacto del audio.
    pad_input = final_video_label if filter_complex_steps else "0:v"
    filter_complex_steps.append(f"[{pad_input}]tpad=stop_mode=clone:stop_duration=2[vfinal]")
    cmd.extend(["-filter_complex", "; ".join(filter_complex_steps)])
    cmd.extend(["-map", "[vfinal]"])

    # Mapear el audio de narración
    cmd.extend(["-map", f"{audio_input_idx}:a"])

    # Parámetros de codificación multi-hilo acelerada en 1080p @ 30 FPS
    cmd.extend([
        "-c:v", "libx264",
        "-preset", ffmpeg_preset,
        "-crf", ffmpeg_crf,
        "-threads", "4",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(final_output),
    ])

    logger.info("Ejecutando ensamble final multi-hilo con FFmpeg (Preset: {})...", ffmpeg_preset)
    result = subprocess.run(cmd, cwd=str(ROOT_DIR), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logger.error("FFmpeg error al ensamblar video final:\n{}", result.stderr[-800:])
        raise RuntimeError("Fallo durante el ensamble final del video con FFmpeg.")

    file_size_mb = final_output.stat().st_size / (1024 * 1024)
    logger.success("Video final producido exitosamente: {} ({:.2f} MB)", final_output, file_size_mb)
    _remove_render_temps(working_temp_dir)
    return final_output


def _remove_render_temps(temp_dir: Path) -> None:
    """Borra los clips intermedios (~800 MB por video, FR-19.1); un nuevo montaje los vuelve a generar."""
    freed = 0
    for item in [*temp_dir.glob("clip_*.mp4"), temp_dir / "overlay_texts.ass"]:
        try:
            if item.exists():
                freed += item.stat().st_size
                item.unlink()
        except OSError as e:
            logger.warning("No se pudo borrar el temporal {}: {}", item.name, e)
    logger.info("Temporales de montaje borrados ({:.0f} MB liberados).", freed / 1024 ** 2)
