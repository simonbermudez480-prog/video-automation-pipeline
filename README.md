# 🎬 Video Automation Pipeline (100% Autónomo)

Pipeline en Python 100% automatizado y ejecutable mediante un único comando para la producción integral de videos educativos y virales en formatos **Vertical 9:16 (Shorts/Reels/TikTok)** y **Horizontal 16:9**, con generación automática de copies/hashtags por IA y publicación multi-plataforma:

$$\text{Idea / Tema} \longrightarrow \text{Guion Estructurado} \longrightarrow \text{Voz Natural} \longrightarrow \text{Timestamps/Whisper} \longrightarrow \text{Imágenes (9:16 / 16:9)} \longrightarrow \text{Ken Burns + Subs Seguros} \longrightarrow \text{Copies IA} \longrightarrow \text{Shorts / Reels / TikTok}$$

---

## 🚀 Inicio Rápido (Un Solo Comando)

### 1. Formato Vertical (Shorts, Reels, TikTok) con Paquete Social y Publicación:
```bash
python main.py --topic "La biblioteca de Alejandria" --aspect-ratio 9:16 --publish-all
```

### 2. Modo Masivo / Batch (Múltiples Videos sin sobreescritura):
```bash
python main.py --topic "Tema 1" "Tema 2" "Tema 3" --aspect-ratio 9:16 --publish-all
# O desde un archivo con un tema por línea:
python main.py --topics-file temas.txt --aspect-ratio 9:16 --publish-all
```

### 3. Documental Panorámico Horizontal 16:9:
```bash
python main.py --topic "El misterio de los Agujeros Negros" --aspect-ratio 16:9 --duration-minutes 3.5
```

---

## 📦 Estructura del Proyecto

```text
Videos educativos/
├── assets/
│   ├── audio/              # narration.mp3 generado por TTS
│   ├── images/             # Imágenes 16:9 por escena (scene_001.png, ...)
│   ├── subtitles/          # Subtítulos sincronizados (subtitles.srt)
│   ├── temp/               # Clips de video temporales renderizados
│   ├── script.json         # Guion estructurado por escenas
│   └── aligned_scenes.json # Escenas con timestamps calculados por Whisper
├── output/
│   └── video_final.mp4     # Video final ensamblado en 1080p @ 30fps
├── src/
│   ├── config.py           # Configuración central y validación de rutas
│   ├── logger.py           # Logging profesional con Loguru y marcas de tiempo
│   ├── script_generator.py # Guion y prompts visuales (Gemini / DeepSeek)
│   ├── voice_synthesizer.py# Síntesis de voz (ElevenLabs con fallback a Edge-TTS)
│   ├── audio_processor.py  # Faster-Whisper, silencios Pydub y generador SRT
│   ├── image_generator.py  # Generación de imágenes 16:9 (Imagen 3 / Fal / Pollinations)
│   ├── video_assembler.py  # Montaje FFmpeg, Ken Burns (zoompan) y quemado de subtítulos
│   └── youtube_uploader.py # Subida oficial a YouTube (YouTube Data API v3)
├── main.py                 # Orquestador CLI unificado con argparse
├── requirements.txt        # Dependencias de Python
├── .env.example            # Plantilla de variables de entorno
└── .env                    # Configuración activa del usuario
```

---

## 🛠️ Requisitos e Instalación

### 1. Requisitos Previos
- **Python 3.10+** (Probado y optimizado en Python 3.12).
- **FFmpeg 6.0+** instalado y accesible en el PATH del sistema (`ffmpeg -version`).

### 2. Instalación de Dependencias
```bash
python -m pip install -r requirements.txt
```

### 3. Configuración de Variables de Entorno (`.env`)
Copia `.env.example` a `.env` y define tus claves:

```ini
# --- 1. LLM / Guion ---
LLM_PROVIDER=gemini              # gemini | deepseek
GEMINI_API_KEY=tu_api_key_aqui
DEEPSEEK_API_KEY=tu_api_key_aqui

# --- 2. Síntesis de Voz (TTS) ---
TTS_PROVIDER=edge-tts            # elevenlabs | edge-tts (edge-tts es 100% gratuito)
ELEVENLABS_API_KEY=tu_api_key_aqui
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
EDGE_TTS_VOICE=es-ES-AlvaroNeural

# --- 3. Detección Acústica ---
WHISPER_MODEL=base               # tiny | base | small
WHISPER_DEVICE=cpu               # cpu | cuda

# --- 4. Generación Visual ---
IMAGE_PROVIDER=pollinations      # imagen | fal | stability | pollinations
IMAGE_API_KEY=tu_api_key_aqui

# --- 5. YouTube Data API v3 ---
YOUTUBE_CLIENT_SECRET_FILE=client_secrets.json
YOUTUBE_PRIVACY_STATUS=private  # private | unlisted | public
```

