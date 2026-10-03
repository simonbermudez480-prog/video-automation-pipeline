"""
Pipeline de Automatización Multimedia 100% Autónomo.
Ejecución: python main.py --topic "Tema del video"

Flujo de producción:
Idea/Tema -> Guion estructurado -> Síntesis de voz -> Detección de pausas/timestamps ->
Generación de imágenes coherentes -> Montaje audiovisual (Ken Burns) -> Publicación en YouTube
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from src.config import settings, ROOT_DIR, ASSETS_DIR, IMAGES_DIR, AUDIO_DIR, SUBTITLES_DIR, TEMP_DIR, OUTPUT_DIR
from src.logger import logger
from src.script_generator import generate_script, save_script_to_disk, ScriptOutput
from src.voice_synthesizer import synthesize_voice
from src.audio_processor import process_audio_and_align
from src.image_generator import generate_images_for_scenes
from src.video_assembler import assemble_video
from src.youtube_uploader import upload_video_to_youtube


def clean_temp_workspace(clean_images: bool = True, clean_audio: bool = False) -> None:
    """Limpia archivos temporales de renderizado previo y opcionalmente imágenes y audio anteriores."""
    logger.info("Limpiando directorios de trabajo temporales...")
    dirs_to_clean = [TEMP_DIR]
    if clean_images:
        dirs_to_clean.append(IMAGES_DIR)
    if clean_audio:
        dirs_to_clean.extend([AUDIO_DIR, SUBTITLES_DIR])

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


def execute_pipeline(args: argparse.Namespace) -> None:
    """Ejecuta el ciclo de vida completo del pipeline audiovisual."""
    start_time = time.time()
    logger.info("=" * 70)
    logger.info("INICIANDO PIPELINE DE AUTOMATIZACIÓN MULTIMEDIA")
    logger.info("Tema: '{}'", args.topic)
    logger.info("=" * 70)

    # Modo Dry-Run (validación de configuración sin consumo de recursos)
    if args.dry_run:
        logger.info("[DRY RUN] Verificando configuración y disponibilidad de dependencias...")
        logger.info("LLM Provider: {} (Key configurada: {})", args.llm_provider, bool(settings.GEMINI_API_KEY or settings.DEEPSEEK_API_KEY))
        logger.info("TTS Provider: {} (ElevenLabs Key: {})", args.tts_provider, bool(settings.ELEVENLABS_API_KEY))
        logger.info("Whisper Model: {} on {}", settings.WHISPER_MODEL, settings.WHISPER_DEVICE)
        logger.info("Image Provider: {} (Image Key: {})", args.image_provider, bool(settings.IMAGE_API_KEY))
        logger.info("Resolución de salida: {} @ {}fps", settings.OUTPUT_RESOLUTION, settings.OUTPUT_FPS)
        logger.info("Subida a YouTube: {} (Privacidad: {})", args.upload, args.privacy)
        logger.success("[DRY RUN] Plan de ejecución verificado correctamente. Listo para producción.")
        return

    if args.clean:
        clean_temp_workspace(clean_images=True, clean_audio=True)
    elif not args.skip_script and settings.SCRIPT_JSON_PATH.exists():
        # Detección automática de cambio de tema para evitar contaminación entre ejecuciones
        try:
            with open(settings.SCRIPT_JSON_PATH, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
                prev_title = prev_data.get("metadata", {}).get("title", "").lower()
                current_topic_lower = args.topic.lower()
                is_different_topic = (
                    ("segunda guerra" in current_topic_lower and "guerra" not in prev_title) or
                    ("multiverso" in current_topic_lower and "multiverso" not in prev_title) or
                    (args.topic.lower() not in prev_title and not any(w in prev_title for w in args.topic.lower().split() if len(w) > 4))
                )
                if is_different_topic:
                    logger.warning(
                        "Detectado cambio de tema respecto al guion previo ('{}' -> '{}'). Purgando automáticamente assets anteriores...",
                        prev_title,
                        args.topic,
                    )
                    clean_temp_workspace(clean_images=True, clean_audio=True)
        except Exception as e:
            logger.debug("No se pudo auditar tema previo: {}", e)

    # -------------------------------------------------------------
    # PASO 1: Generación de Guion y Prompts Visuales
    # -------------------------------------------------------------
    script_data: ScriptOutput
    if not args.skip_script:
        logger.info("\n>>> [PASO 1/6] Generando guion estructurado y prompts visuales ({:.1f} min)...", args.duration_minutes)
        script_data = generate_script(
            topic=args.topic,
            duration_minutes=args.duration_minutes,
            target_words=args.target_words,
            provider=args.llm_provider,
        )
        save_script_to_disk(script_data)
    else:
        logger.info("\n>>> [PASO 1/6] Omitido: Cargando guion existente desde: {}", settings.SCRIPT_JSON_PATH)
        if not settings.SCRIPT_JSON_PATH.exists():
            raise FileNotFoundError(f"No existe guion previo en: {settings.SCRIPT_JSON_PATH}")
        with open(settings.SCRIPT_JSON_PATH, "r", encoding="utf-8") as f:
            script_data = ScriptOutput.model_validate_json(f.read())

    logger.info("Título: {}", script_data.metadata.title)
    logger.info("Número de escenas definidas: {}", len(script_data.scenes))

    # -------------------------------------------------------------
    # PASO 2: Síntesis de Voz (TTS)
    # -------------------------------------------------------------
    narration_audio_path = settings.NARRATION_AUDIO_PATH
    if not args.skip_audio:
        logger.info("\n>>> [PASO 2/6] Sintetizando locución de voz con pausas naturales...")
        narration_audio_path = synthesize_voice(
            text=script_data.narration_full,
            output_path=settings.NARRATION_AUDIO_PATH,
            provider=args.tts_provider,
        )
    else:
        logger.info("\n>>> [PASO 2/6] Omitido: Usando archivo de audio existente: {}", narration_audio_path)
        if not narration_audio_path.exists():
            raise FileNotFoundError(f"No se encontró audio de narración en: {narration_audio_path}")

    # -------------------------------------------------------------
    # PASO 3: Detección de Pausas, Timestamps y Subtítulos
    # -------------------------------------------------------------
    subtitles_path = settings.SUBTITLES_SRT_PATH
    if not args.skip_alignment:
        logger.info("\n>>> [PASO 3/6] Detectando pausas y alineando timestamps con faster-whisper y pydub...")
        script_data.scenes, subtitles_path = process_audio_and_align(
            audio_path=narration_audio_path,
            scenes=script_data.scenes,
            srt_output_path=settings.SUBTITLES_SRT_PATH,
        )
        # Guardar escenas alineadas actualizadas
        save_script_to_disk(script_data, target_path=settings.ALIGNED_SCENES_PATH)
    else:
        logger.info("\n>>> [PASO 3/6] Omitido: Usando alineación previa de escenas y subtítulos.")
        if settings.ALIGNED_SCENES_PATH.exists():
            with open(settings.ALIGNED_SCENES_PATH, "r", encoding="utf-8") as f:
                script_data = ScriptOutput.model_validate_json(f.read())

    # -------------------------------------------------------------
    # PASO 4: Generación de Imágenes Coherentes 16:9
    # -------------------------------------------------------------
    image_paths = []
    if not args.skip_images:
        logger.info("\n>>> [PASO 4/6] Generando imágenes 16:9 secuenciales para cada escena...")
        image_paths = generate_images_for_scenes(
            scenes=script_data.scenes,
            output_dir=settings.IMAGES_DIR,
            provider=args.image_provider,
            topic=args.topic,
        )
    else:
        logger.info("\n>>> [PASO 4/6] Omitido: Cargando imágenes existentes de: {}", settings.IMAGES_DIR)
        for idx in range(1, len(script_data.scenes) + 1):
            p = settings.IMAGES_DIR / f"scene_{idx:03d}.png"
            if not p.exists():
                raise FileNotFoundError(f"Falta la imagen requerida: {p}")
            image_paths.append(p)

    # -------------------------------------------------------------
    # PASO 5: Montaje Audiovisual con Efecto Dinámico (FFmpeg)
    # -------------------------------------------------------------
    final_video_path = settings.FINAL_VIDEO_PATH
    if not args.skip_video:
        logger.info("\n>>> [PASO 5/6] Ensamblando video con efecto Ken Burns y subtítulos quemados...")
        final_video_path = assemble_video(
            scenes=script_data.scenes,
            image_paths=image_paths,
            audio_path=narration_audio_path,
            subtitles_path=subtitles_path,
            output_video_path=settings.FINAL_VIDEO_PATH,
            burn_subtitles=not args.no_subtitles,
        )
    else:
        logger.info("\n>>> [PASO 5/6] Omitido: Montaje de video saltado por usuario.")

    # -------------------------------------------------------------
    # PASO 6: Publicación en YouTube
    # -------------------------------------------------------------
    if args.upload:
        logger.info("\n>>> [PASO 6/6] Publicando video en YouTube...")
        video_url = upload_video_to_youtube(
            video_path=final_video_path,
            title=script_data.metadata.title,
            description=script_data.metadata.description,
            tags=script_data.metadata.tags,
            privacy_status=args.privacy,
        )
        logger.success("Video disponible en YouTube: {}", video_url)
    else:
        logger.info("\n>>> [PASO 6/6] Subida a YouTube omitida (usa flag --upload para subir automáticamente).")

    elapsed = time.time() - start_time
    logger.info("=" * 70)
    logger.success("PIPELINE FINALIZADO CON ÉXITO EN {:.2f} SEGUNDOS", elapsed)
    logger.success("Archivo final exportado en: {}", final_video_path)
    logger.info("=" * 70)


def build_parser() -> argparse.ArgumentParser:
    """Configura los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Pipeline 100%% Automatizado de Creación Audiovisual para YouTube",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default="La teoria de la muerte y el multiverso",
        help="Tema o idea central para el video educativo",
    )
    parser.add_argument(
        "--duration-minutes",
        type=float,
        default=settings.DEFAULT_DURATION_MINUTES,
        help="Duración estimada del video en minutos (ej: 2.5, 3.5, 5.0)",
    )
    parser.add_argument(
        "--target-words",
        type=int,
        default=None,
        help="Cantidad objetivo explícita de palabras para el guion (ej: 500, 750)",
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
        help="Proveedor para generar imágenes en formato 16:9",
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
        help="Subir el video final automáticamente a YouTube vía API v3",
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
        help="Limpiar archivos temporales antes de iniciar la ejecución",
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
