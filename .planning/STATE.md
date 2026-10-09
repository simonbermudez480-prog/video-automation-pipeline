# Current Project State

## Status
- **Current Phase:** Phase 11 Complete (Multimodal Vision QA Gatekeeper, Stock Pexels/Picsum Hybrid & Prompt Poisoning Sanitizer)
- **Active Task:** Phase 11 Finalized and Verified. All generated/downloaded assets are now audited in real-time by Gemini Vision before entering video assembly, prompts are sanitized against portrait poisoning, and verified stock cascades protect against random images.
- **Completed:**
  - `src/script_generator.py`: Erradicación absoluta de la raíz 'portrait' en los prompts de encuadre vertical; sustitución por `vertical 9:16 framing, mobile format` e inyección obligatoria de restricciones anti-hallucination (`uninhabited scene, empty surroundings, no humans, no people, inanimate subject`) para planos generales y macro.
  - `src/image_generator.py`: Sanitización proactiva de prompts con `re.sub(r"\bportraits?\b", "cinematic framing", ...)` garantizando que ningún modelo de difusión interprete orientación como retrato de estudio.
  - `src/image_generator.py`: Implementación de `audit_image_with_gemini_vision`, auditor multimodal que evalúa en tiempo real cada imagen generada o descargada ante 3 descalificadores críticos (`UNWANTED_HUMAN`, `WATERMARK_OR_TEXT`, `ABSURD_DISSONANCE`) utilizando una cascada de modelos Gemini Flash (`gemini-2.5-flash` -> `gemini-3.8-flash` -> `gemini-3.7-flash` -> `gemini-3.5-flash`).
  - `src/image_generator.py`: Implementación de `_fetch_from_pexels` para búsqueda contextual de stock documental en alta definición (orientación vertical 9:16) con `PEXELS_API_KEY`.
  - `src/image_generator.py`: Implementación de `_fetch_from_picsum_verified`, reemplazando el rescate ciego de Picsum por un sistema con semillas temáticas curadas (paisajes, arquitectura, texturas) y validación estricta con Gemini Vision. Si la foto no es coherente, se descarta y escala al fondo procedural cinemático.
  - `src/image_generator.py`: Lógica de reintento inteligente en IA generativa (Pollinations Flux): si el Gatekeeper detecta personas no solicitadas o marcas de agua, reintenta con un prompt correctivo reforzado (`uninhabited scene, absolutely no humans, clean frame, no watermarks`) antes de escalar a los fallbacks.
  - `src/config.py`: Variables de configuración añadidas (`ENABLE_IMAGE_QA_GATEKEEPER`, `GEMINI_VISION_FALLBACK_MODELS`, método `get_gemini_vision_candidates`).
  - Pruebas y verificación: Ejecución de tests empíricos con las imágenes reales del lago Toplitz, validando que el Gatekeeper detecta y rechaza con 100% de precisión a la mujer (`scene_003.png`) y al joven en el campo de margaritas (`scene_004.png`), y comprobación en vivo de que el pipeline previene imágenes absurdas.

## Decisions & Conventions
- **LLM Engine:** Cascada multi-modelo dinámica con Gemini Flash (3.8 -> 3.7 -> 3.6 -> 3.5 -> 2.5 -> flash-latest -> 3.5-lite -> 2.5-lite), con DeepSeek como opción secundaria y heurísticas bloqueadas (`ALLOW_HEURISTIC_SCRIPTS = False`).
- **Visual Bible & Prompt Sanitization:** Cada video define un `VisualContract` mandatorio al inicio del guion. Toda referencia vertical usa `vertical 9:16 framing` (cero tokens 'portrait' para evitar distorsiones de IA). Planos de entorno y macro incorporan siempre directivas explícitas de escenas deshabitadas.
- **Multimodal Visual QA Gatekeeper:** Ninguna imagen entra al montaje final sin ser auditada por Gemini Vision para descartar marcas de agua (`pollinations.ai`, `shutterstock`), humanos espurios o anacronismos absurdos. Si la imagen falla la auditoría, se reintenta con prompt negativo o se escala al rescate verificado (Pexels / Picsum auditado / Fondo procedural cinemático).
- **Audio TTS:** Gemini 3.8 Flash TTS nativo como proveedor primario (ultra-expresivo, humano, costo cero) con cascada de modelos Flash TTS -> ElevenLabs -> Edge-TTS (con aceleración +10% y voz conversacional).
- **Masterización de Audio:** FFmpeg con ecualización de presencia (3.5kHz), compresión dinámica y normalización estándar TikTok a -14 LUFS.
- **Audio Processing:** Local `faster-whisper` para timestamps exactos por palabra y subtítulos con PlayResY=1920 y MarginV=360.
- **Video Composition:** FFmpeg nativo con efectos Ken Burns dinámicos alternados por escena en formato vertical 9:16 (1080x1920 @ 30 FPS).
- **Publicación:** Buffer GraphQL API multicanal para YouTube Shorts, Instagram Reels y TikTok con CDN de entrega rápida.


