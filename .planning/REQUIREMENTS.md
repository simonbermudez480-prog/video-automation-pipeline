# Project Requirements

## Core Functional Requirements (FR)

### FR-01: Script & Visual Prompts Generation (`src/script_generator.py`)
- Soporte dual para **Gemini** (`google-genai`) y **DeepSeek** (`openai` API format).
- Salida estructurada (JSON validado):
  - Metadatos optimizados para CTR: Título atractivo, descripción estructurada con timestamps sugeridos y etiquetas (tags).
  - Guion completo continuo para narración.
  - Lista de escenas divididas lógicamente con:
    - `scene_id`: Identificador entero secuencial.
    - `narration_text`: Texto exacto a locutar en esa escena.
    - `visual_prompt`: Prompt en inglés de alta calidad describiendo composición, iluminación, estilo documental/cinematográfico para ratio 16:9.

### FR-02: Natural Voice Synthesis (`src/voice_synthesizer.py`)
- Integración primaria con **ElevenLabs API** para voces ultra-naturales.
- Fallback automático y transparente a **Microsoft Edge TTS** (`edge-tts`) sin costo ni API key si ElevenLabs falla o no tiene clave configurada.
- Generación de archivo maestro `narration.mp3` con cadencia y pausas naturales.

### FR-03: Audio Alignment & Timestamp Extraction (`src/audio_processor.py`)
- Transcripción local con `faster-whisper` extrayendo timestamps precisos por segmento y palabra.
- Detección de silencios con `pydub` para afinar los cortes naturales entre escenas.
- Algoritmo de alineación secuencial que casa cada escena del guion con su ventana temporal exacta (`start_time`, `end_time`, `duration`).
- Generación y exportación de subtítulos en formato `.srt` sincronizados.

### FR-04: Coherent Visual Generation (`src/image_generator.py`)
- Soporte multi-proveedor: Google Imagen 3 (`google-genai`), Fal.ai / Replicate / Stability AI, y fallback inmediato con Pollinations (sin coste ni clave) para pruebas rápidas.
- Generación secuencial de imágenes en ratio 16:9 guardadas en `assets/images/scene_{idx:03d}.png`.
- Reintentos exponenciales ante cuotas o errores de red.

### FR-05: Dynamic Audiovisual Assembly (`src/video_assembler.py`)
- Montaje automatizado mediante `FFmpeg`.
- Efecto Ken Burns suave y continuo con `zoompan` (alternando zoom in / zoom out / panes por escena para ritmo dinámico sin cortes estáticos).
- Concatenación de clips por escena ajustados a la duración exacta del audio de cada escena.
- Mapeo de pista de audio de narración original (`narration.mp3`).
- Quemado de subtítulos (`subtitles.srt`) con estilo legible y contraste óptimo.
- Exportación final en `output/video_final.mp4` a 1080p (1920x1080) a 30 FPS.

### FR-06: Automated YouTube Upload (`src/youtube_uploader.py`)
- Integración oficial con YouTube Data API v3 (`google-api-python-client`, `google-auth-oauthlib`).
- Subida del archivo con título, descripción y tags derivados del paso 1.
- Configuración de privacidad (`private`, `unlisted`, `public`).
- Manejo de flujo OAuth2 local con almacenamiento en caché de credenciales (`token.json`).

### FR-07: CLI & Orchestration (`main.py`)
- Ejecución con un solo comando: `python main.py --topic "Tema del video"`.
- Opciones de omisión de etapas para debugging (`--skip-script`, `--skip-audio`, `--skip-timestamps`, `--skip-images`, `--skip-video`, `--upload`, `--dry-run`).
- Logging profesional con timestamps, niveles de severidad y formato visual.

