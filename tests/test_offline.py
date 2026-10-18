"""
Pruebas sin internet del pipeline (FR-19.5). Ejecutar desde la carpeta del programa:

    python -m unittest discover -s tests -v

La prueba de montaje necesita FFmpeg y tarda unos segundos; las demás son instantáneas.
"""
import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

import main  # noqa: E402
from src.buffer_publisher import BufferPublisher  # noqa: E402
from src import quality_gate  # noqa: E402
from src.quality_gate import evaluate_gate  # noqa: E402
from src.script_generator import Scene  # noqa: E402
from src.video_assembler import apply_scene_merges, assemble_video  # noqa: E402


def make_images(folder: Path, count: int, size=(108, 192)) -> list[Path]:
    """Imágenes de ruido distintas entre sí (no parecen fondo procedural ni duplicados)."""
    paths = []
    for i in range(1, count + 1):
        rng = random.Random(i)
        im = Image.new("RGB", size)
        im.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(size[0] * size[1])])
        path = folder / f"scene_{i:03d}.png"
        im.save(path)
        paths.append(path)
    return paths


def manifest(statuses: dict[int, str]) -> dict:
    return {"scenes": {str(i): {"audit": s} for i, s in statuses.items()}}


def scene(i: int, duration: float, start: float = 0.0) -> Scene:
    return Scene(scene_id=i, narration_text=f"Escena {i}", visual_prompt=f"prompt {i}",
                 start_time=start, end_time=start + duration, duration=duration)


class TopicTests(unittest.TestCase):
    def test_clean_topic_removes_list_prefixes(self):
        cases = {
            "3. El espía que salvó el Día D": "El espía que salvó el Día D",
            ". La batalla de Karánsebes": "La batalla de Karánsebes",
            "2) La guerra": "La guerra",
            "- Poyais, 1822": "Poyais, 1822",
            "  «El Emú (1932)» ": "El Emú (1932)",
            "• 4. Doble viñeta": "Doble viñeta",
        }
        for raw, expected in cases.items():
            self.assertEqual(main.clean_topic(raw), expected, raw)

    def test_clean_topic_keeps_numbers_that_belong_to_the_title(self):
        for title in ("3.5 millones de muertos", "1914-1918 la guerra", "1932: la guerra del emú"):
            self.assertEqual(main.clean_topic(title), title)

    def test_topic_with_commas_is_one_video(self):
        args = argparse.Namespace(topic=["El hombre que vendió un país (Gregor MacGregor y Poyais, 1822)"], topics_file=None)
        self.assertEqual(main.extract_topics(args), ["El hombre que vendió un país (Gregor MacGregor y Poyais, 1822)"])

    def test_cleaned_duplicates_are_removed(self):
        args = argparse.Namespace(topic=["1. La Navidad negra", "La Navidad negra", "  "], topics_file=None)
        self.assertEqual(main.extract_topics(args), ["La Navidad negra"])


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images = make_images(self.tmp, 6)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_approved_passes(self):
        result = evaluate_gate(self.images, manifest({i: "approved" for i in range(1, 7)}))
        self.assertTrue(result.passed)
        self.assertEqual(result.merges, {})

    def test_two_rejected_scenes_merge_with_previous_valid_scene(self):
        statuses = {i: "approved" for i in range(1, 7)} | {3: "rejected", 4: "rejected"}
        result = evaluate_gate(self.images, manifest(statuses))
        self.assertTrue(result.passed)
        self.assertEqual(result.merges, {3: 2, 4: 2})

    def test_three_rejected_scenes_block(self):
        statuses = {i: "approved" for i in range(1, 7)} | {2: "rejected", 4: "rejected", 6: "rejected"}
        result = evaluate_gate(self.images, manifest(statuses))
        self.assertFalse(result.passed)
        self.assertEqual(result.failing_scenes, {2, 4, 6})

    def test_first_scene_never_merges(self):
        statuses = {i: "approved" for i in range(1, 7)} | {1: "rejected"}
        self.assertFalse(evaluate_gate(self.images, manifest(statuses)).passed)

    def test_duplicate_image_is_detected(self):
        shutil.copy(self.images[0], self.images[3])
        result = evaluate_gate(self.images, manifest({i: "approved" for i in range(1, 7)}))
        self.assertIn(4, result.failing_scenes)

    def test_unaudited_scenes_are_reported_for_the_queue(self):
        statuses = {i: "approved" for i in range(1, 7)} | {5: "unaudited"}
        self.assertEqual(evaluate_gate(self.images, manifest(statuses)).unaudited, {5})

    def test_merge_adds_duration_without_changing_narration(self):
        scenes = [scene(1, 4.0, 0), scene(2, 3.0, 4), scene(3, 5.0, 7)]
        kept, paths = apply_scene_merges(scenes, self.images[:3], {2: 1})
        self.assertEqual([s.scene_id for s in kept], [1, 3])
        self.assertEqual(kept[0].duration, 7.0)
        self.assertEqual(kept[0].end_time, 7.0)
        self.assertEqual(paths, [self.images[0], self.images[2]])
        self.assertAlmostEqual(sum(s.duration for s in kept), 12.0)


