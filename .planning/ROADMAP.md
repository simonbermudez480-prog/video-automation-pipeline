# Implementation Roadmap

- [x] **Phase 1: Environment & Project Foundation**
  - Configuración de dependencias (`requirements.txt`).
  - Plantilla de variables de entorno (`.env.example`).
  - Módulo de configuración global (`src/config.py`).
  - Utilidades de logging estructurado (`src/logger.py`).

- [x] **Phase 2: Script & Prompt Generator**
  - Implementación de `src/script_generator.py` (Gemini & DeepSeek con fallback inteligente).
  - Modelos de datos estructurados con Pydantic (`Scene`, `ScriptOutput`, `VideoMetadata`).
  - Prompts del sistema calibrados para estilo documental y CTR.
  - Verificación y prueba unitaria.

- [x] **Phase 3: Voice Synthesizer & Audio Alignment**
  - Implementación de `src/voice_synthesizer.py` (ElevenLabs + Edge-TTS fallback automático).
  - Implementación de `src/audio_processor.py` (Faster-Whisper + Pydub + generador SRT).
  - Algoritmo de alineación de texto a timestamps por escena.

- [x] **Phase 4: Coherent Image Generation**
  - Implementación de `src/image_generator.py` (Google Imagen 3, Fal, Stability, Pollinations y FFmpeg procedural).
  - Pipeline de descarga y guardado en `assets/images/scene_{idx:03d}.png` 16:9.

- [x] **Phase 5: Dynamic Video Assembly (FFmpeg)**
  - Implementación de `src/video_assembler.py`.
  - Construcción de filtros Ken Burns (`zoompan` dinámico alternado).
  - Ensamble de video por escenas sincronizadas con audio y subtítulos quemados en 1080p 30fps.

- [x] **Phase 6: YouTube Publishing & Orchestrator CLI**
  - Implementación de `src/youtube_uploader.py` (OAuth2 + YouTube Data API v3).
  - CLI unificada en `main.py` con argumentos completos (`--topic`, `--dry-run`, `--skip-*`, etc.).
  - Montaje cinematográfico a pantalla completa en 1080p 30fps con Ken Burns dinámico y fundidos cruzados.
  - Subtítulos de alto contraste quemados.
  - Módulo de avatar revertido por requerimiento del usuario (producción limpia a pantalla completa).

- [x] **Phase 7: Multi-Platform Publishing (YouTube Shorts, Instagram Reels, TikTok) & Social Copywriter**
  - Implementación de `src/social_copywriter.py` (generación con IA de copies y hashtags especializados por plataforma con validación Pydantic y fallback determinista).
  - Implementación de `src/multiplatform_publisher.py` (conectores API directos para YouTube, Instagram y TikTok + generador de paquetes listos `output/social_packages/<slug>_<timestamp>/`).
  - Actualización de configuración en `src/config.py` y `.env.example` con credenciales de Instagram, TikTok y Webhook.
  - Integración en `main.py` con flags `--publish-all`, `--publish-platforms`, `--no-social-pack` y exportación de metadatos.
  - Verificación end-to-end exitosa con video vertical 9:16 y paquete social generado en disco.

- [x] **Phase 8: Resilient Gemini Model Cascade & Anti-Heuristic AI Generation**
  - Implementación de cascada dinámica multi-modelo en `src/config.py`: `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-2.5-flash`, `gemini-flash-latest`, `gemini-3.5-flash-lite`, `gemini-2.5-flash-lite`.
  - Integración de `_generate_with_gemini_cascade` en `src/script_generator.py` para sortear rate limits (429) y saturación de demanda (503).
  - Eliminación estricta de heurísticas / plantillas genéricas para guiones (`ALLOW_HEURISTIC_SCRIPTS = False` por defecto).
  - Integración de cascada en `src/social_copywriter.py` para copys y hashtags adaptativos de alta calidad.
  - Verificación en vivo de saltos de cascada ante 503 y generación real validada con `gemini-3.5-flash-lite`.

- [x] **Phase 9: Human-Grade Voice Engine (Gemini 3.8 Flash TTS & Acoustic Mastering Chain)**
  - Síntesis nativa ultra-humana y expresiva con Google Gemini 3.8 Flash TTS (`gemini-3.8-flash-tts`) y voces predefinidas de alta emotividad (`Puck`, `Charon`, `Aoede`, `Fenrir`).
  - Cascada de resiliencia multi-modelo para TTS (`gemini-3.8-flash-tts` -> `gemini-3.8-flash-lite-tts` -> `gemini-3.1-flash-tts-preview` -> `gemini-2.5-flash-preview-tts` -> ElevenLabs -> Edge-TTS).
  - Optimización de Edge-TTS con voz conversacional dinámica (`es-MX-DaliaNeural`) y aceleración de cadencia TikTok a `+10%`.
  - Cadena de masterización acústica por hardware/FFmpeg: High-Pass (80Hz), Boost de presencia en medios/agudos (+2.5dB @ 3.5kHz), compresión dinámica (3:1 @ -18dB) y normalización EBU R128 (-14 LUFS para TikTok/Shorts/Reels).
  - CLI unificada en `main.py` con `--tts-provider {gemini, elevenlabs, edge-tts}` y `--tts-voice <nombre_voz>`.
- [x] **Phase 10: Visual Coherence & Cinematic Style Matrix (Global Style DNA & Detail-Shot Engine)**
  - Implementación del modelo estructurado `VisualContract` (`era_setting`, `art_style`, `color_palette`, `lighting_atmosphere`, `character_anchor`, `shot_progression_rules`).
  - Rediseño de prompts de dirección de fotografía en `src/script_generator.py`: eliminación de etiquetas genéricas 'sci-fi' y adopción de film photography 35mm (Kodak Vision3 500T).
  - Regla estricta Anti Face-Morphing: categorización de planos por escena (`shot_type`: `macro_detail`, `over_the_shoulder`, `silhouette_backlight`, `environmental_wide`) para evitar inconsistencias en personajes.
  - Implementación de `_build_cohesive_prompt` en `src/image_generator.py` para fusionar dinámicamente la biblia visual con cada escena.
  - Ampliación de capacidad de prompt en Pollinations (hasta 65 palabras) y soporte de semillas deterministas encadenadas por tema para coherencia de textura y grano.
  - Soporte dinámico para `aspect_ratio="9:16"` en Google Imagen 3 y Fal.ai Flux.
  - Conexión completa en `main.py` pasando `visual_contract` desde el guion hasta el orquestador de imágenes.
