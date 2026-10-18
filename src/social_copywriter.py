"""
Módulo Generador de Copies y Hashtags Especializados para Redes Sociales.
Utiliza IA (Gemini / DeepSeek) con esquemas estructurados Pydantic para producir:
1. YouTube Shorts: Título de alto impacto (<60 chars + #Shorts), descripción SEO, tags y comentario fijado.
2. Instagram Reels: Gancho de primera línea (hook con emoji), cuerpo explicativo limpio, CTA y 18 hashtags.
3. TikTok: Texto viral ultra-conciso (<220 chars) y 6 hashtags de tendencia (#fyp, #parati, #aprendecontiktok).

Incluye respaldo algorítmico determinista para garantizar disponibilidad 100%.
"""
import json
import re
from typing import List, Optional
from pydantic import BaseModel, Field

from src.config import settings
from src.logger import logger

# Origen de los últimos textos generados: "ia" o "plantilla" (si fallaron todos los modelos), para avisar en la interfaz
LAST_COPY_SOURCE = "ia"


class YouTubeShortsPost(BaseModel):
    title: str = Field(description="Título irresistible de menos de 60 caracteres que incluye al final '#Shorts'")
    description: str = Field(description="Descripción estructurada para YouTube Shorts con llamada a la acción y pregunta para debate")
    tags: List[str] = Field(description="Lista de 8 a 15 etiquetas clave optimizadas para el algoritmo de YouTube")
    pinned_comment: str = Field(description="Pregunta intrigante para fijar en el primer comentario y disparar retención y comentarios")


class InstagramReelsPost(BaseModel):
    hook_line: str = Field(description="Primera línea potente con emoji para atrapar la atención antes del botón '...más'")
    caption: str = Field(description="Texto completo del post con párrafos limpios, curiosidad y llamada a la acción ('Guarda este video')")
    hashtags: List[str] = Field(description="Lista de 15 a 20 hashtags estratégicos combinando nicho, temáticos y alto alcance")


class TikTokPost(BaseModel):
    hook: str = Field(description="Frase de gancho directo para el espectador")
    caption: str = Field(description="Texto ultra-conciso de menos de 200 caracteres para acompañar el video sin estorbar la pantalla")
    hashtags: List[str] = Field(description="Lista de 5 a 7 hashtags de alto rendimiento viral (#fyp, #parati, #aprendecontiktok, etc.)")


class SocialBundle(BaseModel):
    topic: str = Field(description="Tema central del video")
    youtube_shorts: YouTubeShortsPost
    instagram_reels: InstagramReelsPost
    tiktok: TikTokPost


def _build_social_prompt(topic: str, narration_summary: str, duration_seconds: float) -> str:
    return f"""Eres el estratega de crecimiento y viralidad en redes sociales de mayor rendimiento para canales de divulgación científica, histórica y educativa en español.
Tu objetivo es redactar los copies (textos), ganchos (hooks) y hashtags definitivos para publicar un video vertical (Shorts / Reels / TikTok) sobre:
TEMA: '{topic}'
DURACIÓN: ~{duration_seconds:.0f} segundos.
RESUMEN DEL GUION:
"{narration_summary[:600]}"

REGLAS ESPECÍFICAS POR PLATAFORMA:

1. YOUTUBE SHORTS:
   - Título: Máximo 58 caracteres. Debe generar curiosidad extrema o sorpresa. Terminar OBLIGATORIAMENTE con "#Shorts".
   - Descripción: 2 a 3 oraciones bien estructuradas, invitando a suscribirse.
   - Tags: Palabras clave precisas de búsqueda en YouTube.
   - Pinned Comment: Pregunta abierta y desafiante para que la gente comente.

2. INSTAGRAM REELS:
   - Hook line: Una sola línea impactante con emojis que detenga el dedo al hacer scroll.
   - Caption: Texto agradable de leer con saltos de línea claros, aportando 1 dato revelador del tema.
   - CTA: Llamada a guardar el Reel ("💡 Guarda este Reel para no olvidarlo y compártelo con alguien curioso").
   - Hashtags: Entre 16 y 20 hashtags sin tildes ni caracteres extraños (ej: #curiosidades #ciencia #aprender #historia #reelsinstagram).

3. TIKTOK:
   - Formato ultra-rápido: El texto de TikTok no debe ser largo (idealmente entre 100 y 180 caracteres totales).
   - Hook corto y directo.
   - Hashtags: Exactamente entre 5 y 7 hashtags: incluir '#fyp', '#parati', '#aprendecontiktok' y hashtags temáticos directos.

Todos los textos deben redactarse en español neutro, natural y magnético.
"""