### FR-08: Multi-Platform AI Social Copywriter (`src/social_copywriter.py`)
- Generación de copies y hashtags especializados mediante IA (Gemini / DeepSeek):
  - **YouTube Shorts:** Título con alto gancho (<60 caracteres + `#Shorts`), descripción estructurada con llamada a la acción y tags de búsqueda.
  - **Instagram Reels:** Gancho inicial en primera línea (hook), cuerpo explicativo conciso, CTA ("Guarda este video", "Síguenos") y 15-20 hashtags estratégicos combinando nicho y alto alcance.
- Salida estructurada con validación Pydantic y plantillas fallback de alta conversión.

### FR-09: Multi-Platform Publishing Flow (`src/multiplatform_publisher.py`)
- Enfoque híbrido:
  - **Conectores directos:**
    - YouTube Shorts vía YouTube Data API v3 (`src/youtube_uploader.py`).
    - Instagram Reels vía Meta Graph API (con `INSTAGRAM_ACCESS_TOKEN` y `INSTAGRAM_BUSINESS_ACCOUNT_ID`).
    - TikTok vía TikTok Content Posting API (con `TIKTOK_ACCESS_TOKEN`) o soporte de webhook multi-red.
  - **Paquete de publicación listo (`output/social_packages/<job_slug>/`):**
    - Copia del video en alta resolución 9:16.
    - Archivos de texto listos para copiar y pegar: `youtube_shorts.txt`, `instagram_reels.txt`, `tiktok.txt`.
    - Manifiesto `social_manifest.json` para integración con herramientas de automatización (Metricool, Buffer, Make, n8n).

### FR-10: Visual Contract & Cinematic Consistency Matrix (`src/script_generator.py`, `src/image_generator.py`)
- Definición de `VisualContract` por proyecto (`era_setting`, `art_style`, `color_palette`, `lighting_atmosphere`, `character_anchor`, `shot_progression_rules`).
- Tipificación de planos (`shot_type`: `macro_detail`, `over_the_shoulder`, `silhouette_backlight`, `environmental_wide`, `dramatic_close_up`) para prevenir mutaciones faciales.

### FR-11: Multimodal Vision QA Gatekeeper, Pexels/Picsum Hybrid & Anti-Poisoning (`src/image_generator.py`, `src/script_generator.py`)
- **Sanitización de Prompts Anti-Poisoning**: Erradicación del token "portrait" en composiciones 9:16 para evitar que los modelos generen retratos humanos no deseados. Inyección de directivas negativas y composiciones cinemáticas deshabitadas (`no people, no portraits, archival artifact`) para planos generales y macro.
- **Auditoría Multimodal con Gemini Vision**: Inspección automática de cada imagen antes de incluirla en el video:
  - Detección de marcas de agua y logos comerciales (`pollinations.ai`, `shutterstock`, etc.).
  - Detección de humanos no solicitados o discordancias anacrónicas/temáticas.
  - Rechazo y reintento automático con corrección de prompt.
- **Híbrido de Stock Pexels & Picsum con Verificación**:
  - Soporte de Pexels API para fotografía y video de stock documental contextual.
  - Filtrado inteligente de Picsum Photos mediante auditoría de Gemini Vision para descartar fotos aleatorias desconectadas.
  - Fallback procedural cinemático si las fuentes externas no satisfacen los criterios de calidad.
  - **[SUPERSEDED por FR-12/FR-13]** — Auditoría 2026-10-15: Picsum, el Guardián de Metadatos y el fallback procedural son la causa principal de imágenes incoherentes (ver Contexto en FR-12).

### FR-12: Pre-Publish Quality Gate (Fase 15)
**Contexto (auditoría 2026-10-15, video "La Guerra del Emú"):** escenas 1–2 (gancho, ~21 s) salieron como degradado procedural; escenas 6 y 10 idénticas (mismo MD5); escena 5 soldado moderno anacrónico; escena 12 perro en playa. Log: 298× Pollinations HTTP 402, cuota Gemini Vision agotada a mitad del lote → 89 aprobaciones solo por metadatos vs 18 por visión, 39 fondos procedurales.

