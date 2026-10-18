# Current Project State

## Status
- **Current Phase:** Phases 15–21 completas y commiteadas (salvo 20.6). Phase 22 (Mejoras de calidad tras la auditoría) — registrada, siguiente.
- **Active Task:** Fase 22 — Bloques 1 (205135d), 2 (5922bc4), 3 (4d10415) y 4 hechos; Bloque 4 sin commit (22.7 tiempos + miniaturas JPEG, 22.9 voto por mayoría; 23 pruebas OK). 22.8 espera aprobación del usuario (`.planning/EXPERIMENTO_DURACION.md`). Antes de cada cambio: `python -m unittest discover -s tests`. Siguiente: Bloque 5 (mantenimiento). Nota: la revisión visual sufre esperas largas (timeouts de Gemini) → medir en 22.7; Pollinations sin saldo el 2026-10-18. Fase 21 commiteada (c8f28c2); quedan 5 videos por re-publicar en Instagram desde Historial (lo hace el usuario).
- **Fase 15 — resultado clave:** con el control activo, las fuentes gratuitas actuales (Pexels/Wikimedia con búsqueda simple) solo consiguen 4/13 imágenes válidas para el Emú (1932): casi todo el stock es moderno. El bloqueo funciona; lo que falta es mejor búsqueda de archivo (Fase 16). Nuevo módulo `src/quality_gate.py`; publicar ahora pide confirmación humana por defecto (`--no-approval` para automatizar) y deja `quality_report.json` en la carpeta del job y la hoja de contacto en `output/review/`.
- **Riesgo:** la cuota gratuita de visión por modelo es pequeña (2 modelos se agotaron en 4 llamadas el 2026-10-15). Si se agota, las escenas quedan `unaudited` y la publicación se bloquea.
- **Next Actions:**
  0. Commit de Pollinations con clave + reanudación de cascada (sin commit). Créditos de licencias (16.5b) antes de publicar Chernóbil (fotos IAEA CC BY-SA). Opcional: crear la tarea programada de Windows (README) y producir con `--no-approval` si se quiere publicación sin intervención.
  1. Phase 16: 16.6, producir el video del Emú completo sin publicar (con cuota de visión disponible) y revisar la hoja de contacto y los frames.
  2. 16.5b: créditos de licencias en la descripción.
  2. Usuario: crear cuenta gratuita de Cloudflare y token de Workers AI (solo si se quiere IA para huecos, tarea 16.5).
- **Backup previo a cambios (2026-10-15):** `backups/repo_history_20261015_pre_phase15.bundle` (historial git completo) y `backups/backup_pre_phase15_20261015.zip` (árbol de trabajo con cambios sin commitear, `.env`, assets; sin `venv`, `output/`, `assets/temp`, `assets/jobs`).

## Audit 2026-10-15 — Findings
- El video publicado "La Guerra del Emú" tiene problemas visuales que la verificación por frames sueltos no detectó: escenas 1–2 (gancho, ~21 s) son degradados procedurales; escenas 6 y 10 son la misma imagen; escena 5 muestra un soldado moderno; escena 12 un perro en una playa; escena 3 un buzón en vez de un telegrama.
- Causas: Pollinations sin clave devuelve HTTP 402 (298× en el log); los temas bélicos omiten la IA sin clave; la cuota de Gemini Vision se agota a mitad del lote y Pexels pasa a aprobarse solo por metadatos; Picsum aporta paisajes aleatorios; no existe bloqueo antes de publicar; `character_anchor` nunca se usa.
- Lección: verificar la hoja de contacto completa de todas las escenas, no frames sueltos.

