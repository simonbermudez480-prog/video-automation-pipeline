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

