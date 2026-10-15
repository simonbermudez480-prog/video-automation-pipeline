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
- [x] **Phase 11: Multimodal Vision QA Gatekeeper, Stock Pexels/Picsum Hybrid & Prompt Poisoning Sanitizer**
  - **Sanitización de Prompts Anti-Poisoning**: Erradicación absoluta de la raíz 'portrait' en composiciones 9:16 tanto en `src/image_generator.py` como en `src/script_generator.py`, sustituyéndola por `vertical 9:16 framing, mobile safe zone` e inyectando restricciones de planos deshabitados (`uninhabited scene, empty surroundings, no humans, no people, inanimate subject`) para planos generales y macro.
  - **Guardián Multimodal Gemini Vision (`audit_image_with_gemini_vision`)**: Auditoría visual automática antes del ensamblaje (detección en tiempo real de marcas de agua `pollinations.ai`, humanos fuera de contexto y anacronismos absurdos) con cascada de modelos Gemini Flash (`gemini-2.5-flash`, `gemini-3.8-flash`, etc.).
  - **Híbrido de Stock Pexels & Picsum Verificado**: Búsqueda contextual en Pexels API (`_fetch_from_pexels`) + rescate verificado en Picsum HD (`_fetch_from_picsum_verified`) donde cada foto es auditada por Gemini Vision antes de ser aceptada; si no cumple, se descarta y escala al fondo procedural cinemático.
  - **Reintentos de IA con Prompts Negativos**: Si la IA generativa produce una imagen rechazada por el Gatekeeper (ej. marcas de agua o personas espurias), el pipeline reintenta con un prompt correctivo reforzado antes de activar los fallbacks.
  - **Verificación Integral y Pruebas Empíricas**: Pruebas exitosas con escenas reales rechazando adecuadamente la mujer (`scene_003.png`) y el joven en el prado (`scene_004.png`), garantizando que solo imágenes coherentes lleguen al montaje final.
- [x] **Phase 12: Fail-Closed Vision QA, Metadata Anti-Poisoning Guardian & Pexels Smart Query Engine**
  - **Auditoría Fail-Closed & Control de Saturación**: Blindaje de `audit_image_with_gemini_vision` con semáforo thread-safe (`_VISION_AUDIT_LOCK`) y temporizador de cortesía (1.2s) para no rebasar los límites gratuitos de la API.
  - **Guardián de Metadatos Anti-Poisoning**: Salvaguarda automática e instantánea basada en el texto descriptivo (`alt`) y etiquetas de Pexels, eliminando a nivel de metadatos cualquier mujer, modelo, selfie o retrato fuera de contexto, permitiendo la selección de imágenes de alta fidelidad documental incluso ante agotamiento de cuota de Gemini Vision.
  - **Búsqueda Escalonada en Pexels API**: Derivación automática de términos primarios y simplificados en orientación vertical con adaptación inteligente vía Pillow Lanczos, garantizando fotografías históricas auténticas y coherentes.
  - **Validación End-to-End**: Producción exitosa del documental 'La historia del fundador de Louis Vuitton' (13 escenas) con 100% de imágenes contextuales reales de archivo, subido y publicado automáticamente a YouTube Shorts, Instagram Reels y TikTok.

> Nota: las fases 13 y 14 (batch vertical y publicación vía Buffer) figuran como completas en `STATE.md` pero no se registraron aquí.

- [x] **Phase 15: Pre-Publish Quality Gate** (Requisitos: FR-12) — *Fase A de la auditoría 2026-10-15*
  - [x] 15.1 Corregir bugs: `shot_type` por defecto `macro_detail`, semilla con `hashlib`, firma de caché por escena (FR-12.5).
  - [x] 15.2 Retirar Picsum y la aprobación de Pexels solo por metadatos (FR-12.2).
  - [x] 15.3 Auditoría de visión por lote con hoja de contacto: 1 llamada por video, veredicto JSON por escena (FR-12.3).
  - [x] 15.4 Bloqueo de publicación: procedural en escenas 1–3, >1 procedural, duplicados por hash/pHash → `needs_review` (FR-12.1).
  - [x] 15.5 Flag `--require-approval` con hoja de contacto en `output/review/` (FR-12.4).
  - [x] 15.6 Verificado (2026-10-15): (a) gate sin API sobre las imágenes publicadas del Emú → detecta degradados en escenas 1–2 y duplicado 10=6 (falso positivo de cielo liso corregido con comparación de color); (b) regeneración real del guion del Emú en carpeta temporal → 4 llamadas de visión en total (1 por ronda), 0 degradados, 0 duplicados, 4/13 aprobadas, publicación bloqueada correctamente. `--dry-run` no sirve para esto (sale antes de generar), por eso se usó una carpeta temporal.

