# Automated Multimedia Pipeline: Educational Video Generator

## Project Overview
Un pipeline integral en Python 100% automatizado y ejecutable mediante un único comando (`python main.py --topic "Tema del video"`).
Replica el flujo exacto de producción de contenido educativo y documental:
1. **Idea / Tema** -> Generación de guion estructurado por escenas con prompts visuales detallados (DeepSeek / Gemini).
2. **Síntesis de voz** -> Generación de locución fluida y natural (ElevenLabs con fallback automático a Edge-TTS).
3. **Detección de pausas y timestamps** -> Alineación acústica precisa con `faster-whisper` a nivel de palabra/segmento y detección de silencios (`pydub`), generando subtítulos sincronizados (`.srt`).
4. **Generación de imágenes** -> Creación de visuales 16:9 cinematográficos coherentes (Google Imagen / Fal.ai / Replicate / Stability / Pollinations).
5. **Montaje de video dinámico** -> Ensamble con `FFmpeg` aplicando efecto Ken Burns dinámico (zoompan suave alternado por escena), mezcla de audio y quemado de subtítulos a 1080p 30fps.
6. **Publicación en YouTube** -> Subida automática con YouTube Data API v3 (título CTR, descripción, etiquetas y visibilidad configurable: private, unlisted, public).

## Architecture & Technology Stack
- **Lenguaje:** Python 3.12+
- **LLM Guion:** Google Gemini (`google-genai`) / DeepSeek (`openai` API compatible)
- **Voz / TTS:** ElevenLabs API v1 / Microsoft Edge TTS (`edge-tts`)
- **Audio & Timestamps:** `faster-whisper` + `pydub`
- **Generación Visual:** Google Imagen 3 / Fal.ai / Replicate / Stability AI / Pollinations fallback
- **Motor de Video:** `FFmpeg 9.0+` (filtros `zoompan`, `subtitles`, `concat`)
- **YouTube API:** `google-api-python-client`, `google-auth-oauthlib`
- **Configuración y Logs:** `python-dotenv`, `pydantic`, `loguru` / `rich`
