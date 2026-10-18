"""
Módulo Generador de Guion y Prompts Visuales.
Soporta videos de larga duración (3 a 5 minutos, 450 a 750 palabras, 15 a 25 escenas).
Utiliza:
- Google Gemini (vía SDK google-genai con esquema Pydantic)
- DeepSeek (vía protocolo OpenAI)
"""
import json
import re
from typing import List, Optional
from pydantic import BaseModel, Field

from src.config import settings
from src.logger import logger


class VideoMetadata(BaseModel):
    title: str = Field(description="Título cautivador y optimizado para alto CTR en YouTube")
    description: str = Field(description="Descripción estructurada para SEO de YouTube con llamada a la acción y marcas de tiempo")
    tags: List[str] = Field(description="Lista de 10 a 20 etiquetas relevantes para posicionamiento en YouTube")


class VisualContract(BaseModel):
    era_setting: str = Field(
        description="Contexto histórico, temporal y espacial coherente (ej: 'Early 1970s, Pacific Northwest, commercial aviation')"
    )
    art_style: str = Field(
        description="Estilo cinematográfico fotográfico auténtico adecuado a la época (ej: 'Cinematic 35mm documentary film still, Kodak Vision3 500T texture, fine realistic film grain, Panavision anamorphic lens, moody shadows, realistic photography, no CGI look, no cartoon')"
    )
    color_palette: str = Field(
        description="Paleta cromática uniforme de 2 a 3 tonos dominantes compartida por todas las escenas (ej: 'Muted slate teal, warm tungsten cabin light, rain-soaked asphalt gray')"
    )
    lighting_atmosphere: str = Field(
        description="Atmósfera de iluminación envolvente y coherente (ej: 'Low-key atmospheric lighting, diffused storm illumination, high contrast specular highlights')"
    )
    character_anchor: Optional[str] = Field(
        default=None,
        description="Descripción canónica y fija del personaje o sujeto principal para mantener consistencia de vestuario y rasgos"
    )
    shot_progression_rules: str = Field(
        description="Reglas de dirección cinematográfica para evitar face-morphing (priorizar planos detalle, macro, siluetas, tomas over-the-shoulder y tomas de ambiente)"
    )
    archive_search_terms: Optional[str] = Field(
        default=None,
        description="Nombre canónico en inglés del evento, persona o tema tal como aparece en archivos fotográficos (ej: 'Emu War', 'Emperor Norton', 'Jordan Belfort'). 1 a 4 palabras, sin adjetivos."
    )


class Scene(BaseModel):
    scene_id: int = Field(description="Número de escena secuencial (1, 2, 3...)")
    narration_text: str = Field(description="Texto exacto a ser narrado para esta escena (1 a 2 oraciones, 20 a 35 palabras)")
    shot_type: Optional[str] = Field(
        default="macro_detail",
        description="Tipo de plano cinemático: 'macro_detail' (manos, notas, objetos clave), 'over_the_shoulder', 'silhouette_backlight', 'environmental_wide', 'dramatic_close_up', 'medium_action'"
    )
    visual_prompt: str = Field(
        description="Prompt en inglés ultra-específico describiendo la acción física exacta y sujeto focal de ese momento, sin texto ni marcas de agua"
    )
    search_keywords: Optional[str] = Field(
        default=None,
        description="Términos de búsqueda visual en inglés (3 a 6 palabras) para archivo documental o histórico si corresponde"
    )
    archive_queries: Optional[List[str]] = Field(
        default=None,
        description="2 a 3 consultas en inglés para buscar FOTOGRAFÍAS REALES de archivo de esta escena (personas, lugares, objetos o hechos concretos que existieron), de más específica a más general"
    )
    start_time: Optional[float] = Field(default=None, description="Segundo de inicio en la línea de tiempo")
    end_time: Optional[float] = Field(default=None, description="Segundo de finalización en la línea de tiempo")
    duration: Optional[float] = Field(default=None, description="Duración exacta en segundos")


