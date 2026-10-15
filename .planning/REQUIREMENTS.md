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