- **FR-12.1 Bloqueo de publicación:** El video NO se envía a Buffer/YouTube si: (a) alguna de las escenas 1–3 es un fallback procedural; (b) más de 1 escena total es procedural; (c) existen imágenes duplicadas (hash idéntico o perceptual hash con distancia ≤ 5). El job queda marcado `needs_review` con motivo en el log y en el manifiesto.
- **FR-12.2 Eliminación de fuentes incoherentes:** Se retiran Picsum (`_fetch_from_picsum_verified`) y la aprobación de Pexels solo por metadatos (`alt`). Una imagen sin auditoría visual real no se aprueba.
- **FR-12.3 Auditoría por lote:** La auditoría de Gemini Vision se hace con una sola llamada por video (hoja de contacto numerada con todas las escenas + narración por escena), que devuelve un veredicto JSON por escena. Se re-auditan solo las escenas regeneradas. Objetivo: ≤ 3 llamadas de visión por video.
- **FR-12.4 Aprobación humana opcional:** Flag `--require-approval` (por defecto activo cuando se publica): genera `output/review/<slug>_contact.png` y pausa antes de publicar hasta confirmación explícita.
- **FR-12.5 Correcciones de bugs:** `shot_type` por defecto `"macro_detail"` (hoy `"detail_macro"` no coincide con ninguna rama); semilla del tema con hash estable (`hashlib`) en vez de `hash()`; la caché de imágenes se invalida también si cambia el `visual_prompt` de la escena (firma por escena, no solo por tema).
- **Criterio de aceptación:** Re-ejecutar el tema "La Guerra del Emú" en modo `--dry-run` produce 0 procedurales en escenas 1–3, 0 duplicados, y si alguna condición falla el pipeline se detiene antes de publicar.

### FR-13: Free Hybrid Visual Pipeline — Archivo + Gradación Uniforme + IA gratuita (Fase 16)
**Decisión (2026-10-15, revisada):** Restricción dura: **costo USD 0 por video**. Se descarta la IA con referencias de pago (opción 1) y la generación local (equipo sin GPU dedicada: i3-1115G4, 12 GB RAM, Intel UHD). La coherencia se logra en postproducción, no en el generador.

- **FR-13.1 Fuente principal = archivo real gratuito:** Wikimedia Commons y Library of Congress (dominio público) priorizados para temas históricos, consultados ANTES que Pexels (el stock de Pexels es casi todo moderno). Búsqueda en dos niveles: (a) consulta del tema/evento en inglés (ej. "Emu War") que trae fotos del hecho real; (b) consulta por escena con términos de época. Siempre con la auditoría visual de FR-12.3 (nada se aprueba sin verse).
- **FR-13.2 Gradación uniforme obligatoria:** Toda imagen, venga de donde venga, pasa por el mismo tratamiento en FFmpeg/Pillow definido por video (curva de color o look monocromo/sepia según la época, grano, viñeta). El look se deriva del `VisualContract`.
- **FR-13.3 Encuadre vertical sin recortes destructivos:** Las fotos horizontales se colocan en 9:16 sobre un fondo de la misma imagen desenfocado, en vez de recortar el centro.
- **FR-13.4 IA gratuita solo para huecos:** Si ninguna foto de archivo supera la auditoría, se genera con Cloudflare Workers AI (`@cf/black-forest-labs/flux-1-schnell`) dentro de la asignación gratuita diaria (10.000 neuronas/día; en el plan gratuito, al superarla la llamada falla, no cobra). Requiere `CLOUDFLARE_ACCOUNT_ID` y `CLOUDFLARE_API_TOKEN` creados por el usuario. Sin esas variables, la IA se omite. La imagen generada pasa por la misma gradación. (Descartados en el spike 16.1: imagen de Gemini y Pollinations; ver ROADMAP.)
- **FR-13.5 Garantía de costo cero:** Ningún proveedor que requiera facturación se llama por defecto. El spike verifica que la clave de Gemini no tenga facturación activa (o que las llamadas usadas estén dentro del tier gratuito).
- **FR-13.6 Personajes:** Para personas históricas se usan fotos/retratos reales de archivo; no se generan rostros con IA. `character_anchor` se usa como término de búsqueda de archivo.
- **FR-13.7 Sin degradados silenciosos:** Si una escena no consigue imagen válida tras archivo + IA gratuita, aplica FR-12.1 (bloqueo / revisión).
- **FR-13.8 Licencias y créditos:** Cada imagen de archivo guarda autor y licencia en el manifiesto. Las licencias que exigen atribución (CC BY / CC BY-SA, comunes en Wikimedia) generan una línea de créditos que se añade a la descripción de la publicación. Se descartan imágenes con licencia NC/ND o sin licencia clara.
- **Criterio de aceptación:** Hoja de contacto del video de prueba revisada visualmente: mismo look en todas las escenas, 0 anacronismos evidentes, 0 marcas de agua, 0 duplicados, 0 degradados; costo registrado USD 0; créditos presentes para toda imagen que los requiera.

