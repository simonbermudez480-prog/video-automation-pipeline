"""
Pipeline de Automatización Multimedia 100% Autónomo.
Ejecución individual: python main.py --topic "Tema del video" --aspect-ratio 9:16 --publish-all
Ejecución en lote (Batch): python main.py --topic "Tema 1" "Tema 2" "Tema 3" --aspect-ratio 9:16 --publish-all
O vía archivo: python main.py --topics-file temas.txt --aspect-ratio 9:16 --publish-all

Formatos soportados:
- 9:16 (1080x1920) Vertical: Optimizado para YouTube Shorts, Instagram Reels y TikTok con área segura de subtítulos.
- 16:9 (1920x1080) Horizontal: Documental cinematográfico panorámico.

Flujo de producción:
Idea/Tema -> Guion estructurado -> Síntesis de voz bilingüe -> Timestamps & Subtítulos Ground-Truth ->
Imágenes generativas/documentales -> Montaje audiovisual Ken Burns -> Acumulación sin sobreescritura en output/ ->
Copies y Hashtags con IA -> Publicación y empaquetado Multi-Plataforma (Shorts, Reels, TikTok)
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sys
import time
import unicodedata
from typing import List, Optional

from src.config import settings, ROOT_DIR, ASSETS_DIR, IMAGES_DIR, AUDIO_DIR, SUBTITLES_DIR, TEMP_DIR, OUTPUT_DIR
from src.logger import logger
from src.script_generator import generate_script, save_script_to_disk, ScriptOutput
from src.voice_synthesizer import synthesize_voice
from src.audio_processor import process_audio_and_align
from src.image_generator import generate_images_for_scenes
from src.video_assembler import assemble_video
from src.youtube_uploader import upload_video_to_youtube
from src.social_copywriter import generate_social_copy, SocialBundle
from src.multiplatform_publisher import publish_video_multiplatform


def slugify(text: str, max_length: int = 35) -> str:
    """Convierte un texto o tema a un slug limpio para nombres de archivo."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w\s-]", "", normalized).strip().lower()
    slug = re.sub(r"[-\s]+", "_", cleaned)
    return slug[:max_length].rstrip("_") or "video"


def clean_temp_workspace(clean_images: bool = True, clean_audio: bool = False, clean_jobs: bool = False) -> None:
    """Limpia archivos temporales de renderizado previo y opcionalmente imágenes y audio anteriores."""
    logger.info("Limpiando directorios de trabajo temporales...")
    dirs_to_clean = [TEMP_DIR]
    if clean_images:
        dirs_to_clean.append(IMAGES_DIR)
    if clean_audio:
        dirs_to_clean.extend([AUDIO_DIR, SUBTITLES_DIR])
    if clean_jobs:
        jobs_dir = ASSETS_DIR / "jobs"
        if jobs_dir.exists():
            dirs_to_clean.append(jobs_dir)

    for target_dir in dirs_to_clean:
        if target_dir.exists():
            for item in target_dir.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                except Exception as e:
                    logger.warning("No se pudo eliminar {}: {}", item.name, e)


