# Current Project State

## Status
- **Current Phase:** Phase 9 Complete (Human-Grade Gemini 3.8 Flash TTS & Acoustic Mastering Chain)
- **Active Task:** Phase 9 Finalized and Verified. Ready for ultra-expressive automated video production.
- **Completed:**
  - `src/config.py`: Proveedor TTS nativo `gemini` configurado como predeterminado con modelo `gemini-3.8-flash-tts` y voz expresiva `Puck`. Cascada de fallback TTS configurada (`gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, `gemini-3.1-flash-tts-preview`, `gemini-2.5-flash-preview-tts`), parámetros para Edge-TTS (`es-MX-DaliaNeural`, `+10%`), y cadena acústica `ENABLE_AUDIO_MASTERING=True`.
  - `src/voice_synthesizer.py`: Integración completa de `_synthesize_gemini_tts` y `_synthesize_gemini_tts_cascade` para generar audio humano nativo PCM 24kHz. Implementación de `_master_audio` vía FFmpeg con filtros de High-Pass (80Hz), realce de presencia vocal (+2.5dB @ 3.5kHz), compresión dinámica (3:1 @ -18dB) y normalización EBU R128 (-14 LUFS). Jerarquía de fallbacks robusta y tolerante a fallos.
  - `main.py`: Argumentos `--tts-provider {gemini, elevenlabs, edge-tts}` y `--tts-voice` expuestos en CLI y propagados a `synthesize_voice`.
  - `.env` & `.env.example`: Sincronización de configuraciones de voz expresiva y parámetros acústicos.
  - Pruebas y verificación: Síntesis de prueba con Gemini 3.8 Flash TTS ("Puck") completada y masterizada a 145 KB MP3 (-14 LUFS), y verificación de alineación con `faster-whisper` superada con 0.99 de confianza y generación limpia de subtítulos .srt.
  - Producción y Publicación Pública: Video sobre "El misterio de D.B. Cooper: El hombre que se esfumo de un avion con 200.000 dolares" (9:16 vertical, 1080x1920, 67.48 MB) producido con voz humana Gemini 3.8 Flash TTS ("Puck") y publicado con éxito en los 3 canales (YouTube Shorts [Post ID: 6ac85921987e694c3c3d215e], Instagram Reels [Post ID: 6ac8592504f06b2e8f7757c7] y TikTok [Post ID: 6ac8592f987e694c3c3d26a8]) vía Buffer GraphQL API y GitHub CDN.

## Decisions & Conventions
- **LLM Engine:** Cascada multi-modelo dinámica con Gemini Flash (3.8 -> 3.7 -> 3.6 -> 3.5 -> 2.5 -> flash-latest -> 3.5-lite -> 2.5-lite), con DeepSeek como opción secundaria y heurísticas bloqueadas (`ALLOW_HEURISTIC_SCRIPTS = False`).
- **Audio TTS:** Gemini 3.8 Flash TTS nativo como proveedor primario (ultra-expresivo, humano, costo cero) con cascada de modelos Flash TTS -> ElevenLabs -> Edge-TTS (con aceleración +10% y voz conversacional).
- **Masterización de Audio:** FFmpeg con ecualización de presencia (3.5kHz), compresión dinámica y normalización estándar TikTok a -14 LUFS.
- **Audio Processing:** Local `faster-whisper` para timestamps exactos por palabra y subtítulos con PlayResY=1920 y MarginV=360.
- **Image Generation:** Google Imagen 3 (`google-genai`), Fal.ai / Replicate / Stability API, y fallback con Pollinations.
- **Video Composition:** FFmpeg nativo con efectos Ken Burns dinámicos alternados por escena en formato vertical 9:16 (1080x1920 @ 30 FPS).
- **Publicación:** Buffer GraphQL API multicanal para YouTube Shorts, Instagram Reels y TikTok con CDN de entrega rápida.