### FR-14: Revisión visual siempre disponible y publicación diferida (Fase 17)
**Contexto (2026-10-15):** La revisión visual usaba una lista fija de 3 modelos Gemini; al agotarse su cuota gratuita diaria, todo quedaba `unaudited` y no se podía publicar. La clave tiene más de 10 modelos multimodales gratuitos con cuota propia por modelo (prueba: 5 de 8 respondían con imágenes mientras los 3 de la lista estaban agotados).

- **FR-14.1 Descubrimiento automático de modelos (Capa 1):** La lista de modelos de visión se obtiene de la API (`models.list`) en cada ejecución: modelos `gemini-*flash*` y `gemma-*` con `generateContent`, excluyendo variantes de imagen, audio, TTS, live y transcripción. Orden: primero los preferidos de `GEMINI_VISION_FALLBACK_MODELS`, luego flash, flash-lite y gemma. `GEMINI_VISION_MODELS` en `.env` sigue permitiendo fijar la lista a mano.
- **FR-14.2 Errores diferenciados (Capa 1):** cuota diaria agotada → el modelo se descarta para la sesión; límite por minuto o saturación (429 por minuto, 503) → se reintenta una vez tras una espera corta y, si sigue fallando, se pasa al siguiente sin descartarlo; modelo que no acepta la petición (400) → se descarta para la sesión.
- **FR-14.3 Modelos sin modo JSON (Capa 1):** Si un modelo rechaza `response_mime_type=application/json` (p. ej. Gemma), se repite la petición sin ese parámetro y se extrae el JSON del texto.
- **FR-14.3b Criterios por fuente:** Cada imagen llega al revisor con su fuente (ARCHIVE / STOCK / AI) y, si es de archivo, su título. ARCHIVE se juzga contra la narración y el hecho histórico (no contra el encuadre exacto del prompt), con personas de época permitidas; se rechazan otras épocas o conflictos, temas sin relación, collages/memes y marcas de agua. STOCK solo vale para temas atemporales sin elementos modernos. AI mantiene las reglas estrictas.
- **FR-14.6 Fusión de escenas sin imagen válida:** Una escena sin imagen válida (fondo procedural, duplicada, rechazada o sin revisar) se quita del montaje y su duración se suma a la escena válida anterior; la narración no cambia. Máximo 2 escenas fusionadas por video y nunca la primera; si se supera, el video se bloquea. La hoja de contacto marca en naranja las escenas fusionadas.
- **FR-14.4 Cola de publicación diferida (Capa 2):** Si al terminar el video alguna escena queda `unaudited` (sin capacidad de revisión), el trabajo no se descarta: se guarda en una cola (`output/queue/`) con todo lo necesario para publicar. Un comando `python main.py --process-queue` re-audita las escenas pendientes y, si el control de calidad pasa, publica sin intervención. Pensado para ejecutarse con una tarea programada de Windows cada pocas horas.
- **FR-14.5 Seguridad de la cola:** La cola nunca publica un video que no pase el control completo (FR-12). Un video rechazado por la revisión (no solo sin revisar) sale de la cola y queda `needs_review`.
- **Criterio de aceptación:** (a) con los 3 modelos originales agotados, la auditoría por lote del Emú obtiene veredicto de otro modelo; (b) un video sin revisión posible queda en cola y se publica al procesar la cola cuando hay cuota (probado sin publicar de verdad, con publicación simulada).

