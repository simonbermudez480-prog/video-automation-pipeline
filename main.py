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

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.config import settings, ROOT_DIR, ASSETS_DIR, IMAGES_DIR, AUDIO_DIR, SUBTITLES_DIR, TEMP_DIR, OUTPUT_DIR, JOBS_DIR
from src.logger import logger
from src.script_generator import generate_script, save_script_to_disk, ScriptOutput
from src.voice_synthesizer import synthesize_voice
from src.audio_processor import process_audio_and_align
from src.image_generator import generate_images_for_scenes
from src.quality_gate import MANIFEST_NAME, choose_opening_image, load_manifest, run_quality_gate
from src.publish_queue import ask_yes_no, enqueue, process_queue
from src.video_assembler import apply_scene_merges, assemble_video, choose_look
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
        if JOBS_DIR.exists():
            dirs_to_clean.append(JOBS_DIR)

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


def clean_topic(text: str) -> str:
    """Quita restos de listas al inicio del tema ("3. ", "2) ", "- ", ". ") y comillas o espacios sobrantes (FR-19.4)."""
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(?:\d{1,3}\s*[.)\-:–—](?!\d)\s*|[-–—•*·.,;:]+\s*)+", "", text)
    return text.strip(" \"'«»“”").strip()


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

    # 2. Leer desde argumento --topic: cada valor es un tema completo (puede contener comas, ej. "Poyais, 1822")
    if getattr(args, "topic", None):
        topic_arg = args.topic
        items = topic_arg if isinstance(topic_arg, list) else [topic_arg]
        raw_topics.extend(t.strip() for t in items if t and t.strip())

    # 3. Limpiar restos de listas copiadas y eliminar duplicados manteniendo orden de inserción
    unique_topics = []
    for t in filter(None, map(clean_topic, raw_topics)):
        if t not in unique_topics:
            unique_topics.append(t)

    if not unique_topics:
        unique_topics = ["La teoria de la muerte y el multiverso"]

    return unique_topics


def hook_for(script: ScriptOutput) -> Optional[str]:
    """Texto de gancho del guion o, si falta (guiones antiguos), el título sin hashtags si es corto."""
    if script.hook_text:
        return script.hook_text.strip()
    title = re.sub(r"#\w+", "", script.metadata.title).replace("|", " ").strip(" -:")
    return title if 0 < len(title.split()) <= 12 else None


def publish_social(
    topic: str,
    narration_full: str,
    video_path: Path,
    platforms: List[str],
    create_social_pack: bool,
    privacy: Optional[str],
    llm_provider: Optional[str],
    duration_minutes: Optional[float],
    closing_question: Optional[str] = None,
) -> Optional[dict]:
    """
    Redacta los copies con IA y publica/empaqueta el video (usado por el flujo normal, la cola y la interfaz).
    Retorna el resultado por plataforma ({plataforma: {status, post_id, ...}}) o None si falló.
    """
    try:
        social_bundle = generate_social_copy(
            topic=topic,
            narration_summary=narration_full,
            duration_seconds=(duration_minutes or 1.0) * 60.0,
            provider=llm_provider,
        )
        logger.info("Copies listos: Título YouTube = '{}'", social_bundle.youtube_shorts.title)
        if closing_question:
            # La pregunta final del video va en los 3 textos y como comentario (primer comentario en Instagram)
            q = closing_question.strip()
            social_bundle.tiktok.caption = f"{social_bundle.tiktok.caption.rstrip()} {q}"
            social_bundle.instagram_reels.caption = f"{social_bundle.instagram_reels.caption.rstrip()}\n\n{q}"
            social_bundle.youtube_shorts.description = f"{q}\n\n{social_bundle.youtube_shorts.description}"
            social_bundle.youtube_shorts.pinned_comment = q

        pub_results = publish_video_multiplatform(
            video_path=video_path,
            bundle=social_bundle,
            platforms=platforms,
            create_package=create_social_pack,
            privacy=privacy,
        )
        if "youtube" in pub_results and pub_results["youtube"].get("url"):
            logger.success("Video disponible en YouTube: {}", pub_results["youtube"]["url"])
        return pub_results
    except Exception as e:
        logger.error("Error durante la generación de copies o publicación social: {}", e)
        return None


