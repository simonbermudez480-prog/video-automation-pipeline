"""
Cola de publicación diferida (Fase 17 / FR-14.4 y FR-14.5).
Un video que no pudo revisarse por falta de cuota de visión se guarda en output/queue/.
`python main.py --process-queue` re-audita las escenas pendientes, vuelve a montar el video con las
fusiones finales y lo publica solo si supera el control de calidad completo.
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.config import OUTPUT_DIR
from src.logger import logger
from src.quality_gate import SOURCE_KINDS, audit_images_batch, choose_opening_image, load_manifest, run_quality_gate, save_manifest
from src.script_generator import ScriptOutput
from src.video_assembler import apply_scene_merges, assemble_video, choose_look

QUEUE_DIR = OUTPUT_DIR / "queue"


def ask_yes_no(question: str) -> bool:
    """Pregunta en la terminal; sin terminal real (o con la entrada cerrada) la respuesta es 'no'."""
    if not (sys.stdin and sys.stdin.isatty()):
        return False
    try:
        return input(question).strip().lower() in ("s", "si", "sí", "y", "yes")
    except EOFError:
        return False


def enqueue(entry: dict) -> Path:
    """Guarda un trabajo en la cola. entry incluye rutas de guion, imágenes, audio, subtítulos y opciones de publicación."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    entry = {**entry, "queued_at": datetime.now().isoformat(timespec="seconds"), "attempts": 0}
    path = QUEUE_DIR / f"{Path(entry['video_path']).stem}.json"
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.warning("Video en cola de publicación diferida (sin capacidad de revisión visual ahora): {}", path)
    return path


def _reaudit_pending(images_dir: Path, script: ScriptOutput, topic: str) -> bool:
    """
    Audita las escenas sin revisar (marcadas 'unaudited' o ausentes del manifiesto).
    Retorna False si la visión sigue sin estar disponible.
    """
    manifest = load_manifest(images_dir)
    entries = manifest.setdefault("scenes", {})
    for i in range(1, len(script.scenes) + 1):
        entries.setdefault(str(i), {"source": None, "audit": "unaudited", "reason": "", "issues": []})
    pending = sorted(int(k) for k, e in entries.items() if e.get("audit") == "unaudited")
    if not pending:
        return True
    items = []
    for i in pending:
        e, scene = entries[str(i)], script.scenes[i - 1]
        kind = SOURCE_KINDS.get(e.get("source") or "", "unknown")
        items.append({
            "idx": i, "path": images_dir / f"scene_{i:03d}.png", "narration": scene.narration_text,
            "prompt": scene.visual_prompt, "shot_type": scene.shot_type, "source_kind": kind,
            "source_title": (e.get("credit") or {}).get("title", "") if kind == "archive" else "",
        })
    contract = script.visual_contract
    verdicts = audit_images_batch(
        items,
        era=getattr(contract, "era_setting", "") or "",
        topic=getattr(contract, "archive_search_terms", None) or topic,
    )
    if verdicts is None:
        return False
    for i, (approved, reason, issues, impact) in verdicts.items():
        entries[str(i)].update(audit="approved" if approved else "rejected", reason=reason, issues=issues, impact=impact)
    save_manifest(images_dir, manifest)
    return True


def _move(qfile: Path, entry: dict, folder: str) -> None:
    target = QUEUE_DIR / folder
    target.mkdir(parents=True, exist_ok=True)
    (target / qfile.name).write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    qfile.unlink()


def process_queue(publish: Callable[[dict, Path], None], require_approval: bool = True) -> dict[str, int]:
    """
    Procesa cada trabajo en cola. Resultados: 'published' (publicado y movido a done/),
    'needs_review' (rechazos reales, movido a needs_review/), 'waiting' (sigue en cola).
    publish(entry, video_path) publica el video; se inyecta desde main.py.
    """
    counts = {"published": 0, "needs_review": 0, "waiting": 0}
    for qfile in sorted(QUEUE_DIR.glob("*.json")):
        entry = json.loads(qfile.read_text(encoding="utf-8"))
        entry["attempts"] = entry.get("attempts", 0) + 1
        entry["last_attempt"] = datetime.now().isoformat(timespec="seconds")
        logger.info("Procesando cola: {} (intento {})", qfile.stem, entry["attempts"])

        script = ScriptOutput.model_validate_json(Path(entry["script_path"]).read_text(encoding="utf-8"))
        images_dir = Path(entry["images_dir"])
        if not _reaudit_pending(images_dir, script, entry.get("topic", "")):
            logger.warning("Sigue sin haber capacidad de revisión visual; '{}' queda en cola.", qfile.stem)
            qfile.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
            counts["waiting"] += 1
            continue

        image_paths = [images_dir / f"scene_{i:03d}.png" for i in range(1, len(script.scenes) + 1)]
        gate = run_quality_gate(image_paths, Path(entry["contact_sheet"]))
        entry["gate_reasons"] = gate.reasons
        if not gate.passed:
            if gate.unaudited:
                qfile.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
                counts["waiting"] += 1
            else:
                logger.error("'{}' no supera el control de calidad tras la revisión: pasa a needs_review.", qfile.stem)
                entry["status"] = "needs_review"
                _move(qfile, entry, "needs_review")
                counts["needs_review"] += 1
            continue

        if require_approval and entry.get("require_approval", True):
            if not (sys.stdin and sys.stdin.isatty()):
                logger.warning("'{}' requiere aprobación humana y no hay terminal interactiva; queda en cola.", qfile.stem)
                qfile.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
                counts["waiting"] += 1
                continue
            if not ask_yes_no(f"\nRevisa la hoja de contacto: {entry['contact_sheet']}\n¿Publicar '{qfile.stem}'? [s/N]: "):
                entry["status"] = "rejected_by_human"
                _move(qfile, entry, "needs_review")
                counts["needs_review"] += 1
                continue

        # Se vuelve a montar: las fusiones pueden haber cambiado al completar la revisión
        scenes, images = apply_scene_merges(script.scenes, image_paths, gate.merges)
        video_path = assemble_video(
            scenes=scenes,
            image_paths=images,
            audio_path=Path(entry["audio_path"]),
            subtitles_path=Path(entry["subtitles_path"]) if entry.get("subtitles_path") else None,
            output_video_path=Path(entry["video_path"]),
            burn_subtitles=entry.get("burn_subtitles", True),
            aspect_ratio=entry.get("aspect_ratio", "9:16"),
            temp_dir=Path(entry["job_dir"]) / "temp",
            look=choose_look(script.visual_contract),
            hook_text=script.hook_text,
            closing_question=script.closing_question,
            opening_image=choose_opening_image(image_paths, load_manifest(images_dir), gate.merges),
        )
        entry["merged_scenes"] = {str(k): v for k, v in sorted(gate.merges.items())}
        publish(entry, video_path)
        entry["status"] = "published"
        _move(qfile, entry, "done")
        counts["published"] += 1

    logger.info("Cola procesada: {} publicados, {} a revisión, {} en espera.", counts["published"], counts["needs_review"], counts["waiting"])
    return counts