### FR-15: Interfaz de escritorio para usuarios sin comandos (Fase 18)
**Decisión (2026-10-15):** ventana de escritorio con Tkinter (incluido en Python, sin instalar nada), en español, que se abre con doble clic en `Abrir_Videos_Educativos.bat`. Usa el mismo pipeline (`main.py`) por debajo.

- **FR-15.1 Crear video:** campo de tema, duración (minutos) y botón "Crear video". Muestra el progreso por pasos (guion, voz, alineación, imágenes, montaje) y un registro legible; permite cancelar. No publica: el video queda listo para revisión.
- **FR-15.2 Revisar y publicar:** lista de videos pendientes con la hoja de contacto, el resultado del control de calidad (motivos y escenas fusionadas), botón "Ver video" y botones "Publicar en las 3 cuentas" (con confirmación) y "Descartar" (no borra archivos). Si el control falló, se avisa claramente antes de permitir publicar.
- **FR-15.3 Historial y enlaces:** tabla de videos con fecha, estado (pendiente, publicado, descartado, en cola) y enlaces de YouTube, Instagram y TikTok; los enlaces se obtienen de Buffer con un botón "Actualizar enlaces" y se abren con doble clic.
- **FR-15.4 Cola y estado:** trabajos en la cola diferida con botón "Procesar cola"; saldo de Pollen y espacio libre en disco, con aviso si queda poco.
- **FR-15.5 Soporte en main.py:** `quality_report.json` se escribe siempre (no solo al publicar); nueva opción `--publish-job CARPETA` para publicar un video ya producido; `publish_social` devuelve el resultado y se guarda en `publication.json` del trabajo.
- **Criterio de aceptación:** capturas reales de las 4 pestañas revisadas visualmente (legibilidad y contraste); flujo crear → revisar → publicar probado con publicación simulada; el lanzador abre la ventana sin consola de comandos.

### FR-16: Paquete portátil para otra PC (Fase 19)
**Decisión (2026-10-15):** un único archivo autoextraíble cifrado con contraseña (7-Zip, AES-256) con el código, la interfaz, el instalador, la guía y el `.env` completo (mismas claves). Nada de esto pasa por GitHub (el repo es público).

- **FR-16.1 Subida sin sesión de GitHub:** el video para Buffer se sube a `video-assets` con la API de contenidos de GitHub usando `GITHUB_CDN_TOKEN` (token fine-grained con permiso solo sobre ese repo) y `GITHUB_CDN_REPO`. Si no hay token, se usa el método anterior (`gh` + clon local).
- **FR-16.2 Instalador de doble clic (`instalar.bat`):** instala Python 3.12 si falta (por usuario, con Tkinter), crea `.venv` con las librerías, descarga FFmpeg en `toolsfmpeg`, crea `.env` desde el ejemplo si falta, hace una prueba de arranque y crea un acceso directo en el escritorio. Mensajes en español.
- **FR-16.3 Lanzador portable:** `Abrir_Videos_Educativos.bat` usa `.venv` y `toolsfmpeg` si existen.
- **FR-16.4 Diagnóstico en la interfaz:** la pestaña "Cola y estado" indica en verde/rojo FFmpeg, claves de Gemini, Buffer, Pollinations, Pexels y token de GitHub.
- **FR-16.5 Empaquetador (`empaquetar.bat`):** genera el autoextraíble con contraseña a partir de los archivos versionados + `.env`, sin videos, trabajos ni backups.
- **Criterio de aceptación:** el paquete se extrae en una carpeta limpia, el instalador termina sin errores, la interfaz abre desde el acceso directo y `--dry-run` funciona; subida de prueba a `video-assets` con el token.

