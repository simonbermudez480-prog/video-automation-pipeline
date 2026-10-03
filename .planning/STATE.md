# Current Project State

## Status
- **Current Phase:** Phase 6 (Reverted to Clean Full-Screen Cinematic Documentary)
- **Active Task:** Verification of clean full-screen video without avatar in 1080p @ 30 FPS.
- **Completed:**
  - Avatar update completely reverted upon user request:
    - Removed `src/avatar_generator.py` and avatar assets/frames.
    - Removed avatar overlay filter, circular mask, and avatar inputs from `src/video_assembler.py`.
    - Removed avatar configuration settings from `src/config.py` and `.env.example`.
    - Removed avatar CLI flags (`--avatar`, `--no-avatar`, etc.) from `main.py`.
  - Re-assembled clean final documentary video in `output/video_final.mp4` (2m 59s, 64.17 MB, 1080p @ 30 FPS).
  - Multimodal visual inspection completed via `view_file` on `clean_frame_scene1.jpg`, `clean_frame_scene7.jpg`, and `clean_frame_scene12.jpg` confirming 100% clean full-frame footage without avatar overlay.

## Decisions & Conventions
- **LLM Engine:** Default to Gemini 2.5 Flash via `google-genai` SDK with DeepSeek API option via OpenAI client protocol.
- **Audio TTS:** ElevenLabs API with seamless automatic fallback to Microsoft Edge TTS (`edge-tts`) so the pipeline runs even without an active paid ElevenLabs subscription.
- **Audio Processing:** Local `faster-whisper` for fast word/segment timestamp extraction without external cloud API cost, plus `pydub` for silence detection.
- **Image Generation:** Google Imagen 3 (`google-genai`), Fal.ai / Replicate / Stability API, with free fallback (`pollinations`) for instantaneous testing.
- **Video Composition:** Pure `FFmpeg` CLI commands via Python `subprocess` with escaping for Windows paths, alternating Ken Burns zoompan filters per scene, 1080p @ 30 FPS.
- **YouTube API:** Official `google-api-python-client` with local OAuth token persistence.
