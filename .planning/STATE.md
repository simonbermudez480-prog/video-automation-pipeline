# Current Project State

## Status
- **Current Phase:** Phase 10 Complete (Visual Coherence & Cinematic Style Matrix - Option A)
- **Active Task:** Phase 10 Finalized and Verified. Ready for producing videos with unified cinematic aesthetic and anti-face-morphing direction.
- **Completed:**
  - `src/script_generator.py`: Modelo `VisualContract` integrado en `ScriptOutput` (`era_setting`, `art_style`, `color_palette`, `lighting_atmosphere`, `character_anchor`, `shot_progression_rules`). Atributo `shot_type` en cada escena (`macro_detail`, `over_the_shoulder`, `silhouette_backlight`, `environmental_wide`, `dramatic_close_up`).
  - `src/script_generator.py`: Nuevo System Prompt de dirección cinematográfica y fotografía documental 35mm (Kodak Vision3 500T), eliminando términos genéricos ('sci-fi concept art') e introduciendo reglas estrictas anti-face-morphing.
  - `src/image_generator.py`: Función `_build_cohesive_prompt` que inyecta la biblia visual en cada escena, ampliación de prompt en Pollinations (hasta 65 palabras), y encadenamiento determinista de semillas (`seed`) por tema.
  - `src/image_generator.py`: Soporte dinámico para aspecto 9:16 en Google Imagen 3 (`imagen-3.0-generate-002`) y Fal.ai Flux Schnell.
  - `main.py`: Propagación de `visual_contract` desde el guion hasta el orquestador de imágenes `generate_images_for_scenes`.
  - Pruebas y verificación: Generación en vivo con Gemini 3.8 Flash de un guion documental con `VisualContract` completo (estilo 35mm, paleta unificada de 3 tonos, dirección sin rostros mutantes) validada y probada al 100%.

## Decisions & Conventions
- **LLM Engine:** Cascada multi-modelo dinámica con Gemini Flash (3.8 -> 3.7 -> 3.6 -> 3.5 -> 2.5 -> flash-latest -> 3.5-lite -> 2.5-lite), con DeepSeek como opción secundaria y heurísticas bloqueadas (`ALLOW_HEURISTIC_SCRIPTS = False`).
- **Visual Bible & Coherence:** Cada video define un `VisualContract` mandatorio al inicio del guion, con paleta cromática unificada de 3 tonos, textura analógica Kodak Vision3 500T y dirección de cámara con planos detalle/siluetas/over-the-shoulder para evitar face-morphing de personajes.
- **Audio TTS:** Gemini 3.8 Flash TTS nativo como proveedor primario (ultra-expresivo, humano, costo cero) con cascada de modelos Flash TTS -> ElevenLabs -> Edge-TTS (con aceleración +10% y voz conversacional).
- **Masterización de Audio:** FFmpeg con ecualización de presencia (3.5kHz), compresión dinámica y normalización estándar TikTok a -14 LUFS.
- **Audio Processing:** Local `faster-whisper` para timestamps exactos por palabra y subtítulos con PlayResY=1920 y MarginV=360.
- **Image Generation:** Google Imagen 3 (`google-genai`), Fal.ai / Replicate / Stability API, y fallback con Pollinations (Flux con semilla coherente y enriquecimiento estilístico).
- **Video Composition:** FFmpeg nativo con efectos Ken Burns dinámicos alternados por escena en formato vertical 9:16 (1080x1920 @ 30 FPS).
- **Publicación:** Buffer GraphQL API multicanal para YouTube Shorts, Instagram Reels y TikTok con CDN de entrega rápida.