---

## ⚙️ Descripción Detallada de Módulos

### 1. `src/script_generator.py` (Guion y Prompts)
- Diseña un guion estructurado con:
  - **Metadatos CTR:** Título cautivador, descripción estructurada con llamada a la acción y etiquetas SEO.
  - **Narración Continua:** Guion redactado en español neutro con ritmo documental.
  - **División por Escenas:** Cada escena contiene el texto exacto a narrar y un prompt cinematográfico en inglés detallado para ratio 16:9 (describiendo iluminación, composición de cámara, paleta de colores y texturas 8k).
- Soporte dual: **Google Gemini 2.5 Flash** (vía SDK `google-genai` con respuesta JSON garantizada) y **DeepSeek-Chat** (vía protocolo OpenAI). Incluye generador de contingencia inteligente para pruebas sin API key.

### 2. `src/voice_synthesizer.py` (Síntesis de Voz)
- Motor primario: **ElevenLabs** (`eleven_multilingual_v2`) con modulación natural y control de estabilidad.
- Motor secundario: **Microsoft Edge-TTS** (redes neuronales en español como `es-ES-AlvaroNeural`), 100% gratuito, sin necesidad de tokens ni API keys.
- Detección y fallback automático ante cuota excedida o fallos de red.

### 3. `src/audio_processor.py` (Alineación y Detección de Pausas)
- Reemplaza la necesidad de herramientas manuales mediante transcripción local con **Faster-Whisper**.
- Extrae timestamps a nivel de palabra y segmento.
- Analiza silencios acústicos con **Pydub** para ajustar los cortes de escena en los puntos de silencio natural.
- Genera y exporta el archivo de subtítulos sincronizados `assets/subtitles/subtitles.srt`.

### 4. `src/image_generator.py` (Generación de Imágenes)
- Multi-proveedor: Google Imagen 3, Fal.ai (Flux Schnell/Dev), Stability AI y Pollinations.
- Exporta imágenes en horizontal 16:9 (`scene_{idx:03d}.png`).
- Incluye generador cinemático procedural local para asegurar que la renderización continúe sin interrupciones ante fallos de conexión.