### FR-17: Gancho inicial y pregunta final (Fase 20)
**Contexto (2026-10-17):** El video más viral (Bin Laden, 11K vistas, 83 seguidores, 45,3 s de media, 19,7 % lo terminan) muestra en TikTok Studio que "la mayoría dejó de verlo en el segundo 0:02". Arranca con un plano de ambiente oscuro y quieto, sin texto de gancho; el título con gancho solo está en la descripción. Los comentarios son muy bajos (3 en 11K vistas).

- **FR-17.1 Texto de gancho en pantalla:** el guion genera `hook_text` (máximo 8 palabras, la promesa o contradicción más fuerte; p. ej. "No estaba en una cueva. Vivía frente al ejército"). Se muestra grande y centrado en el tercio superior durante los primeros ~2,5 s, con alto contraste y dentro de la zona segura de TikTok/Reels/Shorts. Si falta, se usa el título sin "#Shorts".
- **FR-17.2 Imagen más fuerte primero:** el guion debe abrir con el sujeto más icónico y real del tema (protagonista, lugar o hecho), con consultas de archivo dirigidas a eso. Además, el revisor visual puntúa el impacto de cada imagen aprobada (1–10) en la misma llamada; si la escena 1 no es la de mayor impacto, el video abre con un "avance" de ~1,2 s de la imagen de mayor impacto y luego corta a la escena 1.
- **FR-17.3 Corte rápido al inicio:** sin fundido de entrada; movimiento visible desde el primer fotograma (acercamiento rápido en el primer segundo) y el primer cambio de plano antes de los 2 s.
- **FR-17.4 Pregunta final:** la última escena termina con una pregunta directa y corta al espectador (narrada) y se muestra en pantalla los últimos ~3 s. La misma pregunta va en el texto de TikTok, Instagram y YouTube.
- **FR-17.5 Comentario fijado:** si Buffer permite publicar un primer comentario por API para alguna plataforma, se publica la pregunta como primer comentario; si no, la interfaz muestra "Comentario para fijar" con un botón para copiarlo.
- **FR-17.6 Medición:** se registra en `.planning` el "segundo en que se va la mayoría", el tiempo medio y el porcentaje que lo termina de los videos nuevos (TikTok Studio) para compararlos con la línea base (0:02 / 45,3 s / 19,7 %).
- **Criterio de aceptación:** video de prueba re-montado desde un trabajo existente (sin publicar) con capturas a 0,3 s, 1 s, 2 s y en los últimos 3 s revisadas visualmente: gancho legible y con contraste, cambio de plano antes de 2 s, pregunta final visible y sin chocar con los subtítulos; audio completo.

### FR-18: Corrección de Instagram y rediseño de la interfaz (Fase 21)
**Contexto (2026-10-18):** El historial marcaba "Error" en Instagram aunque YouTube y TikTok se publicaban. Causa raíz: desde la Fase 20 se enviaba `firstComment` a Instagram y el plan gratuito de Buffer rechaza el post completo ("First comment requires a paid plan"): 5 videos no llegaron a Instagram (Oreja de Jenkins, Karánsebes, Tres Reyes, Guam, Sargento Reckless). Además, re-publicar en una plataforma sobrescribía el registro de las demás.