- [ ] **Phase 16: Free Hybrid Visual Pipeline** (Requisitos: FR-13) — *Fase B, enfoque híbrido gratuito elegido 2026-10-15 (costo USD 0)*
  - [x] 16.1 Spike gratuito (2026-10-15):
    - Clave Gemini: **tier gratuito confirmado** (los errores de cuota citan `...-FreeTier`); no puede generar cargos.
    - Imagen de Gemini (`gemini-2.5-flash-image`, `gemini-3.1-flash-image`, `-lite`, `-preview`): **descartada**, límite gratuito = 0.
    - Pollinations: **descartada**, sin clave responde 402 incluso a 512px (cabeceras `X-PAYMENT`: pago por uso).
    - Cloudflare Workers AI: **elegida para huecos**, 10.000 neuronas/día gratis; FLUX schnell ≈ 58 neuronas por imagen 576x1024 a 4 pasos (estimación) → ~170 imágenes/día. Pendiente: el usuario crea cuenta y token.
    - Archivo: Wikimedia tiene fotos reales del hecho ("Deceased emu during Emu War.jpg", "Emus coming to drink Emu War.jpg") y de ametralladoras Lewis de época; el pipeline no las encontraba por buscar con palabras genéricas por escena y consultar Wikimedia al final. Library of Congress: útil pero lenta (timeouts). Openverse: agrega Flickr/Wikimedia con licencias CC (requiere atribución).
  - [x] 16.2 Búsqueda de archivo (2026-10-15): nuevo campo `VisualContract.archive_search_terms` (nombre canónico en inglés del hecho); orden de fuentes: Wikimedia por tema → Wikimedia por escena (con década) → Pexels → NASA → IA; autor/licencia en el manifiesto (`credit`), descartando NC/ND y sin licencia. Prueba con el Emú: 7/13 escenas con fotos reales de 1932 de dominio público (antes 0), duplicados reemplazados aunque la visión esté caída. Library of Congress aplazada: lenta y sin licencia en los resultados de búsqueda.
    - Pendiente detectado: el collage moderno "TheGreatEmuWarcolage.png" entra como candidato; la escena 11 trajo una foto de la Guerra Civil de EE. UU. La auditoría visual debería rechazarlos (no se pudo comprobar: cuota de visión agotada ese día).
  - [x] 16.3 Encuadre con fondo desenfocado cuando el formato de origen difiere más de 1,25× del destino (`_fit_with_blurred_background` en `image_generator.py`); si difiere menos, se recorta como antes.
  - [x] 16.4 Gradación uniforme en `video_assembler.py`: look `archival` (monocromo cálido) si la época es anterior a 1960, `cinematic` (desaturado, sombras frías, luces cálidas) en otro caso; grano y viñeta en ambos. Verificado con frames renderizados en `screenshots/fase16_look_compare.png`.
  - [ ] 16.5 IA gratuita para huecos vía Cloudflare Workers AI, con la misma gradación (FR-13.4, FR-13.5). Bloqueada hasta que el usuario cree la cuenta y el token.
  - [ ] 16.5b Créditos de licencias en la descripción de la publicación (FR-13.8).
  - [ ] 16.6 Verificar: producir video de prueba sin publicar, revisar hoja de contacto completa y comparar contra la del Emú.

