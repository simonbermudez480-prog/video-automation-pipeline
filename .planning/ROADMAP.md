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
  - [x] 17.8 Correcciones tras publicar Poyais (2026-10-15):
    - `--topic` ya no se separa por comas: cada valor es un tema completo (verificado con `--dry-run`: "A (B, 1822)" → 1 tema; dos valores → 2 temas).
    - Revisor: rechaza en imágenes de IA y stock el texto visible inventado, ilegible o mal escrito (WATERMARK_OR_TEXT); el material de archivo incluye pinturas, grabados, mapas, billetes y documentos (antes de 1840 no hay fotografía); a las imágenes de archivo ya no se les envía el "sujeto previsto" pensado para IA. Verificado 3 veces con Poyais: cartel "WANTED" (escena 11) rechazado 3/3; retrato real de MacGregor (escena 10) aprobado 3/3 (antes se rechazaba por "pintura" o por "no ser silueta"); IA correctas aprobadas.
    - Pendiente detectado: el mapa de la escena 13 de Poyais tiene marcas de agua tenues "©Old World Auctions" que el revisor solo detectó 1 de 3 veces (las miniaturas de 432x768 las ocultan). Ese mapa está en el video publicado.
  - [x] 17.9 Marcas de agua tenues (2026-10-15): el revisor recibe las imágenes a 864x1536 (antes 432x768) y una regla explícita para marcas tenues, semitransparentes o en mosaico (subastas, agencias, URLs), sin confundirlas con el texto original de mapas, billetes o documentos. Verificado: mapa de Poyais con "©Old World Auctions" rechazado 5/5 (antes 1/3); el resto de Poyais estable 5/5; en Chernóbil, ningún falso positivo por marca de agua.
    - Regla añadida: fotos posteriores del mismo lugar (ruinas, memoriales, sarcófago, el lugar hoy) valen cuando la narración habla de consecuencias o del presente.
    - Limitación observada: en imágenes límite (Chernóbil escenas 4, 9, 10, 12) el veredicto cambia entre pasadas; es variabilidad del modelo. Posible mejora futura: voto por mayoría de 2–3 llamadas solo para imágenes dudosas.
  - [x] 17.6 Verificado (2026-10-15) sin publicar nada real: (a) con visión simulada caída el trabajo queda en cola (1 intento); (b) con visión real re-audita, aprueba 1/2/5, rechaza 3/4, fusiona {3→2, 4→2}, re-monta (30,0 s con audio completo), llama una vez a la publicación simulada y pasa a `done/`; (c) `main.py` real con `--skip-*` y `--publish-platforms youtube` encola el video (`quality_report` = `queued`); la entrada de prueba se retiró de `output/queue/`; (d) `--process-queue` con cola vacía funciona. Tarea programada documentada en el README (no creada).
    - Fallos encontrados y corregidos en la verificación: en Git Bash `isatty()` es verdadero aunque no haya entrada y `input()` lanzaba `EOFError`; las escenas sin registro en el manifiesto contaban como "sin revisar" para el control pero no para la cola.

- [x] **Phase 18: Interfaz de escritorio** (Requisitos: FR-15)
  - [x] 18.1 Soporte en `main.py`: `quality_report.json` siempre, `--publish-job`, resultado de publicación en `publication.json` (FR-15.5).
  - [x] 18.2 Ventana `app.py` con pestañas Crear, Revisar y publicar, Historial, Cola y estado (FR-15.1–15.4).
  - [x] 18.3 Lanzador `Abrir_Videos_Educativos.bat` (sin consola).
  - [x] 18.4 Verificado (2026-10-15): capturas reales de las 4 pestañas en `screenshots/fase18_tab*.png` revisadas (texto legible, buen contraste, estados en color); `publish_job` con publicación simulada (éxito → "Publicado"; fallo → conserva el veredicto del control y muestra "Error al publicar"); el ejecutor de la ventana lee el progreso de `main.py` (`--dry-run`); el lanzador abre `pythonw app.py` sin consola. Corregido en la verificación: barra de progreso poco visible; carpetas de prueba antiguas que aparecían como "En cola".
    - Los trabajos publicados antes de la Fase 18 (Chernóbil y Poyais) recibieron `quality_report.json` y `publication.json` con sus IDs reales de Buffer para que aparezcan en el historial.
    - Tkinter no tiene modo oscuro del sistema: la ventana usa un tema claro fijo de alto contraste.