class ScriptOutput(BaseModel):
    metadata: VideoMetadata
    visual_contract: Optional[VisualContract] = Field(
        default=None,
        description="Contrato de estilo visual y biblia de coherencia cinematográfica para todo el video"
    )
    narration_full: str = Field(description="Guion completo concatenado para narración continua")
    scenes: List[Scene] = Field(description="Lista de escenas ordenadas secuencialmente")
    hook_text: Optional[str] = Field(
        default=None,
        description="Texto de gancho que se muestra en pantalla los primeros 2,5 segundos: máximo 8 palabras, la contradicción o promesa más fuerte del video, sin emojis ni hashtags"
    )
    closing_question: Optional[str] = Field(
        default=None,
        description="Pregunta directa y corta (máximo 12 palabras) al espectador con la que termina la narración, para invitar a comentar"
    )


def _build_system_prompt(duration_minutes: float, target_words: int, num_scenes: int, aspect_ratio: str = "16:9") -> str:
    is_vertical = aspect_ratio == "9:16"
    format_desc = "VERTICAL 9:16 (Shorts/Reels/TikTok)" if is_vertical else "PANORÁMICO 16:9 (Documental horizontal)"
    ratio_guidance = (
        "Es un video VERTICAL 9:16 para smartphones (TikTok/Shorts/Reels). Cada escena debe ser concebida en orientación vertical ('vertical 9:16 framing, mobile format'), con el sujeto focal perfectamente encuadrado en el tercio superior o medio para no ser tapado por los subtítulos inferiores."
        if is_vertical
        else "Es un video PANORÁMICO 16:9 cinematográfico."
    )

    return f"""Eres un Director de Cine y Documentales de Prestigio (estilo David Fincher, Christopher Nolan, HBO Documentaries) y Director de Fotografía experto en retención visual.
Tu misión es diseñar un guion audiovisual {format_desc} de ~{duration_minutes:.1f} minutos, estableciendo una BIBLIA DE COHERENCIA VISUAL ('visual_contract') y escenas cinematográficas con tensión dramática.

PARÁMETROS DE PRODUCCIÓN NARRATIVA:
1. Longitud total: Alrededor de {target_words} palabras narradas (ritmo cautivador de ~140 palabras por minuto).
2. División en escenas: EXACTAMENTE entre {max(3, num_scenes - 1)} y {num_scenes + 1} escenas.
3. Cada escena contiene entre 20 y 35 palabras (~6 a 12 segundos de locución por escena).
4. El guion debe estar redactado en español neutro, apasionante, riguroso y con giros que mantengan al espectador pegado a la pantalla.
5. 'narration_full' debe ser exactamente la concatenación de todas las escenas en orden.

DIRECTRICES DE COHERENCIA VISUAL (VISUAL CONTRACT & ANTI-FACE-MORPHING):
6. 'visual_contract': Define primero la biblia visual obligatoria para TODO el video:
   - 'era_setting': Época histórica y ambientación espacial coherente con el tema.
   - 'art_style': Estilo cinematográfico fotográfico auténtico adecuado al tema (ej: para historia usar 'Cinematic 35mm documentary film still, Kodak Vision3 500T, fine realistic grain, Panavision anamorphic lens, moody shadows, realistic photography'; NUNCA usar 'unreal engine 5', 'sci-fi concept art' ni videojuegos para hechos históricos reales).
   - 'color_palette': Paleta de 2 o 3 colores dominantes para unificar todas las escenas (ej: 'Muted slate teal, warm tungsten amber, moody charcoal black').
   - 'lighting_atmosphere': Iluminación envolvente consistente (ej: 'Low-key atmospheric lighting, diffused rain highlights, soft haze').
   - 'character_anchor': Si hay un protagonista (ej: D.B. Cooper, emperador, científico), define su descripción canónica exacta (vestimenta, peinado, accesorios distintivos).
   - 'shot_progression_rules': Regla estricta de dirección para evitar rostros mutantes.
   - 'archive_search_terms': Nombre canónico en inglés del evento, persona o tema tal como aparecería en Wikimedia Commons (ej: 'Emu War', 'Emperor Norton'). Se usa para encontrar fotografías reales del hecho.

7. REGLA DE ORO DE PLANOS DETALLE (ANTI FACE-MORPHING):
   - NUNCA repitas retratos genéricos del rostro de frente del protagonista en múltiples escenas, ya que la IA cambiará sus facciones y destruirá la inmersión.
   - Aplica dirección cinematográfica de misterio y prestigio:
     * 'macro_detail': Planos detalle de manos, notas escritas, dinero, relojes, instrumentos, mapas, huellas, objetos clave en tensión.
     * 'over_the_shoulder': Planos desde la espalda del sujeto observando la escena.
     * 'silhouette_backlight': Silueta del sujeto a contraluz contra una ventana o foco de luz.
     * 'environmental_wide': Planos de ambiente amplios (un lago en la niebla, un bosque alpino, una bóveda bancaria desierta).
     * 'dramatic_close_up': Solo cuando sea un objeto, mirada en sombra o detalle extremo.

8. REGLA ESTRICTA ANTI-PROMPT-POISONING (CERO HUMANOS ESPURIOS):
   - NUNCA uses la palabra 'portrait' en 'visual_prompt', pues los modelos de difusión la interpretan erróneamente como un retrato humano de estudio. Usa 'vertical 9:16 framing'.
   - Si la escena describe un entorno, artefacto, naturaleza, lago, vehículo o documento (especialmente 'environmental_wide' o 'macro_detail'), debes incluir explícitamente: 'uninhabited scene, no people, no portraits, archival artifact' para evitar que la IA dibuje personas fuera de contexto.

9. Para cada escena, escribe un 'visual_prompt' en inglés ultra-específico:
   - Describe la ACCIÓN FÍSICA EXACTA que se está relatando en esa escena específica (no conceptos abstractos).
   - Debe alinearse estrictamente con el 'visual_contract' y especificar el ángulo de cámara ('shot_type').
   - Formato {aspect_ratio}: {'vertical 9:16 framing, mobile safe zone' if is_vertical else 'cinematic 16:9 widescreen'}.
   - Termina siempre especificando: 'cinematic film still, photorealistic, 8k, no text, no watermark, no captions'.
10. Para cada escena, incluye 'search_keywords' con 2 a 4 términos esenciales y directos en inglés que representen el objeto, vehículo, lugar o sujeto físico tangible (ej: 'vintage coach bus', 'hotel ballroom', 'signing contract pen', 'vintage race car'), evitando frases largas para que las APIs de archivo fotográfico encuentren coincidencias exactas.
10b. Para cada escena, incluye 'archive_queries': 2 a 3 consultas en inglés pensadas para encontrar fotografías REALES en Wikimedia Commons o bibliotecas públicas, nombrando cosas que existieron (ej: 'Sir George Pearce', 'Australian Parliament House 1930s', 'Western Australia wheat farm 1930s'), de más específica a más general. No describas el encuadre ni la luz.
11. Metadatos optimizados para YouTube: Título con alto gancho emocional (añade '#Shorts' si es 9:16), descripción completa y tags relevantes.

RETENCIÓN EN LOS PRIMEROS 2 SEGUNDOS Y COMENTARIOS (la mayoría de espectadores decide en el segundo 2):
12. 'hook_text': máximo 8 palabras que se mostrarán en grande en pantalla al empezar. Debe ser la contradicción, sorpresa o promesa más fuerte de la historia, entendible sin contexto (ej: 'No estaba en una cueva. Vivía frente al ejército', 'Australia perdió una guerra contra pájaros'). Sin emojis, sin hashtags, sin comillas.
13. La ESCENA 1 abre directamente con esa idea: su primera frase narrada plantea el gancho, sin introducciones ni contexto previo. Su 'visual_prompt' y sus 'archive_queries' deben apuntar al sujeto MÁS ICÓNICO y reconocible del tema (el protagonista, el lugar o el hecho real), nunca a un plano de ambiente vacío u oscuro.
14. 'closing_question': pregunta directa y corta al espectador (máximo 12 palabras) que invite a comentar una opinión o dato (ej: '¿Tú habrías comprado tierras en Poyais?'). La ÚLTIMA escena debe terminar narrando exactamente esa pregunta, y 'narration_full' también.
"""