- [x] **Phase 17: Revisión visual siempre disponible y publicación diferida** (Requisitos: FR-14)
  - [x] 17.1 Descubrimiento automático de modelos de visión gratuitos (FR-14.1).
  - [x] 17.2 Errores diferenciados: cuota diaria, límite por minuto, saturación, petición no soportada (FR-14.2).
  - [x] 17.3 Soporte de modelos sin modo JSON (FR-14.3).
  - [x] 17.4 Verificado (2026-10-15): 16 modelos descubiertos (antes 3). Con los 3 originales marcados como agotados: `gemini-3.8-flash` → saturado, reintento, cuota diaria → descartado; `gemini-3.7-flash` → saturado, reintento → auditoría resuelta.
    - **Hallazgo:** el revisor rechaza fotos reales de archivo correctas (0/13 con `gemini-2.5-flash`, 2/13 con `gemini-3.7-flash`). Motivos: (a) regla "ningún humano en planos macro/ambiente", pensada para IA, aplicada a fotos de época con personas; (b) compara contra la composición exacta del `visual_prompt` (pensado para IA) en vez de contra la narración y el hecho. Además, distintos modelos son más o menos estrictos. Pendiente de decisión: criterios específicos para fotos de archivo.
  - [x] 17.4b Criterios del revisor por fuente (FR-14.3b). Verificado con el Emú en carpeta nueva: 9/13 aprobadas (antes 0–2/13); las 4 fotos reales de 1932 aprobadas; rechazadas correctamente la camioneta moderna, un parque urbano, vidrio roto contemporáneo y una imagen de Pollinations con marca de agua. Captura: `screenshots/fase17_emu_contact.png`.
    - Dudoso: aprobó un dingo en jaula para la escena de la valla (criterio de stock algo permisivo).
    - El video sigue bloqueado: 4 escenas agotan sus candidatos tras 4 rondas. Hace falta una fuente extra para huecos (16.5, Cloudflare) o más profundidad de búsqueda en archivo.
  - [x] 17.4c Búsqueda de archivo ampliada (sin cuentas nuevas): campo `Scene.archive_queries` generado por el guion; consultas lugar + década desde `era_setting`; nueva fuente Openverse (Flickr Commons/bibliotecas, solo licencias comerciales y modificables); límites de candidatos mayores y 8 rondas.
    - Resultado (2026-10-15): **no mejora la tasa de aprobación**. Guion original: 9/13 (igual que antes, distinto conjunto). Guion nuevo de 5 escenas con `archive_queries`: 3/5 (las 3 son fotos reales de 1932). Openverse no aportó ninguna imagen final. Tiempo de la etapa de imágenes: 6–11 min.
    - Inconsistencia del revisor: aprobó vidrio roto contemporáneo (escena 2) que antes rechazó, y siluetas de soldados modernos (escena 11).
    - Conclusión: las escenas que fallan describen acciones sin registro fotográfico (camión persiguiendo emúes, atardecer con emúes); más búsqueda no las resuelve. Opciones: fusionar la escena sin imagen con la anterior, usar un recorte de una foto aprobada, o IA para huecos (16.5, requiere cuenta). Captura: `screenshots/fase17_emu_contact_archivo_ampliado.png`.
  - [x] 17.4d Fusión de escenas sin imagen válida (FR-14.6): `evaluate_gate` calcula las fusiones, `apply_scene_merges` (video_assembler) las aplica y `main.py` ejecuta el control antes del montaje. Verificado (2026-10-15): Emú 13 escenas con 4 fallidas → bloqueado (supera el máximo de 2); Emú 5 escenas con 2 fallidas → aprobado con fusiones {3→2, 4→2}; video montado de 30 s con la foto de la escena 2 durante 18 s (frames en `screenshots/fase17_fusion_frames.png`).
    - Observación: 18 s sobre una sola foto es largo para Shorts.
    - Fallo previo detectado (no causado por la fusión): el video sale ~0,5 s más corto que la narración (Emú publicado: 126,67 s vs 127,16 s) y `-shortest` corta el final de la voz.
  - [x] 17.4e Corregido el corte del final de la narración (2026-10-15) en `video_assembler.py`: el último clip también se extiende `TRANSITION_DURATION` (los fundidos empiezan 0,5 s antes de cada cambio y adelantaban todo el video), frames redondeados en vez de truncados, y `tpad` congela el último frame como red de seguridad. Verificado: audio de 43,480 s → audio en el video 43,480 s (antes 42,957 s); cambios de escena sin desfase; también con subtítulos quemados y con una sola escena.
  - [x] 17.5 Cola de publicación diferida (`src/publish_queue.py`): `main.py` encola cuando el control falla por escenas sin revisar (`GateResult.unaudited`); `--process-queue` re-audita solo lo pendiente, vuelve a montar con las fusiones finales y publica si pasa el control; resultados en `done/` o `needs_review/`. La publicación se extrajo a `publish_social` para compartirla. `ask_yes_no` trata la entrada cerrada (EOF) como "no".
  - [x] 17.7 Prueba completa con Chernóbil (2026-10-15), sin publicar: pipeline de principio a fin en 17 min; audio completo (126,04 s). Sin clave de IA: 7/13 aprobadas → bloqueado. Con clave de Pollinations (`sk_`, API nueva `gen.pollinations.ai`, FLUX schnell, ~0,002 Pollen/imagen, saldo gratuito de nivel 0,25 y pagado 0): 11/13 aprobadas + 2 fusiones → control superado; video `output/la_explosion_de_chernobil_1986_9x16_v2.mp4`. Capturas: `screenshots/chernobyl_v2_contact.png`, `screenshots/chernobyl_v2_frames.png`.
    - Cambios: Pollinations solo con clave (sin clave trae marca de agua) y por la API nueva; las escenas rechazadas guardan en el manifiesto (`cascade`) la fuente y los candidatos ya probados, y una nueva ejecución continúa desde ahí.
  - [x] 17.6 Verificado (2026-10-15) sin publicar nada real: (a) con visión simulada caída el trabajo queda en cola (1 intento); (b) con visión real re-audita, aprueba 1/2/5, rechaza 3/4, fusiona {3→2, 4→2}, re-monta (30,0 s con audio completo), llama una vez a la publicación simulada y pasa a `done/`; (c) `main.py` real con `--skip-*` y `--publish-platforms youtube` encola el video (`quality_report` = `queued`); la entrada de prueba se retiró de `output/queue/`; (d) `--process-queue` con cola vacía funciona. Tarea programada documentada en el README (no creada).
    - Fallos encontrados y corregidos en la verificación: en Git Bash `isatty()` es verdadero aunque no haya entrada y `input()` lanzaba `EOFError`; las escenas sin registro en el manifiesto contaban como "sin revisar" para el control pero no para la cola.