class MajorityVoteTests(unittest.TestCase):
    ITEMS = [{"idx": 1, "source_kind": "archive"}, {"idx": 2, "source_kind": "stock"}, {"idx": 3, "source_kind": "archive"}]
    OK, BAD = (True, "bien", [], 7), (False, "otra época", ["ANACHRONISM"], 3)

    def run_vote(self, first, opinions):
        """opinions: veredictos que devolverán la 2.ª y 3.ª llamada al revisor."""
        calls = []

        def fake_audit(items, era="", topic=""):
            calls.append([it["idx"] for it in items])
            return {it["idx"]: opinions[len(calls) - 1][it["idx"]] for it in items}

        with mock.patch.object(quality_gate, "audit_images_batch", side_effect=fake_audit):
            return quality_gate.vote_on_doubtful(self.ITEMS, first), calls

    def test_clear_verdicts_spend_no_extra_calls(self):
        first = {1: self.OK, 2: (False, "persona moderna", ["UNWANTED_HUMAN"], 2), 3: self.OK}
        result, calls = self.run_vote(first, [])
        self.assertEqual(result, first)
        self.assertEqual(calls, [])

    def test_archive_rejected_by_judgment_gets_majority(self):
        first = {1: self.BAD, 2: self.OK, 3: self.OK}
        result, calls = self.run_vote(first, [{1: self.OK}, {1: self.OK}])
        self.assertTrue(result[1][0])
        self.assertEqual(calls, [[1], [1]])

    def test_second_opinion_agreeing_skips_third(self):
        flagged = (True, "texto raro", ["WATERMARK_OR_TEXT"], 6)
        result, calls = self.run_vote({1: self.OK, 2: flagged, 3: self.OK}, [{2: flagged}])
        self.assertTrue(result[2][0])
        self.assertEqual(calls, [[2]])

    def test_tie_without_third_opinion_rejects(self):
        flagged = (True, "texto raro", ["WATERMARK_OR_TEXT"], 6)
        no_answer = mock.patch.object(quality_gate, "audit_images_batch", side_effect=[{2: (False, "x", ["WATERMARK_OR_TEXT"], 1)}, None])
        with no_answer:
            result = quality_gate.vote_on_doubtful(self.ITEMS, {1: self.OK, 2: flagged, 3: self.OK})
        self.assertFalse(result[2][0])

    def test_audit_thumbnail_is_sent_as_jpeg(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            part = quality_gate._jpeg_part(make_images(tmp, 1, size=(1080, 1920))[0])
            self.assertEqual(part.inline_data.mime_type, "image/jpeg")
            self.assertLess(len(part.inline_data.data), 1_500_000)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class CreditsAndModelsTests(unittest.TestCase):
    def test_credits_cite_only_images_in_the_video_that_require_it(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            quality_gate.save_manifest(tmp, {"scenes": {
                "1": {"source": "wikimedia_scene", "credit": {"author": "Bernard Gagnon", "license": "CC BY-SA 4.0", "attribution_required": True}},
                "2": {"source": "wikimedia_topic", "credit": {"author": "Uncredited author; unknown", "license": "CC BY 2.0", "attribution_required": True}},
                "3": {"source": "pexels", "credit": {"author": "Ana", "license": "Pexels License", "attribution_required": False}},
                "4": {"source": "pollinations", "credit": {"author": "Pollinations", "license": "Generada por IA", "attribution_required": False}},
                "5": {"source": "openverse", "credit": {"author": "Bernard Gagnon", "license": "CC BY-SA 4.0", "attribution_required": True}},
            }})
            text, uses_ai = quality_gate.media_credits(tmp)
            self.assertEqual(text, "Imágenes: Bernard Gagnon (CC BY-SA 4.0), autor desconocido (CC BY 2.0), vía Wikimedia Commons y Openverse.")
            self.assertTrue(uses_ai)
            text, uses_ai = quality_gate.media_credits(tmp, merged={2, 4})
            self.assertNotIn("CC BY 2.0", text)
            self.assertFalse(uses_ai, "la escena de IA fusionada no sale en el video")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ai_flag_reaches_every_buffer_post(self):
        publisher = BufferPublisher(token="prueba")
        bundle = SimpleNamespace(
            youtube_shorts=SimpleNamespace(title="T", description="D", tags=["historia"], pinned_comment=""),
            instagram_reels=SimpleNamespace(caption="C", hashtags=[], hook_line="G"),
            tiktok=SimpleNamespace(caption="C", hashtags=[], hook="G"),
        )
        sent = []
        with mock.patch.object(publisher, "_execute_create_post", side_effect=lambda v: sent.append(v) or {"status": "success"}), \
                mock.patch.object(publisher, "get_channels", return_value={p: {"id": p} for p in ("youtube", "instagram", "tiktok")}), \
                mock.patch("src.buffer_publisher.upload_video_to_public_host", return_value="https://v.mp4"):
            publisher.publish_all_platforms(Path("v.mp4"), bundle, ai_generated=True)
        flags = [next(iter(v["input"]["metadata"].values()))["isAiGenerated"] for v in sent]
        self.assertEqual(flags, [True, True, True])

    def test_model_discovery_drops_missing_and_adds_new_models(self):
        from src.config import TEXT_MODEL_PATTERN, TTS_MODEL_PATTERN, with_discovered_models
        available = ["gemini-3.8-flash", "gemini-3.9-flash", "gemini-3.9-flash-lite", "gemini-2.5-pro",
                     "gemini-3.9-flash-tts", "gemini-3.1-flash-image", "gemini-flash-lite-latest"]
        text = with_discovered_models(["gemini-3.8-flash", "gemini-3.7-flash"], TEXT_MODEL_PATTERN, available)
        self.assertEqual(text, ["gemini-3.8-flash", "gemini-3.9-flash", "gemini-3.9-flash-lite", "gemini-flash-lite-latest"])
        self.assertEqual(with_discovered_models(["gemini-3.8-flash-tts"], TTS_MODEL_PATTERN, available), ["gemini-3.9-flash-tts"])
        self.assertEqual(with_discovered_models(["a"], TEXT_MODEL_PATTERN, None), ["a"], "sin red se usa la lista configurada")


class InstagramRetryTests(unittest.TestCase):
    def bundle(self):
        return SimpleNamespace(
            instagram_reels=SimpleNamespace(caption="Texto", hashtags=["#historia"], hook_line="Gancho"),
            youtube_shorts=SimpleNamespace(pinned_comment="¿Lo sabías?"),
        )

    def test_paid_plan_error_retries_without_first_comment(self):
        publisher = BufferPublisher(token="prueba")
        calls = []

        def fake_post(variables):
            calls.append(json.loads(json.dumps(variables["input"]["metadata"]["instagram"])))
            if len(calls) == 1:
                return {"status": "error", "message": "First comment requires a paid plan"}
            return {"status": "success", "post_id": "abc"}

        with mock.patch.object(publisher, "_execute_create_post", side_effect=fake_post):
            result = publisher.publish_instagram("canal", "https://video.mp4", self.bundle())
        self.assertEqual(result["status"], "success")
        self.assertIn("firstComment", calls[0])
        self.assertNotIn("firstComment", calls[1])

    def test_other_errors_are_not_retried(self):
        publisher = BufferPublisher(token="prueba")
        with mock.patch.object(publisher, "_execute_create_post",
                               return_value={"status": "error", "message": "Invalid video"}) as post:
            result = publisher.publish_instagram("canal", "https://video.mp4", self.bundle())
        self.assertEqual(post.call_count, 1)
        self.assertEqual(result["status"], "error")


class PublicationRecordTests(unittest.TestCase):
    def setUp(self):
        self.job = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.job, ignore_errors=True)

    def read(self) -> dict:
        return json.loads((self.job / "publication.json").read_text(encoding="utf-8"))

    def test_retry_on_one_platform_keeps_the_others(self):
        main.save_publication(self.job, ["youtube", "instagram"], {
            "youtube": {"status": "success", "post_id": "yt1"},
            "instagram": {"status": "error", "message": "First comment requires a paid plan"},
        })
        main.save_publication(self.job, ["instagram"], {"instagram": {"status": "success", "post_id": "ig2"}})
        platforms = self.read()["platforms"]
        self.assertEqual(platforms["youtube"]["post_id"], "yt1")
        self.assertEqual(platforms["instagram"], {"status": "success", "post_id": "ig2", "message": None})

    def test_general_failure_reason_is_saved_per_platform(self):
        main.save_publication(self.job, ["tiktok"], {"buffer": {"status": "error", "message": "No fue posible alojar el video"}})
        self.assertEqual(self.read()["platforms"]["tiktok"]["message"], "No fue posible alojar el video")
        main.save_publication(self.job, ["youtube"], {"error": "Fallo al redactar los textos o publicar: sin red"})
        self.assertIn("redactar", self.read()["platforms"]["youtube"]["message"])
        main.save_publication(self.job, ["instagram"], None)
        self.assertEqual(self.read()["platforms"]["instagram"]["status"], "error")

    def test_template_texts_are_recorded(self):
        main.save_publication(self.job, ["youtube"], {"youtube": {"status": "success"}, "copy_source": "plantilla"})
        self.assertEqual(self.read()["copy_source"], "plantilla")

    def test_publish_failure_does_not_mark_job_published(self):
        (self.job / "quality_report.json").write_text(json.dumps({"status": "passed", "topic": "t", "video_path": "x.mp4"}))
        (self.job / "script.json").write_text(json.dumps({
            "metadata": {"title": "t", "description": "d", "tags": []}, "narration_full": "n",
            "scenes": [scene(1, 3.0).model_dump()]}), encoding="utf-8")
        with mock.patch.object(main, "publish_social", return_value={"error": "sin red"}):
            ok = main.publish_job(self.job, ["youtube"], None, None)
        self.assertFalse(ok)
        self.assertEqual(json.loads((self.job / "quality_report.json").read_text())["status"], "passed")


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg no está instalado")
class AssemblyDurationTests(unittest.TestCase):
    def test_video_lasts_as_long_as_the_narration(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            images = make_images(tmp, 3, size=(540, 960))
            audio = tmp / "narracion.mp3"
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=9", str(audio)],
                           check=True, capture_output=True)
            scenes = [scene(1, 3.0, 0), scene(2, 3.0, 3), scene(3, 3.0, 6)]
            out = assemble_video(scenes=scenes, image_paths=images, audio_path=audio, output_video_path=tmp / "v.mp4",
                                 burn_subtitles=False, aspect_ratio="9:16", temp_dir=tmp / "temp",
                                 hook_text="Gancho", closing_question="¿Pregunta?")
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                                   check=True, capture_output=True, text=True)
            self.assertAlmostEqual(float(probe.stdout), 9.0, delta=0.25)
            self.assertEqual(list((tmp / "temp").glob("clip_*.mp4")), [], "los clips temporales deben borrarse")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