def _clean_json_response(raw_text: str) -> str:
    """Limpia bloques de código markdown de una respuesta JSON."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def _generate_with_gemini(
    topic: str,
    duration_minutes: float,
    target_words: int,
    num_scenes: int,
    aspect_ratio: str = "16:9",
    model_name: Optional[str] = None,
) -> ScriptOutput:
    """Genera el guion de larga duración utilizando la API de Google Gemini."""
    target_model = model_name or settings.GEMINI_MODEL
    logger.info("Solicitando guion documental a Google Gemini ({}) - Objetivo: {:.1f} min ({} palabras, {} escenas, formato: {})", target_model, duration_minutes, target_words, num_scenes, aspect_ratio)
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    system_prompt = _build_system_prompt(duration_minutes, target_words, num_scenes, aspect_ratio)
    
    user_prompt = (
        f"Tema del documental: '{topic}'\n"
        f"Formato: {aspect_ratio}\n"
        f"Duración requerida: {duration_minutes:.1f} minutos.\n"
        f"Total de palabras aproximado: {target_words}.\n"
        f"Estructura en aproximadamente {num_scenes} escenas cortas (6 a 12 segundos por escena)."
    )

    response = client.models.generate_content(
        model=target_model,
        contents=[user_prompt],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
            response_mime_type="application/json",
            response_schema=ScriptOutput,
        ),
    )

    if not response.text:
        raise ValueError(f"Google Gemini ({target_model}) devolvió una respuesta vacía.")

    data = json.loads(response.text)
    return ScriptOutput.model_validate(data)


def _generate_with_gemini_cascade(
    topic: str,
    duration_minutes: float,
    target_words: int,
    num_scenes: int,
    aspect_ratio: str = "16:9",
) -> ScriptOutput:
    """
    Ejecuta una cascada de modelos Gemini (3.8-flash, 3.7-flash, 3.6-flash, 3.5-flash, 2.5-flash, etc.)
    garantizando que ante errores 429 (Resource Exhausted / Rate Limit) o 503 (High Demand / Unavailable)
    se pase automáticamente al siguiente modelo sin caer en heurísticas genéricas.
    """
    candidate_models = settings.get_gemini_model_candidates()
    last_error: Optional[Exception] = None

    for idx, model in enumerate(candidate_models, 1):
        try:
            logger.info("Cascada Gemini [{}/{}]: Solicitando guion a '{}'...", idx, len(candidate_models), model)
            script = _generate_with_gemini(
                topic=topic,
                duration_minutes=duration_minutes,
                target_words=target_words,
                num_scenes=num_scenes,
                aspect_ratio=aspect_ratio,
                model_name=model,
            )
            logger.success("Guion documental generado exitosamente con Gemini modelo '{}'", model)
            return script
        except Exception as e:
            last_error = e
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                logger.warning(
                    "Cuota / Rate Limit agotado para Gemini '{}' (429). Saltando de inmediato al siguiente modelo en cascada...",
                    model
                )
            elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                logger.warning(
                    "Alta demanda temporal en Gemini '{}' (503). Saltando al siguiente modelo en cascada...",
                    model
                )
            else:
                logger.warning("Fallo en Gemini '{}': {}. Probando siguiente modelo en cascada...", model, err_msg)

    raise RuntimeError(
        f"Todos los modelos de la cascada Gemini ({candidate_models}) fallaron. Último error: {last_error}"
    )


def _generate_with_deepseek(topic: str, duration_minutes: float, target_words: int, num_scenes: int, aspect_ratio: str = "16:9") -> ScriptOutput:
    """Genera el guion de larga duración utilizando la API de DeepSeek."""
    logger.info("Solicitando guion documental a DeepSeek ({}) - Objetivo: {:.1f} min (formato: {})", settings.DEEPSEEK_MODEL, duration_minutes, aspect_ratio)
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )

    system_prompt = _build_system_prompt(duration_minutes, target_words, num_scenes, aspect_ratio)
    json_schema_hint = json.dumps(ScriptOutput.model_json_schema(), ensure_ascii=False)
    user_prompt = (
        f"Tema: '{topic}'\n"
        f"Formato: {aspect_ratio}\n"
        f"Duración: {duration_minutes:.1f} minutos, ~{target_words} palabras, {num_scenes} escenas.\n"
        f"Responde ÚNICAMENTE un objeto JSON válido según este esquema:\n{json_schema_hint}"
    )

    response = client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("DeepSeek devolvió una respuesta vacía.")

    cleaned_json = _clean_json_response(content)
    data = json.loads(cleaned_json)
    return ScriptOutput.model_validate(data)


def generate_script(
    topic: str,
    duration_minutes: float = 3.5,
    target_words: Optional[int] = None,
    provider: Optional[str] = None,
    aspect_ratio: str = "16:9",
) -> ScriptOutput:
    """
    Punto de entrada principal para generar el guion y metadatos.
    Calcula dinámicamente palabras y escenas para la duración objetivo y aspect ratio.
    Utiliza una robusta cascada de modelos Gemini (3.8-flash, 3.7-flash, 3.6-flash, 3.5-flash, 2.5-flash, etc.)
    para sortear rate limits y picos de demanda, evitando heurísticas pre-programadas.
    """
    # Ritmo estándar de 140 palabras por minuto
    calculated_words = target_words or int(duration_minutes * 140)
    # Entre 3 y 25 escenas adaptadas al metraje real (promedio de 7 a 11 segundos por escena)
    calculated_scenes = max(3, min(25, int(duration_minutes * 5.5)))

    selected_provider = (provider or settings.LLM_PROVIDER).lower()

    # 1. Si se eligió DeepSeek específicamente, intentarlo primero
    if selected_provider == "deepseek" and settings.DEEPSEEK_API_KEY and settings.DEEPSEEK_API_KEY != "tu_clave_deepseek_aqui":
        try:
            return _generate_with_deepseek(topic, duration_minutes, calculated_words, calculated_scenes, aspect_ratio=aspect_ratio)
        except Exception as e:
            logger.error("Fallo con DeepSeek: {}. Pasando a cascada de Gemini...", e)

    # 2. Cascada de modelos Gemini
    if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "tu_clave_gemini_aqui":
        try:
            return _generate_with_gemini_cascade(topic, duration_minutes, calculated_words, calculated_scenes, aspect_ratio=aspect_ratio)
        except Exception as e:
            logger.error("Fallo en cascada completa de Gemini: {}", e)

    # 3. Reintento alternativo con DeepSeek si aún no se ha probado
    if selected_provider != "deepseek" and settings.DEEPSEEK_API_KEY and settings.DEEPSEEK_API_KEY != "tu_clave_deepseek_aqui":
        try:
            return _generate_with_deepseek(topic, duration_minutes, calculated_words, calculated_scenes, aspect_ratio=aspect_ratio)
        except Exception as e:
            logger.error("Fallo alternativo con DeepSeek: {}", e)

    # 4. Sin plantillas de contingencia: un guion genérico no tiene calidad para publicarse
    raise RuntimeError(
        f"No se pudo generar el guion documental para '{topic}' mediante IA. "
        "Todos los modelos de la cascada fallaron (límite de uso o saturación temporal); reintenta más tarde."
    )


def save_script_to_disk(script_output: ScriptOutput, target_path = None) -> None:
    """Persiste el guion estructurado en formato JSON en disco."""
    path = target_path or settings.SCRIPT_JSON_PATH
    with open(path, "w", encoding="utf-8") as f:
        f.write(script_output.model_dump_json(indent=2))
    logger.success("Guion estructurado guardado exitosamente en: {}", path)