- [x] **Phase 19: Paquete portátil para otra PC** (Requisitos: FR-16)
  - [x] 19.1 Subida a `video-assets` por API con token limitado (FR-16.1).
  - [x] 19.2 `instalar.bat` + lanzador portable (FR-16.2, FR-16.3).
  - [x] 19.3 Diagnóstico en la interfaz y `.env.example` completo (FR-16.4).
  - [x] 19.4 `INSTALACION.md` y `empaquetar.bat` (FR-16.5).
  - [x] 19.5 Verificado (2026-10-16): paquete de 0,29 MB cifrado (AES-256, nombres de archivo incluidos); instalación limpia en carpeta nueva con FFmpeg del sistema oculto → 6/6 pasos OK (librerías en `.venv`, FFmpeg descargado de GitHub, prueba de arranque); la ventana abre desde esa copia con su FFmpeg local y el diagnóstico todo en verde (`screenshots/fase19_diagnostico_instalacion_limpia.png`). Token fine-grained: subida real a `video-assets` OK (HTTP 200 en raw), archivo de prueba borrado, escritura en otro repo bloqueada (403).
    - Corregido en la verificación: rutas largas (>90 caracteres) rompían pip → el instalador lo detecta y lo explica; gyan.dev cortaba la descarga de FFmpeg → `curl.exe` con reintentos y GitHub como fuente principal; PowerShell 5.1 trataba el registro del programa (stderr) como error → la prueba de arranque se redirige con `cmd`.
    - Paquete final generado en `dist\VideosEducativos_Instalador.exe` (no versionado) con contraseña aleatoria entregada al usuario por chat.

- [ ] **Phase 20: Gancho inicial y pregunta final** (Requisitos: FR-17) — *backup previo: `backups/backup_pre_hook_20261017.zip` y `repo_history_20261017_pre_hook.bundle`*
  - [x] 20.1 Guion: campos `hook_text` y `closing_question`; escena 1 con el sujeto más icónico y consultas de archivo dirigidas (FR-17.1, FR-17.2, FR-17.4).
  - [x] 20.2 Montaje: texto de gancho en pantalla (0–2,5 s), acercamiento rápido inicial y pregunta final en pantalla (últimos 3 s) sin chocar con los subtítulos (FR-17.1, FR-17.3, FR-17.4).
  - [x] 20.3 Revisor visual: puntuación de impacto por imagen y "avance" de ~1,2 s con la imagen más fuerte si no es la escena 1 (FR-17.2).
  - [x] 20.4 Textos de publicación con la pregunta; spike de primer comentario por Buffer y, si no se puede, "Comentario para fijar" copiable en la interfaz (FR-17.4, FR-17.5).
  - [x] 20.5 Verificado (2026-10-17), sin publicar:
    - Guion nuevo (Victor Lustig): `hook_text` de 8 palabras, escena 1 abre narrando el gancho con el sujeto icónico (Torre Eiffel) y consultas de archivo dirigidas; la última escena y `narration_full` terminan con `closing_question`.
    - Re-montaje de Poyais en copia: impacto real por imagen (escena 1 = 7, máx. 8 → sin apertura alternativa por no superar +2); gancho legible 0–2,5 s y pregunta final en amarillo los últimos ~3 s, sin chocar con subtítulos; audio completo (153,07/153,08 s). Capturas: `screenshots/fase20_frames_poyais.png`, `fase20_frame_inicio.png`, `fase20_frame_final.png`.
    - Corregido en la verificación: el corte inicial no se notaba con la misma imagen → la apertura ahora es un primer plano cerrado (zoom 1,7–1,9) y corta al plano completo antes de 1,5 s (`screenshots/fase20_apertura_corte.png`).
    - Spike Buffer: solo Instagram acepta `firstComment` (se envía la pregunta); TikTok y YouTube no → recuadro "Comentario para fijar" con botón Copiar en la interfaz (`screenshots/fase20_interfaz_comentario.png`). Pregunta añadida a los 3 textos (verificado sin red).
    - Hallazgo: Buffer tiene `isAiGenerated` para TikTok, YouTube e Instagram; los videos con imágenes FLUX podrían requerir la etiqueta de contenido IA (decisión pendiente del usuario).
  - [ ] 20.6 Medición tras publicar 3–5 videos nuevos: comparar con la línea base de Bin Laden (FR-17.6).

- [x] **Phase 21: Corrección de Instagram y rediseño de la interfaz** (Requisitos: FR-18)
  - [x] 21.1 Instagram reintenta sin primer comentario; `publication.json` fusiona plataformas (prueba de reproducción en verde).
  - [x] 21.2 Historial con estado parcial, motivo del error y "Reintentar en <plataforma>".
  - [x] 21.3 Rediseño oscuro con CustomTkinter (menú lateral, tarjetas, píldoras, estados vacíos).
  - [x] 21.4 Verificado (2026-10-18): capturas reales `screenshots/fase21_create.png`, `fase21_review.png`, `fase21_history.png` (con aviso de error y "Reintentar en Instagram") y `fase21_status.png` revisadas; contraste comprobado (texto 15,7:1, secundario 7,7:1, botón principal 7,0:1). Reintento probado sin publicar: genera `--publish-job <carpeta> --publish-platforms instagram`.
    - Corregido en la verificación: píldora de estado cortada y títulos recortados en el historial (columnas fijas en cuadrícula), emojis de los títulos que Tk mostraba como cuadros, barra de disco que mostraba el espacio usado en azul con texto "Suficiente", hoja de contacto recortada o demasiado pequeña.
    - Solo tema oscuro (decisión del usuario). Requiere `customtkinter` (añadido a requirements.txt; el instalador lo instala). Pendiente: volver a publicar en Instagram los 5 videos afectados, con confirmación del usuario.