def _generate_with_gemini(
    topic: str,
    narration_summary: str,
    duration_seconds: float,
    model_name: Optional[str] = None,
) -> SocialBundle:
    """Genera el paquete de copies con Google Gemini."""
    target_model = model_name or settings.GEMINI_MODEL
    logger.info("Generando copies y hashtags para redes sociales con Google Gemini ({})...", target_model)
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    prompt = _build_social_prompt(topic, narration_summary, duration_seconds)

    response = client.models.generate_content(
        model=target_model,
        contents=[f"Genera los copies para: '{topic}'\n{prompt}"],
        config=types.GenerateContentConfig(
            temperature=0.7,
            response_mime_type="application/json",
            response_schema=SocialBundle,
        ),
    )

    if not response.text:
        raise ValueError(f"Google Gemini ({target_model}) devolvió una respuesta vacía al generar copies sociales.")

    data = json.loads(response.text)
    return SocialBundle.model_validate(data)


def _generate_with_gemini_cascade(
    topic: str,
    narration_summary: str,
    duration_seconds: float,
) -> SocialBundle:
    """
    Ejecuta una cascada ordenada de modelos Gemini para generar copies sociales,
    sorteando rate limits (429) y picos de carga (503).
    """
    candidate_models = settings.get_gemini_model_candidates()
    last_error: Optional[Exception] = None

    for idx, model in enumerate(candidate_models, 1):
        try:
            logger.info("Cascada Gemini Copies [{}/{}]: Intentando modelo '{}'...", idx, len(candidate_models), model)
            bundle = _generate_with_gemini(
                topic=topic,
                narration_summary=narration_summary,
                duration_seconds=duration_seconds,
                model_name=model,
            )
            logger.success("Copies sociales generados con éxito por Gemini modelo '{}'", model)
            return bundle
        except Exception as e:
            last_error = e
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                logger.warning("Cuota agotada en Gemini '{}' (429). Saltando al siguiente modelo en cascada...", model)
            elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                logger.warning("Alta demanda en Gemini '{}' (503). Saltando al siguiente modelo en cascada...", model)
            else:
                logger.warning("Error en Gemini '{}' al generar copies: {}. Probando siguiente...", model, err_msg)

    raise RuntimeError(
        f"Todos los modelos de la cascada Gemini ({candidate_models}) fallaron al generar copies. Último error: {last_error}"
    )


def _generate_with_deepseek(topic: str, narration_summary: str, duration_seconds: float) -> SocialBundle:
    """Genera el paquete de copies con DeepSeek."""
    logger.info("Generando copies y hashtags para redes sociales con DeepSeek ({})...", settings.DEEPSEEK_MODEL)
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )
    prompt = _build_social_prompt(topic, narration_summary, duration_seconds)

    response = client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Genera los copies en formato JSON para el tema: '{topic}'"},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("DeepSeek devolvió una respuesta vacía.")

    data = json.loads(content)
    return SocialBundle.model_validate(data)