- **FR-18.1** Instagram reintenta sin primer comentario cuando Buffer exige plan de pago. `publication.json` solo reemplaza las plataformas publicadas en cada intento.
- **FR-18.2** El historial distingue "Publicado", "Publicado con errores" y "Error al publicar", muestra el motivo de cada error y permite reintentar solo la plataforma que falló.
- **FR-18.3** Rediseño oscuro con CustomTkinter: menú lateral con sección activa y contadores, tarjetas, píldoras de estado, estados vacíos y de error. Tokens inspirados en el DESIGN.md de Linear (un solo acento, grises fríos, contraste AAA en texto y botones).
- **Criterio de aceptación:** prueba que reproduce el fallo de Instagram pasa; capturas reales de las 4 secciones revisadas (contraste, alineación, estados); flujo de reintento probado sin publicar.

### FR-19: Mejoras de calidad del pipeline tras la auditoría (Fase 22)
**Contexto (auditoría 2026-10-18, solo lectura):** se publicaron videos que no superaron el control (Guam 6/13 imágenes aprobadas, Karánsebes 10/13); cada trabajo deja ~800 MB de clips temporales; el proyecto vive dentro de OneDrive (sincroniza temporales y bloquea archivos); temas con restos de listas ("3. El espía…", ". La batalla…"); 13–36 min por video; sin pruebas automáticas; 56 `except Exception`; ~700 líneas de guiones de contingencia sin uso; repo `video-assets` en 525 MB con 44 videos; 17 commits sin pasar a `main`; dependencias sin versión fija.

- **FR-19.1 Disco:** la carpeta `temp` de cada trabajo se borra al terminar bien el video (se conservan imágenes, audio, guion, subtítulos y reportes).
- **FR-19.2 Fuera de OneDrive:** `assets/jobs` y `output` pueden vivir en una carpeta fuera de OneDrive configurable en `.env` (`WORK_DIR`), con migración de lo existente y el instalador/diagnóstico al tanto.
- **FR-19.3 Reparar escenas:** desde la interfaz, un video que no superó el control puede regenerar solo las escenas rechazadas (continuando la búsqueda, con IA si hay clave) y volver a montarse; publicar con menos del 80 % de imágenes aprobadas pide una confirmación reforzada.
- **FR-19.4 Tema limpio:** se quitan numeraciones y puntuación inicial ("3.", "- ", ". ") del tema antes de generar el guion y el nombre del archivo.
- **FR-19.5 Pruebas automáticas sin internet:** control de calidad y fusiones, duración del audio en el montaje, reintento de Instagram, fusión de `publication.json`, temas con comas y limpieza de temas. Se ejecutan con un solo comando.
- **FR-19.6 Errores visibles:** los fallos de redacción de textos, subida o publicación llegan a la interfaz con un motivo claro en vez de quedar ocultos en el registro.
- **FR-19.7 Tiempos por paso:** el reporte de cada trabajo guarda la duración de cada paso; con esos datos se reducen rondas y esperas inútiles.
- **FR-19.8 Experimento de duración:** 3 videos de ~60 s frente a 3 de ~2,5 min, comparando en TikTok Studio el segundo de abandono, el tiempo medio y el porcentaje que termina (enlaza con la tarea 20.6).
- **FR-19.9 Revisor estable:** voto por mayoría (2–3 opiniones) solo para imágenes dudosas.
- **FR-19.10 Licencias y etiqueta IA:** créditos automáticos de imágenes con licencia que exige atribución (16.5b) y decisión sobre `isAiGenerated`.
- **FR-19.11 Descubrimiento de modelos** de guion y voz igual que el de visión.
- **FR-19.12 Alojamiento sostenible:** política para `video-assets` (limpieza o adjuntos de *releases*) antes de que GitHub avise por tamaño.
- **FR-19.13 Mantenimiento:** pasar la rama a `main` y subirla (sin claves), fijar versiones en `requirements.txt`, sacar de git los archivos de trabajo de `assets/` y eliminar los guiones de contingencia sin uso.
- **Criterio de aceptación:** cada tarea se verifica con su prueba o con capturas; tras FR-19.1/19.2 el disco no crece con temporales entre videos; ningún video con el control fallido se publica sin la confirmación reforzada.
