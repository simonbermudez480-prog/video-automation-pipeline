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