def _generate_deterministic_social_fallback(topic: str, narration_summary: str) -> SocialBundle:
    """Genera copys y hashtags de alta retención mediante plantillas analíticas sin consumo de API."""
    clean_topic = topic.strip().title()
    slug_tag = re.sub(r"[^\w]", "", clean_topic)

    # 1. YouTube Shorts
    yt_title = f"¿Lo sabías? El secreto de {clean_topic} #Shorts"[:58]
    if not yt_title.endswith("#Shorts"):
        yt_title = yt_title[:50].rstrip() + " #Shorts"

    yt_desc = (
        f"Descubre la fascinante historia y los misterios detrás de {clean_topic}. "
        "Un recorrido visual imprescindible para mentes curiosas.\n\n"
        "🔔 Suscríbete para aprender algo nuevo todos los días.\n"
        f"#{slug_tag} #Shorts #Aprender #Documental #Curiosidades"
    )
    yt_tags = [
        clean_topic,
        "Shorts",
        "Educacion",
        "Ciencia",
        "Historia",
        "Curiosidades",
        "Documental",
        "Sabias Que",
        "Datos Curiosos",
        "Cultura General",
    ]
    yt_pinned = f"¿Qué es lo que más te sorprende sobre {clean_topic}? ¡Te leo en los comentarios! 👇"

    # 2. Instagram Reels
    ig_hook = f"🤯 Lo que NADIE te contó sobre {clean_topic}:"
    ig_caption = (
        f"{ig_hook}\n\n"
        f"A lo largo del tiempo, pocos temas han ocultado tantos enigmas como {clean_topic}. "
        "En menos de un minuto te contamos el dato clave que cambia toda la perspectiva.\n\n"
        "💡 Guarda este Reel para repasarlo luego y compártelo con alguien que adore aprender cosas nuevas.\n\n"
        "👉 Síguenos para descubrir revelaciones diarias de ciencia, historia y conocimiento."
    )
    ig_hashtags = [
        f"#{slug_tag.lower()}",
        "#curiosidades",
        "#sabiasque",
        "#datoscuriosos",
        "#aprender",
        "#conocimiento",
        "#historia",
        "#ciencia",
        "#educacion",
        "#culturageneral",
        "#reelsinstagram",
        "#reelsviral",
        "#viralreels",
        "#datodeldia",
        "#documental",
        "#increible",
        "#mentescabadas",
    ]

    # 3. TikTok
    tk_hook = f"¿Sabías esto sobre {clean_topic}? 😱"
    tk_caption = f"{tk_hook} El enigma que los libros rara vez explican. ¡Mira hasta el final!"
    tk_hashtags = [
        "#fyp",
        "#parati",
        "#aprendecontiktok",
        f"#{slug_tag.lower()}",
        "#curiosidades",
        "#sabiasque",
        "#viral",
    ]

    return SocialBundle(
        topic=clean_topic,
        youtube_shorts=YouTubeShortsPost(
            title=yt_title,
            description=yt_desc,
            tags=yt_tags,
            pinned_comment=yt_pinned,
        ),
        instagram_reels=InstagramReelsPost(
            hook_line=ig_hook,
            caption=ig_caption,
            hashtags=ig_hashtags,
        ),
        tiktok=TikTokPost(
            hook=tk_hook,
            caption=tk_caption,
            hashtags=tk_hashtags,
        ),
    )


def generate_social_copy(
    topic: str,
    narration_summary: str = "",
    duration_seconds: float = 60.0,
    provider: Optional[str] = None,
) -> SocialBundle:
    """
    Punto de entrada principal para generar los copies de todas las redes sociales.
    Intenta LLM seleccionado (Gemini o DeepSeek) y recurre automáticamente a plantilla optimizada ante cualquier eventualidad.
    """
    global LAST_COPY_SOURCE
    LAST_COPY_SOURCE = "ia"
    selected_provider = (provider or settings.LLM_PROVIDER).lower()

    if selected_provider == "deepseek" and settings.DEEPSEEK_API_KEY and settings.DEEPSEEK_API_KEY != "tu_clave_deepseek_aqui":
        try:
            return _generate_with_deepseek(topic, narration_summary, duration_seconds)
        except Exception as e:
            logger.warning("Fallo al generar copies con DeepSeek: {}. Probando cascada de Gemini...", e)

    if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "tu_clave_gemini_aqui":
        try:
            return _generate_with_gemini_cascade(topic, narration_summary, duration_seconds)
        except Exception as e:
            logger.warning("Fallo en cascada de Gemini para copies: {}. Intentando alternativa...", e)

    if selected_provider != "deepseek" and settings.DEEPSEEK_API_KEY and settings.DEEPSEEK_API_KEY != "tu_clave_deepseek_aqui":
        try:
            return _generate_with_deepseek(topic, narration_summary, duration_seconds)
        except Exception as e:
            logger.warning("Fallo alternativo con DeepSeek para copies: {}", e)

    logger.warning("Ningún modelo redactó los textos: se usa la plantilla automática para '{}'", topic)
    LAST_COPY_SOURCE = "plantilla"
    return _generate_deterministic_social_fallback(topic, narration_summary)