- [ ] **Phase 22: Mejoras de calidad tras la auditoría** (Requisitos: FR-19) — *auditoría 2026-10-18; orden por impacto*
  - **Bloque 1 · Disco** (poco esfuerzo, evita que el disco se llene)
    - [x] 22.1 Borrar `temp` de cada trabajo al terminar bien (FR-19.1). *Hecho 2026-10-18: `assemble_video` borra `clip_*.mp4` y el `.ass` al terminar (738 MB por video); verificado re-montando Reckless.*
    - [x] 22.2 Carpeta de trabajo fuera de OneDrive (`WORK_DIR`) con migración (FR-19.2). *Hecho 2026-10-18: `WORK_DIR` en `.env` → `jobs/`, `temp/`, `output/`; `mover_carpeta_trabajo.py` movió 28 trabajos y `output` a `C:\Users\simon\VideosEducativos_trabajo`, corrigió 51 JSON y liberó 2,37 GB (incluye el clon viejo del CDN); aviso en el diagnóstico de la interfaz.*
  - **Bloque 2 · Lo que se publica**
    - [x] 22.3 "Reparar escenas" y confirmación reforzada con <80 % aprobadas (FR-19.3). *Hecho 2026-10-18: `main.py --repair-job` reabre la búsqueda solo de las escenas no aprobadas con candidatos extra (`REPAIR_BONUS`), vuelve a pasar el control, re-monta en el mismo archivo, borra el `_web.mp4` viejo y actualiza el reporte (salida 0 = supera, 2 = en parte). Interfaz: «Reparar escenas» como acción principal si el control falla, «Publicar igualmente» secundaria y segundo aviso (por defecto «No») con <80 % aprobadas. Prueba con copia de Guam: 6 → 8 de 13 aprobadas en ~24 min; Pollinations sin saldo (HTTP 402) limitó el resultado. Capturas: `screenshots/fase22_review_antes.png` y `_despues.png`.*
    - [x] 22.4 Limpieza del tema de entrada (FR-19.4). *Hecho 2026-10-18: `clean_topic` en `extract_topics` quita "3. ", "2) ", "- ", ". ", viñetas y comillas; respeta "3.5 millones", "1914-1918" y "1932: …".*
  - **Bloque 3 · Red de seguridad**
    - [x] 22.5 Pruebas automáticas sin internet (FR-19.5). *Hecho 2026-10-18: `tests/test_offline.py` (unittest, sin dependencias nuevas), 18 pruebas en ~18 s con `python -m unittest discover -s tests`: limpieza de temas y comas, control de calidad y fusiones, duplicados, reintento de Instagram, fusión de `publication.json`, fallo de publicación sin marcar publicado y duración del montaje con FFmpeg (incluye borrado de temporales). Comprobado que detectan fallos provocados (máximo de fusiones y decimales en el tema).*
    - [x] 22.6 Errores visibles en la interfaz (FR-19.6). *Hecho 2026-10-18: si falla la subida o la redacción, cada plataforma guarda el motivo en `publication.json` (antes quedaba vacío → «Error desconocido»); se registra `copy_source` y la interfaz avisa si los textos salieron de la plantilla; al detenerse una creación o reparación se muestra el último error del registro; nuevos mensajes en español para subida, límite y token de Buffer. Capturas: `screenshots/fase22_error_publicar.png`, `fase22_error_crear.png`.*
  - **Bloque 4 · Decisiones con datos**
    - [ ] 22.7 Tiempos por paso en el reporte (FR-19.7).
    - [ ] 22.8 Experimento de duración 60 s vs 2,5 min (FR-19.8, con 20.6).
    - [ ] 22.9 Voto por mayoría en imágenes dudosas (FR-19.9).
  - **Bloque 5 · Mantenimiento**
    - [ ] 22.10 Créditos de licencias y decisión `isAiGenerated` (FR-19.10).
    - [ ] 22.11 Descubrimiento de modelos de guion y voz (FR-19.11).
    - [ ] 22.12 Política de alojamiento de `video-assets` (FR-19.12).
    - [ ] 22.13 Pasar a `main`, fijar versiones, sacar `assets/` de git, quitar código muerto (FR-19.13).