## Completed (history)
  - Publicación de "El hombre que vendió un país que no existía (Gregor MacGregor y Poyais, 1822)" (2026-10-15): `output/el_hombre_que_vendio_un_pais_que_no_9x16_20261015_093538.mp4` (153,08 s; control superado con 11/13 + fusiones 4→3 y 6→5; look archival). Vía Buffer:
    - YouTube: https://www.youtube.com/watch?v=BvL8hf-yAS8 (Post ID `6ad0e052109a34529aa1d6e0`)
    - Instagram Reels: https://www.instagram.com/reel/DehJyJaDk-C/ (Post ID `6ad0e056a0df5987c75e40ed`)
    - TikTok: https://tiktok.com/@historiaycultura2411/video/7696898485110558004 (Post ID `6ad0e06110fd2689b3e5592c`)
    - Publicado tal como estaba por decisión del usuario: la escena 11 (cartel "WANTED" de IA) tiene texto inventado y mal escrito que el revisor aprobó. Sin créditos: 2 imágenes CC BY-SA 4.0 / CC BY 4.0.
    - Fallo detectado: `extract_topics` separa `--topic` por comas, así que "…Poyais, 1822)" generó un segundo video basura ("1822)"); se borró sin publicar.
  - Publicación de "La explosión de Chernóbil (1986)" (2026-10-15), primer video con las fases 15–17: `output/la_explosion_de_chernobil_1986_9x16_v2.mp4` (126,04 s; control superado con 11/13 imágenes + 2 fusiones). Publicado vía Buffer:
    - YouTube: https://www.youtube.com/watch?v=EuJT_8RnMcg (Post ID `6ad08ae75ca32ad3c7eca0e7`)
    - Instagram Reels: https://www.instagram.com/reel/DeggFAWiqQJ/ (Post ID `6ad08aeb6295ecc932f5390c`)
    - TikTok: https://tiktok.com/@historiaycultura2411/video/7696804573444459783 (Post ID `6ad08af6de79014f82c64029`)
    - **Publicado sin créditos de licencia por decisión del usuario**, aunque usa fotos de la IAEA con CC BY-SA 2.0 que exigen atribución (16.5b pendiente).
    - Primer intento fallido: disco lleno (0,8 GB libres) → falló el CDN de GitHub y quedó un `_web.mp4` truncado. Corregido en `buffer_publisher.py`: solo se reutiliza el video optimizado si FFmpeg puede leerlo y se borran restos de intentos fallidos (sin commit).
  - Producción y Publicación de "La Guerra del Emú en Australia (1932)": Video master de 43.18 MB (`la_guerra_del_emu_en_australia_1932_9x16_20261014_085816.mp4`, 126.67s @ 1080x1920), optimizado a 10.77 MB web (`_web.mp4`), alojado en CDN de GitHub y publicado exitosamente en las 3 plataformas vía Buffer GraphQL API:
    - YouTube Shorts: `https://www.youtube.com/shorts/ESQAYfPmYHg` (Post ID: `6acf800a145f884d2ce0c9d1`)
    - Instagram Reels: `https://www.instagram.com/reel/DeedxRyEf2P/` (Post ID: `6acf800dd3e18071d3973615`)
    - TikTok: `https://tiktok.com/@historiaycultura2411/video/7696510953705262388` (Post ID: `6acf8019ba9c302b3b8400e5`)
  - Verificación visual multimodal: Inspección directa con `view_file` de frames clave en `screenshots/emu_frame_36s.png` (ametralladora Lewis y cartuchera militar), `emu_frame_55s.png` (casquillos de bala percutidos), y `emu_frame_66s.png` (primer plano del emú vigía en el desierto). Se verificó legibilidad óptima de subtítulos con contorno oscuro, alto contraste WCAG AAA y safe margin vertical (`MarginV=360`).
  - Producción y Publicación de "El Lobo de Wall Street: Ascenso y Caída de Jordan Belfort" (YouTube Shorts, Instagram Reels, TikTok).
  - Producción y Publicación previa de "La Caída de Osama Bin Laden" (YouTube, Instagram, TikTok).
  - Producción y Publicación de "El Emperador Norton I" (YouTube, Instagram, TikTok).

## Decisions & Conventions
- **LLM Engine:** Cascada multi-modelo dinámica con Gemini Flash (3.8 -> 3.7 -> 3.6 -> 3.5 -> 2.5 -> flash-latest -> 3.5-lite -> 2.5-lite), con DeepSeek como opción secundaria y heurísticas bloqueadas (`ALLOW_HEURISTIC_SCRIPTS = False`).
- **Visual Bible & Prompt Sanitization:** Cada video define un `VisualContract` mandatorio al inicio del guion. Toda referencia vertical usa `vertical 9:16 framing` (cero tokens 'portrait' para evitar distorsiones de IA). Planos de entorno y macro incorporan siempre directivas explícitas de escenas deshabitadas.
- **Multimodal Visual QA Gatekeeper:** Ninguna imagen entra al montaje final sin ser auditada por Gemini Vision para descartar marcas de agua (`pollinations.ai`, `shutterstock`), humanos espurios o anacronismos absurdos. Si la imagen falla la auditoría, se reintenta con prompt negativo o se escala al rescate verificado (Pexels / Picsum auditado / Fondo procedural cinemático). **[Será reemplazado en Fases 15–16]**: la cascada mixta se sustituye por una sola fuente.
- **Image Source Strategy (decidido 2026-10-15, revisado):** Restricción de costo USD 0 por video. Híbrido gratuito: fotos de archivo real (Wikimedia / Library of Congress / Pexels) como fuente principal, gradación uniforme por video en postproducción para la coherencia, e IA gratuita solo para huecos. Se descartó la opción 1 (IA con referencias, de pago) y la generación local (sin GPU dedicada).
- **Audio TTS:** Gemini 3.8 Flash TTS nativo como proveedor primario (ultra-expresivo, humano, costo cero) con cascada de modelos Flash TTS -> ElevenLabs -> Edge-TTS (con aceleración +10% y voz conversacional).
- **Masterización de Audio:** FFmpeg con ecualización de presencia (3.5kHz), compresión dinámica y normalización estándar TikTok a -14 LUFS.
- **Audio Processing:** Local `faster-whisper` para timestamps exactos por palabra y subtítulos con PlayResY=1920 y MarginV=360.
- **Video Composition:** FFmpeg nativo con efectos Ken Burns dinámicos alternados por escena en formato vertical 9:16 (1080x1920 @ 30 FPS).
- **Publicación:** Buffer GraphQL API multicanal para YouTube Shorts, Instagram Reels y TikTok con CDN de entrega rápida.


