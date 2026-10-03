# Current Project State

## Status
- **Current Phase:** Phase 7 Complete (Multi-Platform Publishing: YouTube Shorts, Instagram Reels, TikTok & AI Social Copywriter)
- **Active Task:** Phase 7 Finalized and Verified. Ready for new feature requests or production scaling.
- **Completed:**
  - `src/social_copywriter.py`: Modelos Pydantic (`YouTubeShortsPost`, `InstagramReelsPost`, `TikTokPost`, `SocialBundle`), integración con Gemini / DeepSeek y fallback analítico determinista con títulos <58 chars con `#Shorts`, hooks para Instagram Reels y TikTok con hashtags categorizados.
  - `src/multiplatform_publisher.py`: Conectores a YouTube Data API v3, Meta Graph API (Instagram Reels), TikTok Content Posting API, despachador de Webhook y generador offline de paquetes sociales listos para publicar (`output/social_packages/<slug>_<timestamp>/`).
  - Integración en `main.py` CLI (`--publish-all`, `--publish-platforms`, `--no-social-pack`).
  - Configuración y variables en `src/config.py` y `.env.example`.
  - Prueba integral end-to-end completada exitosamente generando video vertical 9:16 y paquete social estructurado para "La Biblioteca De Alejandria".

## Decisions & Conventions
- **LLM Engine:** Default to Gemini 2.5 Flash via `google-genai` SDK with DeepSeek API option via OpenAI client protocol.
- **Audio TTS:** ElevenLabs API with seamless automatic fallback to Microsoft Edge TTS (`edge-tts`) so the pipeline runs even without an active paid ElevenLabs subscription.
- **Audio Processing:** Local `faster-whisper` for fast word/segment timestamp extraction without external cloud API cost, plus `pydub` for silence detection.
- **Image Generation:** Google Imagen 3 (`google-genai`), Fal.ai / Replicate / Stability API, with free fallback (`pollinations`) for instantaneous testing.
- **Video Composition:** Pure `FFmpeg` CLI commands via Python `subprocess` with escaping for Windows paths, alternating Ken Burns zoompan filters per scene, 1080p @ 30 FPS.
- **YouTube API:** Official `google-api-python-client` with local OAuth token persistence.