def save_publication(job_dir: Path, platforms: List[str], results: Optional[dict]) -> None:
    """
    Guarda en publication.json el resultado de la publicación (IDs de Buffer) para el historial.
    Solo reemplaza las plataformas publicadas ahora: las demás conservan su registro y sus enlaces.
    """
    results = results or {}
    path = job_dir / "publication.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"platforms": {}}
    data["published_at"] = datetime.now().isoformat(timespec="seconds")
    for p in platforms:
        data.setdefault("platforms", {})[p] = {k: results.get(p, {}).get(k) for k in ("status", "post_id", "message")}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def repair_job(job_dir: Path) -> bool:
    """
    Reparar escenas (FR-19.3): rehace solo las imágenes no aprobadas de un video ya producido, vuelve a pasar el
    control de calidad y re-monta el video en el mismo archivo. Retorna True si ahora supera el control.
    """
    report_path = job_dir / "quality_report.json"
    script_path = job_dir / "aligned_scenes.json"
    if not report_path.exists() or not script_path.exists():
        logger.error("La carpeta {} no tiene reporte o guion alineado; no se puede reparar.", job_dir)
        return False
    report = json.loads(report_path.read_text(encoding="utf-8"))
    script = ScriptOutput(**json.loads(script_path.read_text(encoding="utf-8")))
    images_dir = job_dir / "images"
    manifest = load_manifest(images_dir)
    aspect_ratio = manifest.get("aspect_ratio") or "9:16"
    before = sum(1 for e in manifest["scenes"].values() if e.get("audit") == "approved")
    logger.info(">>> Reparando escenas de '{}' ({}/{} imágenes aprobadas)...", report.get("topic"), before, len(script.scenes))

    image_paths = generate_images_for_scenes(
        scenes=script.scenes,
        output_dir=images_dir,
        topic=manifest.get("topic") or report.get("topic"),
        aspect_ratio=aspect_ratio,
        visual_contract=script.visual_contract,
        repair=True,
    )
    video_path = Path(report["video_path"])
    gate = run_quality_gate(image_paths, Path(report.get("contact_sheet") or OUTPUT_DIR / "review" / f"{video_path.stem}_contact.png"))
    after = sum(1 for e in load_manifest(images_dir)["scenes"].values() if e.get("audit") == "approved")

    scenes, images = apply_scene_merges(script.scenes, image_paths, gate.merges)
    assemble_video(
        scenes=scenes,
        image_paths=images,
        audio_path=job_dir / "audio" / "narration.mp3",
        subtitles_path=job_dir / "subtitles" / "subtitles.srt",
        output_video_path=video_path,
        burn_subtitles=True,
        aspect_ratio=aspect_ratio,
        temp_dir=job_dir / "temp",
        look=choose_look(script.visual_contract),
        hook_text=hook_for(script),
        closing_question=script.closing_question,
        opening_image=choose_opening_image(image_paths, load_manifest(images_dir), gate.merges),
    )
    # La versión optimizada para subir era del video anterior: se borra para que se rehaga al publicar
    (video_path.parent / f"{video_path.stem}_web.mp4").unlink(missing_ok=True)

    report.update(
        status="passed" if gate.passed else "needs_review",
        reasons=gate.reasons,
        failing_scenes=sorted(gate.failing_scenes),
        merged_scenes={str(k): v for k, v in sorted(gate.merges.items())},
        repaired_at=datetime.now().isoformat(timespec="seconds"),
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Reparación terminada: {} -> {} de {} imágenes aprobadas.", before, after, len(script.scenes))
    return gate.passed


def publish_job(job_dir: Path, platforms: List[str], privacy: Optional[str], llm_provider: Optional[str]) -> bool:
    """Publica un video ya producido a partir de su carpeta de trabajo (usado por la interfaz con --publish-job)."""
    report_path = job_dir / "quality_report.json"
    if not report_path.exists():
        logger.error("La carpeta {} no tiene quality_report.json; no se puede publicar.", job_dir)
        return False
    report = json.loads(report_path.read_text(encoding="utf-8"))
    script_path = next((p for p in (job_dir / "aligned_scenes.json", job_dir / "script.json") if p.exists()), None)
    if not script_path:
        logger.error("La carpeta {} no tiene guion.", job_dir)
        return False
    script = ScriptOutput.model_validate_json(script_path.read_text(encoding="utf-8"))
    duration = (script.scenes[-1].end_time or 0) / 60.0 if script.scenes and script.scenes[-1].end_time else None
    results = publish_social(
        topic=report.get("topic", ""),
        narration_full=script.narration_full,
        video_path=Path(report["video_path"]),
        platforms=platforms,
        create_social_pack=False,
        privacy=privacy,
        llm_provider=llm_provider,
        duration_minutes=duration,
        closing_question=script.closing_question,
    )
    save_publication(job_dir, platforms, results)
    ok = bool(results) and all((results.get(p) or {}).get("status") == "success" for p in platforms)
    if ok:  # si falla, el reporte conserva el veredicto del control; el fallo queda en publication.json
        report["status"] = "published"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return ok


def publish_queued(entry: dict, video_path: Path) -> None:
    """Publica un trabajo de la cola diferida con las opciones guardadas al encolarlo."""
    script = ScriptOutput.model_validate_json(Path(entry["script_path"]).read_text(encoding="utf-8"))
    results = publish_social(
        topic=entry["topic"],
        narration_full=script.narration_full,
        video_path=video_path,
        platforms=entry["platforms"],
        create_social_pack=entry.get("create_social_pack", True),
        privacy=entry.get("privacy"),
        llm_provider=entry.get("llm_provider"),
        duration_minutes=entry.get("duration_minutes"),
        closing_question=script.closing_question,
    )
    job_dir = Path(entry["job_dir"])
    save_publication(job_dir, entry["platforms"], results)
    report_path = job_dir / "quality_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["status"] = "published"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def execute_single_video_job(topic: str, args: argparse.Namespace, job_index: int, total_jobs: int) -> Path:
    """Ejecuta el ciclo de vida completo de creación para un video individual en su propio entorno aislado."""
    start_time = time.time()
    aspect_ratio = args.aspect_ratio or settings.DEFAULT_ASPECT_RATIO
    ratio_tag = "9x16" if aspect_ratio == "9:16" else "16x9"
    slug = slugify(topic)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Carpeta aislada para assets de este trabajo
    job_dir = JOBS_DIR / f"{slug}_{ratio_tag}_{timestamp}"
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
            voice=getattr(args, "tts_voice", None),
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
            visual_contract=getattr(script_data, "visual_contract", None),
        )
        for img in image_paths + [job_images_dir / MANIFEST_NAME]:
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

    # Control de calidad visual (FR-12 / FR-14.6): decide qué escenas se fusionan antes del montaje
    contact_sheet = OUTPUT_DIR / "review" / f"{target_video_path.stem}_contact.png"
    gate = run_quality_gate(image_paths, contact_sheet) if image_paths else None
    quality_report = {}
    if gate:
        # Se escribe siempre: la interfaz lo usa para revisar y publicar videos ya producidos
        quality_report = {
            "topic": topic,
            "title": script_data.metadata.title,
            "video_path": str(target_video_path),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "status": "passed" if gate.passed else "needs_review",
            "reasons": gate.reasons,
            "failing_scenes": sorted(gate.failing_scenes),
            "merged_scenes": {str(k): v for k, v in sorted(gate.merges.items())},
            "contact_sheet": str(contact_sheet),
            "hook_text": hook_for(script_data),
            "closing_question": script_data.closing_question,
        }
        (job_dir / "quality_report.json").write_text(json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8")
    assembly_scenes, assembly_images = (
        apply_scene_merges(script_data.scenes, image_paths, gate.merges) if gate else (script_data.scenes, image_paths)
    )
    # Apertura con la imagen de mayor impacto si supera claramente a la escena 1 (FR-17.2)
    opening_image = choose_opening_image(image_paths, load_manifest(image_paths[0].parent), gate.merges) if gate else None

    # -------------------------------------------------------------
    # PASO 5: Montaje Audiovisual con Efecto Dinámico (FFmpeg)
    # -------------------------------------------------------------
    final_video = target_video_path
    if not args.skip_video:
        logger.info("\n>>> [{}/{}] [PASO 5/6] Ensamblando video {} con Ken Burns y subtítulos quemados en zona segura...", job_index, total_jobs, aspect_ratio)
        final_video = assemble_video(
            scenes=assembly_scenes,
            image_paths=assembly_images,
            audio_path=narration_audio,
            subtitles_path=subtitles_file,
            output_video_path=target_video_path,
            burn_subtitles=not args.no_subtitles,
            aspect_ratio=aspect_ratio,
            temp_dir=job_temp_dir,
            look=choose_look(getattr(script_data, "visual_contract", None)),
            hook_text=hook_for(script_data),
            closing_question=script_data.closing_question,
            opening_image=opening_image,
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

    # Control de calidad visual previo a publicar (FR-12): bloquea la publicación automática si falla
    if platforms_to_publish and gate:
        approved = gate.passed and not args.require_approval
        images_dir = image_paths[0].parent
        if not gate.passed and gate.unaudited:
            # Falta capacidad de revisión visual (no hay rechazos que lo impidan): se publica más tarde desde la cola
            queued_script = job_dir / "queued_script.json"
            save_script_to_disk(script_data, target_path=queued_script)
            enqueue({
                "topic": topic,
                "job_dir": str(job_dir),
                "script_path": str(queued_script),
                "images_dir": str(images_dir),
                "audio_path": str(narration_audio),
                "subtitles_path": str(subtitles_file) if subtitles_file else None,
                "burn_subtitles": not args.no_subtitles,
                "aspect_ratio": aspect_ratio,
                "video_path": str(target_video_path),
                "contact_sheet": str(contact_sheet),
                "platforms": platforms_to_publish,
                "privacy": args.privacy,
                "require_approval": args.require_approval,
                "create_social_pack": create_social_pack,
                "llm_provider": args.llm_provider,
                "duration_minutes": args.duration_minutes,
            })
            quality_report["status"] = "queued"
            platforms_to_publish = []
            create_social_pack = False
        elif args.require_approval:
            if sys.stdin and sys.stdin.isatty():
                approved = ask_yes_no(
                    f"\nRevisa la hoja de contacto: {contact_sheet}\n"
                    f"Control de calidad: {'SUPERADO' if gate.passed else 'FALLIDO'}. ¿Publicar en {', '.join(platforms_to_publish)}? [s/N]: "
                )
                quality_report["human_decision"] = "approved" if approved else "rejected"
            else:
                logger.warning("Se requiere aprobación humana y no hay terminal interactiva (usa --no-approval para omitirla).")
        if not approved and quality_report["status"] != "queued":
            logger.error("Publicación BLOQUEADA: el video queda marcado 'needs_review'. Solo se genera el paquete local.")
            quality_report["status"] = "needs_review"
            platforms_to_publish = []
        (job_dir / "quality_report.json").write_text(json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8")

    if final_video.exists() and (create_social_pack or platforms_to_publish):
        logger.info(
            "\n>>> [{}/{}] [PASO 6/6] Redactando copies optimizados con IA y organizando distribución multi-plataforma...",
            job_index,
            total_jobs,
        )
        pub_results = publish_social(
            topic=topic,
            narration_full=script_data.narration_full,
            video_path=final_video,
            platforms=platforms_to_publish,
            create_social_pack=create_social_pack,
            privacy=args.privacy,
            llm_provider=args.llm_provider,
            duration_minutes=args.duration_minutes,
            closing_question=script_data.closing_question,
        )
        if platforms_to_publish:
            save_publication(job_dir, platforms_to_publish, pub_results)
            if quality_report:
                quality_report["status"] = "published"
                (job_dir / "quality_report.json").write_text(json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8")
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
        help="Uno o varios temas para generar videos; cada valor es un tema completo y puede llevar comas (ej: --topic 'Tema 1' 'Tema 2, 1822')",
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
        choices=["gemini", "elevenlabs", "edge-tts"],
        default=settings.TTS_PROVIDER,
        help="Motor de síntesis de voz (gemini: nativo y expresivo, elevenlabs, edge-tts)",
    )
    parser.add_argument(
        "--tts-voice",
        type=str,
        default=None,
        help="Voz específica para el sintetizador (ej. 'Puck', 'Charon', 'Aoede', 'Fenrir' en Gemini, o 'es-MX-DaliaNeural' en Edge-TTS)",
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
        "--process-queue",
        action="store_true",
        help="Procesar la cola de publicación diferida (output/queue/): re-auditar, re-montar y publicar lo que pase el control",
    )
    parser.add_argument(
        "--repair-job",
        type=str,
        default=None,
        metavar="CARPETA",
        help="Rehacer solo las escenas rechazadas de un video ya producido y volver a montarlo (usado por la interfaz)",
    )
    parser.add_argument(
        "--publish-job",
        type=str,
        default=None,
        metavar="CARPETA",
        help="Publicar un video ya producido a partir de su carpeta de trabajo (jobs/...), usado por la interfaz",
    )
    parser.add_argument(
        "--no-approval",
        dest="require_approval",
        action="store_false",
        help="Publicar sin confirmación humana si el control de calidad visual se supera (por defecto se pide confirmación)",
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
        if args.process_queue:
            process_queue(publish_queued, require_approval=args.require_approval)
            return
        if args.repair_job:
            sys.exit(0 if repair_job(Path(args.repair_job)) else 2)
        if args.publish_job:
            platforms = [p.lower() for p in args.publish_platforms] if args.publish_platforms else ["youtube", "instagram", "tiktok"]
            ok = publish_job(Path(args.publish_job), platforms, args.privacy, args.llm_provider)
            sys.exit(0 if ok else 1)
        execute_pipeline(args)
    except KeyboardInterrupt:
        logger.warning("\nOperación cancelada por el usuario.")
        sys.exit(130)
    except Exception as e:
        logger.exception("Error crítico durante la ejecución del pipeline: {}", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
