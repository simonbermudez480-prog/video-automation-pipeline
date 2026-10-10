# Current Project State

## Status
- **Current Phase:** Phase 12 Complete & Operational
- **Active Task:** "El espía con 27 identidades inventadas: Juan Pujol García, 'Garbo'" produced, visually audited, and successfully published to YouTube Shorts, Instagram Reels, and TikTok.
- **Completed:**
  - `src/buffer_publisher.py`: Resiliencia con `_post_with_retry` ejecutada sin contratiempos; publicación directa y simultánea en las 3 plataformas.
  - `src/image_generator.py`: Auditoría visual con `_EXHAUSTED_VISION_MODELS` y Guardián de Metadatos Anti-Poisoning funcionando a máxima velocidad (tiempo de producción reducido a ~25 min).
  - Producción y Publicación de "El Agente Garbo": Video de 22.13 MB master (`garbo_9x16_20261010_122014.mp4`), optimizado a 5.03 MB web (`_web.mp4`), hosteado en CDN de GitHub y publicado a través de Buffer API:
    - YouTube Shorts: `6aca67c6f91f772d459cf38b`
    - Instagram Reels: `6aca67c9f91f772d459cf3ef`
    - TikTok: `6aca67d4f91f772d459cf594`
  - Verificación visual multimodal: Inspección directa con `view_file` de 11 escenas fotográficas reales de alta fidelidad documental (máquina de escribir mecánica vintage con reporte 'Contact', túneles subterráneos de Londres, mapas de operaciones militares con brújula y pines, escritorio clásico con libro antiguo y lámpara de bronce, y maletas de viaje con pasaporte alusivas a su escape y vida anónima en Venezuela).

## Decisions & Conventions
- **LLM Engine:** Cascada multi-modelo dinámica con Gemini Flash (3.8 -> 3.7 -> 3.6 -> 3.5 -> 2.5 -> flash-latest -> 3.5-lite -> 2.5-lite), con DeepSeek como opción secundaria y heurísticas bloqueadas (`ALLOW_HEURISTIC_SCRIPTS = False`).
- **Visual Bible & Prompt Sanitization:** Cada video define un `VisualContract` mandatorio al inicio del guion. Toda referencia vertical usa `vertical 9:16 framing` (cero tokens 'portrait' para evitar distorsiones de IA). Planos de entorno y macro incorporan siempre directivas explícitas de escenas deshabitadas.
- **Multimodal Visual QA Gatekeeper:** Ninguna imagen entra al montaje final sin ser auditada por Gemini Vision para descartar marcas de agua (`pollinations.ai`, `shutterstock`), humanos espurios o anacronismos absurdos. Si la imagen falla la auditoría, se reintenta con prompt negativo o se escala al rescate verificado (Pexels / Picsum auditado / Fondo procedural cinemático).
- **Audio TTS:** Gemini 3.8 Flash TTS nativo como proveedor primario (ultra-expresivo, humano, costo cero) con cascada de modelos Flash TTS -> ElevenLabs -> Edge-TTS (con aceleración +10% y voz conversacional).
- **Masterización de Audio:** FFmpeg con ecualización de presencia (3.5kHz), compresión dinámica y normalización estándar TikTok a -14 LUFS.
- **Audio Processing:** Local `faster-whisper` para timestamps exactos por palabra y subtítulos con PlayResY=1920 y MarginV=360.
- **Video Composition:** FFmpeg nativo con efectos Ken Burns dinámicos alternados por escena en formato vertical 9:16 (1080x1920 @ 30 FPS).
- **Publicación:** Buffer GraphQL API multicanal para YouTube Shorts, Instagram Reels y TikTok con CDN de entrega rápida.


