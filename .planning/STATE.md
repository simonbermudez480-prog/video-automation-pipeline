# Current Project State

## Status
- **Current Phase:** Phase 7 Complete (Multi-Platform Publishing: YouTube Shorts, Instagram Reels, TikTok & AI Social Copywriter)
- **Active Task:** Phase 7 Finalized and Verified. Ready for new feature requests or production scaling.
- **Completed:**
  - `src/social_copywriter.py`: Modelos Pydantic (`YouTubeShortsPost`, `InstagramReelsPost`, `TikTokPost`, `SocialBundle`), integración con Gemini / DeepSeek y fallback analítico determinista con títulos <58 chars con `#Shorts`, hooks para Instagram Reels y TikTok con hashtags categorizados.
  - `src/buffer_publisher.py`: Conector oficial con Buffer GraphQL API (`https://api.buffer.com`). Autodescubrimiento dinámico de canales para YouTube Shorts ("Historia y curiosidades"), Instagram Reels ("@historiaycultura2411") y TikTok ("@historiaycultura2411"). Subida de video a hosting temporal público para ingesta en Buffer y mutación `createPost` con copys específicos por red social.
  - Integración en `src/multiplatform_publisher.py` y `main.py` CLI con `--publish-all`.
  - Verificación en vivo: 3 publicaciones exitosas confirmadas con Post IDs reales en Buffer (`6ac19863fec59133948d0678`, `6ac19868814d657011dba348`, `6ac198755829d2489afd673f`).

## Decisions & Conventions
- **LLM Engine:** Default to Gemini 2.5 Flash via `google-genai` SDK with DeepSeek API option via OpenAI client protocol.
- **Audio TTS:** ElevenLabs API with seamless automatic fallback to Microsoft Edge TTS (`edge-tts`) so the pipeline runs even without an active paid ElevenLabs subscription.
- **Audio Processing:** Local `faster-whisper` for fast word/segment timestamp extraction without external cloud API cost, plus `pydub` for silence detection.
- **Image Generation:** Google Imagen 3 (`google-genai`), Fal.ai / Replicate / Stability API, with free fallback (`pollinations`) for instantaneous testing.
- **Video Composition:** Pure `FFmpeg` CLI commands via Python `subprocess` with escaping for Windows paths, alternating Ken Burns zoompan filters per scene, 1080p @ 30 FPS.
- **YouTube API:** Official `google-api-python-client` with local OAuth token persistence.