def extract_topics(args: argparse.Namespace) -> List[str]:
    """Extrae y normaliza la lista de temas desde --topic y/o --topics-file."""
    raw_topics = []

    # 1. Leer desde archivo de temas si fue provisto
    if getattr(args, "topics_file", None):
        t_file = Path(args.topics_file)
        if t_file.exists():
            with open(t_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        raw_topics.append(line)
            logger.info("Cargados {} temas desde archivo: {}", len(raw_topics), t_file.name)
        else:
            logger.warning("El archivo de temas especificado no existe: {}", t_file)

    # 2. Leer desde argumento --topic (lista de cadenas o separadas por comas)
    if getattr(args, "topic", None):
        topic_arg = args.topic
        if isinstance(topic_arg, list):
            for item in topic_arg:
                parts = [p.strip() for p in item.split(",") if p.strip()]
                raw_topics.extend(parts)
        elif isinstance(topic_arg, str):
            parts = [p.strip() for p in topic_arg.split(",") if p.strip()]
            raw_topics.extend(parts)

    # 3. Eliminar duplicados manteniendo orden de inserción
    unique_topics = []
    for t in raw_topics:
        if t not in unique_topics:
            unique_topics.append(t)

    if not unique_topics:
        unique_topics = ["La teoria de la muerte y el multiverso"]

    return unique_topics


def execute_single_video_job(topic: str, args: argparse.Namespace, job_index: int, total_jobs: int) -> Path:
    """Ejecuta el ciclo de vida completo de creación para un video individual en su propio entorno aislado."""
    start_time = time.time()
    aspect_ratio = args.aspect_ratio or settings.DEFAULT_ASPECT_RATIO
    ratio_tag = "9x16" if aspect_ratio == "9:16" else "16x9"
    slug = slugify(topic)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Carpeta aislada para assets de este trabajo
    jobs_root = ASSETS_DIR / "jobs"
    job_dir = jobs_root / f"{slug}_{ratio_tag}_{timestamp}"
    job_audio_dir = job_dir / "audio"
    job_subtitles_dir = job_dir / "subtitles"
    job_images_dir = job_dir / "images"
    job_temp_dir = job_dir / "temp"

    for d in [job_dir, job_audio_dir, job_subtitles_dir, job_images_dir, job_temp_dir]:
        d.mkdir(parents=True, exist_ok=True)

    job_script_path = job_dir / "script.json"
    job_aligned_path = job_dir / "aligned_scenes.json"
    job_audio_path = job_audio_dir / "narration.mp3"
    job_subtitles_path = job_subtitles_dir / "subtitles.srt"

    # Definir nombre de salida único en la carpeta output/
    output_dir = Path(args.output_dir) if getattr(args, "output_dir", None) else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    if getattr(args, "output_name", None) and total_jobs == 1:
        out_filename = args.output_name if args.output_name.endswith(".mp4") else f"{args.output_name}.mp4"
    else:
        out_filename = f"{slug}_{ratio_tag}_{timestamp}.mp4"

    target_video_path = output_dir / out_filename

    width, height = settings.get_dimensions(aspect_ratio)
    logger.info("=" * 70)
    logger.info("INICIANDO PRODUCCIÓN [{}/{}]: '{}'", job_index, total_jobs, topic)
    logger.info("Formato: {} ({}x{}) | Archivo Destino: {}", aspect_ratio, width, height, target_video_path.name)
    logger.info("Espacio de trabajo aislado: {}", job_dir.name)
    logger.info("=" * 70)

    # -------------------------------------------------------------
    # PASO 1: Generación de Guion y Prompts Visuales
    # -------------------------------------------------------------
    script_data: ScriptOutput
    if not args.skip_script:
        logger.info("\n>>> [{}/{}] [PASO 1/6] Generando guion estructurado y prompts visuales ({:.1f} min, {})...", job_index, total_jobs, args.duration_minutes, aspect_ratio)
        script_data = generate_script(
            topic=topic,
            duration_minutes=args.duration_minutes,
            target_words=args.target_words,
            provider=args.llm_provider,
            aspect_ratio=aspect_ratio,
        )
        save_script_to_disk(script_data, target_path=job_script_path)
        try:
            save_script_to_disk(script_data, target_path=settings.SCRIPT_JSON_PATH)
        except Exception:
            pass
    else:
        logger.info("\n>>> [{}/{}] [PASO 1/6] Omitido: Cargando guion existente desde: {}", job_index, total_jobs, settings.SCRIPT_JSON_PATH)
        if not settings.SCRIPT_JSON_PATH.exists():
            raise FileNotFoundError(f"No existe guion previo en: {settings.SCRIPT_JSON_PATH}")
        with open(settings.SCRIPT_JSON_PATH, "r", encoding="utf-8") as f:
            script_data = ScriptOutput.model_validate_json(f.read())

    logger.info("Título: {}", script_data.metadata.title)
    logger.info("Número de escenas definidas: {}", len(script_data.scenes))

    # -------------------------------------------------------------
    # PASO 2: Síntesis de Voz (TTS)
    # -------------------------------------------------------------
    narration_audio = job_audio_path
    if not args.skip_audio:
        logger.info("\n>>> [{}/{}] [PASO 2/6] Sintetizando locución de voz con pausas y pronunciación natural...", job_index, total_jobs)
        narration_audio = synthesize_voice(
            text=script_data.narration_full,
            output_path=job_audio_path,
            provider=args.tts_provider,
        )
        try:
            shutil.copy2(narration_audio, settings.NARRATION_AUDIO_PATH)
        except Exception:
            pass
    else:
        narration_audio = settings.NARRATION_AUDIO_PATH
        logger.info("\n>>> [{}/{}] [PASO 2/6] Omitido: Usando audio existente: {}", job_index, total_jobs, narration_audio)
        if not narration_audio.exists():
            raise FileNotFoundError(f"No se encontró audio de narración en: {narration_audio}")

    # -------------------------------------------------------------
    # PASO 3: Detección de Pausas, Timestamps y Subtítulos Ground-Truth
    # -------------------------------------------------------------
    subtitles_file = job_subtitles_path
    if not args.skip_alignment:
        logger.info("\n>>> [{}/{}] [PASO 3/6] Alineando timestamps con faster-whisper y generando subtítulos Ground-Truth...", job_index, total_jobs)
        script_data.scenes, subtitles_file = process_audio_and_align(
            audio_path=narration_audio,
            scenes=script_data.scenes,
            srt_output_path=job_subtitles_path,
        )
        save_script_to_disk(script_data, target_path=job_aligned_path)
        try:
            shutil.copy2(subtitles_file, settings.SUBTITLES_SRT_PATH)
            save_script_to_disk(script_data, target_path=settings.ALIGNED_SCENES_PATH)
        except Exception:
            pass
    else:
        logger.info("\n>>> [{}/{}] [PASO 3/6] Omitido: Usando subtítulos existentes.")
        subtitles_file = settings.SUBTITLES_SRT_PATH

    # -------------------------------------------------------------
    # PASO 4: Generación de Imágenes Coherentes (9:16 o 16:9)
    # -------------------------------------------------------------
    image_paths = []
    if not args.skip_images:
        logger.info("\n>>> [{}/{}] [PASO 4/6] Generando imágenes {} secuenciales para cada escena...", job_index, total_jobs, aspect_ratio)
        image_paths = generate_images_for_scenes(
            scenes=script_data.scenes,
            output_dir=job_images_dir,
            provider=args.image_provider,
            topic=topic,
            aspect_ratio=aspect_ratio,
        )
        for img in image_paths:
            try:
                shutil.copy2(img, settings.IMAGES_DIR / img.name)
            except Exception:
                pass
    else:
        logger.info("\n>>> [{}/{}] [PASO 4/6] Omitido: Cargando imágenes de: {}", job_index, total_jobs, settings.IMAGES_DIR)
        for idx in range(1, len(script_data.scenes) + 1):
            p = settings.IMAGES_DIR / f"scene_{idx:03d}.png"
            if not p.exists():
                raise FileNotFoundError(f"Falta la imagen requerida: {p}")
            image_paths.append(p)

    # -------------------------------------------------------------
    # PASO 5: Montaje Audiovisual con Efecto Dinámico (FFmpeg)
    # -------------------------------------------------------------
    final_video = target_video_path
    if not args.skip_video:
        logger.info("\n>>> [{}/{}] [PASO 5/6] Ensamblando video {} con Ken Burns y subtítulos quemados en zona segura...", job_index, total_jobs, aspect_ratio)
        final_video = assemble_video(
            scenes=script_data.scenes,
            image_paths=image_paths,
            audio_path=narration_audio,
            subtitles_path=subtitles_file,
            output_video_path=target_video_path,
            burn_subtitles=not args.no_subtitles,
            aspect_ratio=aspect_ratio,
            temp_dir=job_temp_dir,
        )
        # Sincronizar copia con video_final.mp4 para conveniencia
        try:
            shutil.copy2(final_video, settings.FINAL_VIDEO_PATH)
        except Exception:
            pass
    else:
        logger.info("\n>>> [{}/{}] [PASO 5/6] Omitido: Montaje de video saltado por usuario.")

    # -------------------------------------------------------------
    # PASO 6: Copys con IA y Publicación Multi-Plataforma (Shorts, Reels, TikTok)
    # -------------------------------------------------------------
    platforms_to_publish: List[str] = []
    if getattr(args, "publish_all", False) or getattr(args, "publish", False):
        platforms_to_publish = ["youtube", "instagram", "tiktok"]
    elif getattr(args, "publish_platforms", None):
        platforms_to_publish = [p.lower() for p in args.publish_platforms]
    elif getattr(args, "upload", False):
        platforms_to_publish = ["youtube"]

    create_social_pack = not getattr(args, "no_social_pack", False)

    if final_video.exists() and (create_social_pack or platforms_to_publish):
        logger.info(
            "\n>>> [{}/{}] [PASO 6/6] Redactando copies optimizados con IA y organizando distribución multi-plataforma...",
            job_index,
            total_jobs,
        )
        try:
            est_seconds = (args.duration_minutes or 1.0) * 60.0
            social_bundle = generate_social_copy(
                topic=topic,
                narration_summary=script_data.narration_full,
                duration_seconds=est_seconds,
                provider=args.llm_provider,
            )
            logger.info("Copies listos: Título YouTube = '{}'", social_bundle.youtube_shorts.title)

            pub_results = publish_video_multiplatform(
                video_path=final_video,
                bundle=social_bundle,
                platforms=platforms_to_publish,
                create_package=create_social_pack,
                privacy=args.privacy,
            )
            if "youtube" in pub_results and pub_results["youtube"].get("url"):
                logger.success("Video disponible en YouTube: {}", pub_results["youtube"]["url"])
        except Exception as e:
            logger.error("Error durante la generación de copies o publicación social: {}", e)
    else:
        logger.info(
            "\n>>> [{}/{}] [PASO 6/6] Publicación social omitida (usa --publish-all o --publish para publicar en Shorts, Reels y TikTok).",
            job_index,
            total_jobs,
        )

    job_elapsed = time.time() - start_time
    file_size_mb = final_video.stat().st_size / (1024 * 1024) if final_video.exists() else 0.0
    logger.success(
        "VIDEO [{}/{}] FINALIZADO CON ÉXITO EN {:.2f}s | Salida: {} ({:.2f} MB)",
        job_index,
        total_jobs,
        job_elapsed,
        final_video.name,
        file_size_mb,
    )
    return final_video


def execute_pipeline(args: argparse.Namespace) -> List[Path]:
    """Ejecuta el ciclo de vida del pipeline para uno o múltiples videos (modo Batch)."""
    overall_start = time.time()
    topics = extract_topics(args)
    total_jobs = len(topics)

    logger.info("=" * 70)
    logger.info("PIPELINE DE AUTOMATIZACIÓN MULTIMEDIA (BATCH & VERTICAL)")
    logger.info("Total de videos a procesar: {}", total_jobs)
    logger.info("Formato seleccionado: {} ({}x{})", args.aspect_ratio, *settings.get_dimensions(args.aspect_ratio))
    for i, t in enumerate(topics, start=1):
        logger.info("  {}. {}", i, t)
    logger.info("=" * 70)

    # Modo Dry-Run (validación de configuración sin consumo de recursos)
    if args.dry_run:
        logger.info("[DRY RUN] Verificando configuración y disponibilidad de dependencias...")
        logger.info("LLM Provider: {} (Key configurada: {})", args.llm_provider, bool(settings.GEMINI_API_KEY or settings.DEEPSEEK_API_KEY))
        logger.info("TTS Provider: {} (ElevenLabs Key: {})", args.tts_provider, bool(settings.ELEVENLABS_API_KEY))
        logger.info("Whisper Model: {} on {}", settings.WHISPER_MODEL, settings.WHISPER_DEVICE)
        logger.info("Image Provider: {} (Image Key: {})", args.image_provider, bool(settings.IMAGE_API_KEY))
        logger.info("Escala: {} ({}x{}) @ {}fps", args.aspect_ratio, *settings.get_dimensions(args.aspect_ratio), settings.OUTPUT_FPS)
        logger.info("Publicación Social: Todo={} (Plataformas: {}, Pack Local: {})", bool(args.publish_all), args.publish_platforms, not args.no_social_pack)
        logger.info("Buffer Publisher: Token Configurado={} (Modo: {})", bool(settings.BUFFER_ACCESS_TOKEN), settings.BUFFER_SHARE_MODE)
        logger.info("Subida a YouTube: {} (Privacidad: {})", bool(args.upload or args.publish_all), args.privacy)
        logger.success("[DRY RUN] Plan de ejecución verificado correctamente para {} video(s).", total_jobs)
        return []

    if args.clean:
        clean_temp_workspace(clean_images=True, clean_audio=True, clean_jobs=True)

    produced_videos: List[Path] = []
    for idx, topic in enumerate(topics, start=1):
        try:
            video_path = execute_single_video_job(topic, args, job_index=idx, total_jobs=total_jobs)
            produced_videos.append(video_path)
        except Exception as e:
            logger.exception("Error procesando video [{}/{} - '{}']: {}", idx, total_jobs, topic, e)
            if total_jobs == 1:
                raise e
            logger.warning("Continuando con los siguientes videos del lote...")

    overall_elapsed = time.time() - overall_start
    logger.info("\n" + "=" * 70)
    logger.success("PROCESAMIENTO FINALIZADO: {} DE {} VIDEO(S) GENERADOS CON ÉXITO ({:.2f}s)", len(produced_videos), total_jobs, overall_elapsed)
    for idx, v in enumerate(produced_videos, start=1):
        mb = v.stat().st_size / (1024 * 1024) if v.exists() else 0.0
        logger.success("  {}. {} ({:.2f} MB)", idx, v, mb)
    logger.info("=" * 70)
    return produced_videos


def build_parser() -> argparse.ArgumentParser:
    """Configura los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Pipeline 100%% Automatizado de Creación Audiovisual (Shorts, Reels, TikTok y Horizontal)",
    )
    parser.add_argument(
        "--topic",
        nargs="+",
        type=str,
        default=["La teoria de la muerte y el multiverso"],
        help="Uno o varios temas para generar videos (ej: --topic 'Tema 1' 'Tema 2' o 'Tema 1, Tema 2')",
    )
    parser.add_argument(
        "--topics-file",
        type=str,
        default=None,
        help="Ruta a un archivo .txt con un tema por línea para generación masiva en lote (Batch)",
    )
    parser.add_argument(
        "--aspect-ratio",
        type=str,
        choices=["9:16", "16:9"],
        default=settings.DEFAULT_ASPECT_RATIO,
        help="Escala de aspecto visual: 9:16 (Vertical Shorts/TikTok/Reels 1080x1920) o 16:9 (Panorámico 1920x1080). Default: 9:16",
    )
    parser.add_argument(
        "--duration-minutes",
        type=float,
        default=settings.DEFAULT_DURATION_MINUTES,
        help="Duración estimada de cada video en minutos (ej: 2.0 a 3.0 para videos largos, default: 2.5 min)",
    )
    parser.add_argument(
        "--target-words",
        type=int,
        default=None,
        help="Cantidad objetivo explícita de palabras para el guion (ej: 140 para Shorts de 1 min, 500 para 3.5 min)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(settings.OUTPUT_DIR),
        help="Directorio donde se acumulan los videos generados sin sobreescribirse (Default: output/)",
    )
    parser.add_argument(
        "--output-name",
        type=str,
        default=None,
        help="Nombre de archivo específico para el video final (solo cuando se procesa un único tema)",
    )
    parser.add_argument(
        "--llm-provider",
        type=str,
        choices=["gemini", "deepseek"],
        default=settings.LLM_PROVIDER,
        help="Proveedor para la generación del guion y prompts",
    )
    parser.add_argument(
        "--tts-provider",
        type=str,
        choices=["elevenlabs", "edge-tts"],
        default=settings.TTS_PROVIDER,
        help="Motor de síntesis de voz (edge-tts es 100%% gratuito)",
    )
    parser.add_argument(
        "--image-provider",
        type=str,
        choices=["imagen", "fal", "replicate", "stability", "pollinations", "pexels"],
        default=settings.IMAGE_PROVIDER,
        help="Proveedor para generar o descargar imágenes coherentes",
    )
    parser.add_argument(
        "--skip-script",
        action="store_true",
        help="Omitir generación de guion y usar assets/script.json existente",
    )
    parser.add_argument(
        "--skip-audio",
        action="store_true",
        help="Omitir síntesis de voz y usar assets/audio/narration.mp3 existente",
    )
    parser.add_argument(
        "--skip-alignment",
        action="store_true",
        help="Omitir detección de pausas y alineación con Whisper",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Omitir generación de imágenes y usar assets/images/ existentes",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="Omitir renderizado del video final",
    )
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="No quemar subtítulos en el video final",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Subir los videos finales automáticamente a YouTube vía API v3",
    )
    parser.add_argument(
        "--publish",
        "--publish-all",
        dest="publish_all",
        action="store_true",
        help="Generar copies/hashtags con IA y distribuir simultáneamente a YouTube Shorts, Instagram Reels y TikTok",
    )
    parser.add_argument(
        "--publish-platforms",
        nargs="+",
        choices=["youtube", "instagram", "tiktok", "all"],
        default=None,
        help="Especificar redes para publicación (ej: --publish-platforms youtube instagram)",
    )
    parser.add_argument(
        "--no-social-pack",
        action="store_true",
        help="No generar el paquete local con video, textos y manifiesto en output/social_packages/",
    )
    parser.add_argument(
        "--privacy",
        type=str,
        choices=["private", "unlisted", "public"],
        default=settings.YOUTUBE_PRIVACY_STATUS,
        help="Estado de privacidad para el video en YouTube",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verificar configuración y rutas sin consumir créditos ni procesar video",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Limpiar archivos temporales y caché antes de iniciar la ejecución",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        execute_pipeline(args)
    except KeyboardInterrupt:
        logger.warning("\nOperación cancelada por el usuario.")
        sys.exit(130)
    except Exception as e:
        logger.exception("Error crítico durante la ejecución del pipeline: {}", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
