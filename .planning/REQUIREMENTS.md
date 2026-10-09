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