### 5. `src/video_assembler.py` (Montaje FFmpeg, Ken Burns Dinámico y Xfade)
- **Efecto Ken Burns de Alto Rango:** Utiliza el filtro `zoompan` de FFmpeg con velocidad y zoom incrementados (1.0x a 1.38x, paneos completos L->R y R->L, empujes diagonales), garantizando un movimiento vivo y continuo.
- **Transiciones Suaves con `xfade`:** Aplica fundidos cruzados cinemáticos de 0.5 segundos entre cada cambio de escena sin desfasar el audio gracias al cálculo de headroom adaptativo.
- **Quemado de Subtítulos:** Inyecta subtítulos con borde negro sólido y sombra (`MarginV=35`, fuente Arial negrita), garantizando contraste y legibilidad según WCAG en cualquier fondo.
- **Exportación:** Produce el archivo [`output/video_final.mp4`](file:///c:/Users/simon/OneDrive/Documents/Videos%20educativos/output/video_final.mp4) a **1080p (1920x1080) @ 30 FPS**.

### 6. `src/youtube_uploader.py` (Publicación en YouTube)
- Utiliza la API oficial `google-api-python-client` y `google-auth-oauthlib`.
- Sube el video mediante transferencia reanudable (resumable upload) reportando el porcentaje de carga.
- Configura automáticamente título, descripción, etiquetas y estado de privacidad (`private`, `unlisted`, `public`).
- Guarda el token en `token.json` tras el primer inicio de sesión para no solicitar autorización recurrente.

### 6. `src/social_copywriter.py` (Copys y Hashtags Especializados con IA)
- Genera textos hiper-optimizados según las dinámicas de cada red social usando Gemini o DeepSeek con validación estricta Pydantic:
  - **YouTube Shorts:** Título con gancho (<58 caracteres + `#Shorts`), descripción SEO y pregunta para comentario fijado.
  - **Instagram Reels:** Gancho con emoji para retener antes de "...más", caption ordenado, llamada a la acción y 18 hashtags estratégicos.
  - **TikTok:** Texto conciso (<200 caracteres) y hashtags de alto descubrimiento viral (`#fyp`, `#parati`, `#aprendecontiktok`).
  - Generador determinista de contingencia para disponibilidad 100% garantizada.

### 7. `src/buffer_publisher.py` (Publicación 100% Automática vía Buffer GraphQL API)
- Conexión oficial directa con la API GraphQL de Buffer (`https://api.buffer.com`).
- **Autodescubrimiento Dinámico de Canales:** Detecta automáticamente tus canales vinculados de YouTube Shorts, Instagram Reels y TikTok.
- **Alojamiento Automático de Video:** Provee la URL directa segura requerida por Buffer para procesar el archivo.
- **Distribución Simultánea con un Clic:** Publica en las 3 plataformas a la vez con título optimizado, categorización educativa, captions nativos y hashtags virales específicos.

### 8. `src/multiplatform_publisher.py` (Orquestador Multi-Plataforma Híbrido)
- **Subida Directa por API / Buffer:** Publica simultáneamente vía Buffer GraphQL API, YouTube Data API v3, Meta Graph API y TikTok API.
- **Paquete de Publicación Listo (`output/social_packages/<slug>_<timestamp>/`):** Siempre exporta el video vertical junto con `youtube_shorts.txt`, `instagram_reels.txt`, `tiktok.txt`, `README.txt` y `social_manifest.json`.

---

## 🎛️ Opciones de CLI (`main.py`)

| Argumento | Descripción | Valor por Defecto |
| :--- | :--- | :--- |
| `--topic` | Uno o varios temas (ej: `--topic "Tema 1" "Tema 2"`) | `"La teoria de la muerte y el multiverso"` |
| `--topics-file` | Archivo `.txt` con un tema por línea (procesamiento Batch) | `None` |
| `--aspect-ratio` | Escala visual: `9:16` (Vertical Shorts/Reels/TikTok) o `16:9` (Horizontal) | `9:16` |
| `--duration-minutes` | Duración objetivo en minutos (ej: 0.5 para 30s, 1.0 para Shorts, 3.5 para documental) | `1.0` |
| `--target-words` | Cantidad explícita de palabras para el guion | Automático (~140 ppm) |
| `--output-dir` | Directorio donde se acumulan los videos generados | `output/` |
| `--output-name` | Nombre de archivo específico (solo para video individual) | Automático (`<slug>_<ratio>_<fecha>.mp4`) |
| `--publish`, `--publish-all` | Genera copys con IA y publica/prepara en Shorts, Reels y TikTok | `False` |
| `--publish-platforms` | Plataformas específicas (`youtube`, `instagram`, `tiktok`, `all`) | Todas si se usa `--publish-all` |
| `--no-social-pack` | No generar la carpeta de paquete local en `output/social_packages/` | `False` |
| `--llm-provider` | Proveedor LLM (`gemini`, `deepseek`) | `gemini` |
| `--tts-provider` | Proveedor TTS (`elevenlabs`, `edge-tts`) | `edge-tts` |
| `--image-provider` | Proveedor de imágenes (`imagen`, `fal`, `pollinations`, `pexels`) | `pollinations` |
| `--skip-script` | Usa `assets/script.json` existente sin llamar al LLM | `False` |
| `--skip-audio` | Usa audio existente sin llamar a TTS | `False` |
| `--skip-alignment` | Salta Whisper y usa alineación previa | `False` |
| `--skip-images` | Usa imágenes existentes en disco | `False` |
| `--skip-video` | Salta el renderizado final de video | `False` |
| `--no-subtitles` | No quema subtítulos en el video | `False` |
| `--upload` | Sube únicamente a YouTube vía API v3 | `False` |
| `--privacy` | Privacidad en YouTube (`private`, `unlisted`, `public`) | `private` |
| `--dry-run` | Valida credenciales y configuración sin renderizar | `False` |
| `--clean` | Limpia archivos temporales antes de empezar | `False` |

---

## 🔑 Configurar YouTube OAuth (Paso a Paso)

1. Ve a [Google Cloud Console](https://console.cloud.google.com/).
2. Crea un proyecto y habilita **YouTube Data API v3**.
3. En la sección **Pantalla de consentimiento de OAuth**, selecciona tipo de usuario **Externo** y añade tu correo como usuario de prueba.
4. En **Credenciales**, haz clic en **Crear credenciales** -> **ID de cliente de OAuth**.
5. Selecciona **Tipo de aplicación: Aplicación de escritorio (Desktop App)**.
6. Descarga el archivo JSON y renómbralo como `client_secrets.json` en la raíz de este proyecto.
7. Al ejecutar con `--upload`, se abrirá el navegador para autorizar una única vez.
