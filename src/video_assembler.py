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
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from src.config import settings, ROOT_DIR
from src.logger import logger
from src.script_generator import Scene

TRANSITION_DURATION = 0.5  # Duración del fundido cruzado en segundos


def _get_dynamic_ken_burns_filter(
    scene_index: int,
    num_frames: int,
    fps: int,
    resolution: str,
) -> str:
    """
    Genera la cadena de filtros zoompan de FFmpeg con movimiento CONTINUO y fluido,
    garantizando que la cámara se mueva desde el fotograma 1 hasta el último sin congelarse.
    """
    motion_type = scene_index % 5
    safe_frames = max(num_frames, 1)

    if motion_type == 0:
        # Zoom In fluido y progresivo hacia el centro (de 1.0x hasta 1.28x)
        zoom_expr = f"1.0+0.28*(on/{safe_frames})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion_type == 1:
        # Zoom Out suave y dramático (de 1.28x retrocediendo hacia 1.0x)
        zoom_expr = f"1.28-0.28*(on/{safe_frames})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion_type == 2:
        # Paneo horizontal fluido de Izquierda a Derecha con ligero zoom de profundidad
        zoom_expr = f"1.18+0.08*(on/{safe_frames})"
        x_expr = f"(on/{safe_frames})*(iw-iw/zoom)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion_type == 3:
        # Paneo horizontal fluido de Derecha a Izquierda
        zoom_expr = f"1.18+0.08*(on/{safe_frames})"
        x_expr = f"(1.0-(on/{safe_frames}))*(iw-iw/zoom)"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        # Paneo diagonal cinematográfico suave hacia el centro
        zoom_expr = f"1.08+0.20*(on/{safe_frames})"
        x_expr = f"(on/{safe_frames})*(iw/2-(iw/zoom/2))"
        y_expr = f"(on/{safe_frames})*(ih/2-(ih/zoom/2))"

    # Pre-escalar a 2560x1440 (2.5K): ofrece nitidez perfecta y elimina 56% del costo de CPU frente a 4K
    filter_graph = (
        f"scale=2560:1440:force_original_aspect_ratio=increase,"
        f"crop=2560:1440,"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={num_frames}:s={resolution}:fps={fps},"
        f"format=yuv420p"
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
) -> Path:
    """
    Renderiza un clip de video individual para una escena con efecto Ken Burns continuo.
    Usa preset ultrafast y CRF 16 para máxima velocidad con calidad visual impecable para el ensamble.
    """
    output_clip_path.parent.mkdir(parents=True, exist_ok=True)
    num_frames = max(int(duration * fps), fps)

    filter_graph = _get_dynamic_ken_burns_filter(scene_index, num_frames, fps, resolution)

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


def assemble_video(
    scenes: List[Scene],
    image_paths: List[Path],
    audio_path: Path,
    subtitles_path: Optional[Path] = None,
    output_video_path: Optional[Path] = None,
    burn_subtitles: bool = True,
) -> Path:
    """
    Ensambla el video final aplicando:
    1. Renderizado paralelo de clips individuales con Ken Burns dinámico y continuo.
    2. Transición suave de fundido cruzado (xfade de 0.5s) entre cada escena.
    3. Mapeo y mezcla con la pista de audio original.
    4. Quemado de subtítulos con alto contraste visual (WCAG AAA).
    5. Exportación multi-hilo acelerada a 1080p, 30 FPS en output/video_final.mp4.
    """
    final_output = output_video_path or settings.FINAL_VIDEO_PATH
    final_output.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = settings.TEMP_DIR
    temp_dir.mkdir(parents=True, exist_ok=True)

    fps = settings.OUTPUT_FPS
    resolution = settings.OUTPUT_RESOLUTION
    clip_workers = getattr(settings, "CONCURRENT_CLIP_WORKERS", 2)
    ffmpeg_preset = getattr(settings, "FFMPEG_PRESET", "veryfast")
    ffmpeg_crf = getattr(settings, "FFMPEG_CRF", "19")

    total_scenes = len(scenes)
    logger.info(
        "Iniciando montaje audiovisual optimizado de {} escenas (Workers: {}, Preset: {}, CRF: {}, {} @ {}fps)...",
        total_scenes,
        clip_workers,
        ffmpeg_preset,
        ffmpeg_crf,
        resolution,
        fps,
    )

    if len(image_paths) < total_scenes:
        raise ValueError(f"Se requieren {total_scenes} imágenes pero solo hay {len(image_paths)}")

    # 1. Preparar lista de clips individuales a renderizar
    clip_render_tasks = []
    for idx, (scene, img_path) in enumerate(zip(scenes, image_paths), start=1):
        base_duration = scene.duration or 6.0
        render_duration = base_duration + (TRANSITION_DURATION if idx < total_scenes else 0.0)
        clip_path = temp_dir / f"clip_{idx:03d}.mp4"
        clip_render_tasks.append((idx, scene, img_path, render_duration, clip_path))

    # Renderizado paralelo de clips con ThreadPoolExecutor
    logger.info("Renderizando clips dinámicos concurrentemente con {} workers...", clip_workers)
    clip_paths_dict = {}

    def _render_worker(task):
        idx, scene, img_path, r_dur, clip_path = task
        logger.info(
            "[{}/{}] Renderizando clip Escena #{:02d} (Duración base: {:.2f}s, Render: {:.2f}s)...",
            idx,
            total_scenes,
            scene.scene_id,
            scene.duration or 6.0,
            r_dur,
        )
        render_scene_clip(img_path, r_dur, clip_path, idx, fps, resolution, threads=2)
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
            scene_duration = scenes[i - 1].duration or 6.0
            cumulative_offset += scene_duration
            offset = max(0.1, round(cumulative_offset - TRANSITION_DURATION, 3))
            out_v = f"v{i}"
            filter_complex_steps.append(
                f"[{last_v}][{i}:v]xfade=transition=fade:duration={TRANSITION_DURATION:.1f}:offset={offset:.3f}[{out_v}]"
            )
            last_v = out_v
    else:
        last_v = "0:v"

    # 3. Quemado de subtítulos con alto contraste
    final_video_label = last_v
    if burn_subtitles and subtitles_path and subtitles_path.exists():
        try:
            rel_srt = subtitles_path.resolve().relative_to(ROOT_DIR).as_posix()
        except ValueError:
            rel_srt = subtitles_path.resolve().as_posix().replace(":", r"\:")

        sub_filter = (
            f"subtitles='{rel_srt}':force_style="
            f"'FontName=Arial,FontSize=22,Bold=1,PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=3,Outline=2.0,Shadow=1.0,Alignment=2,MarginV=38'"
        )
        filter_complex_steps.append(f"[{last_v}]{sub_filter}[vout]")
        final_video_label = "vout"
        logger.info("Añadiendo filtro de subtítulos de alto contraste: {}", sub_filter[:65])

    filter_complex_str = "; ".join(filter_complex_steps)
    if filter_complex_str:
        cmd.extend(["-filter_complex", filter_complex_str])
        cmd.extend(["-map", f"[{final_video_label}]"])
    else:
        cmd.extend(["-map", "0:v"])

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
    return final_output
