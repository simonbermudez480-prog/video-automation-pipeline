"""
Módulo Generador de Guion y Prompts Visuales.
Soporta videos de larga duración (3 a 5 minutos, 450 a 750 palabras, 15 a 25 escenas).
Utiliza:
- Google Gemini (vía SDK google-genai con esquema Pydantic)
- DeepSeek (vía protocolo OpenAI)
- Generador de guiones de alta densidad documental para contingencia.
"""
import json
import math
import re
from typing import List, Optional
from pydantic import BaseModel, Field

from src.config import settings
from src.logger import logger


class VideoMetadata(BaseModel):
    title: str = Field(description="Título cautivador y optimizado para alto CTR en YouTube")
    description: str = Field(description="Descripción estructurada para SEO de YouTube con llamada a la acción y marcas de tiempo")
    tags: List[str] = Field(description="Lista de 10 a 20 etiquetas relevantes para posicionamiento en YouTube")


class Scene(BaseModel):
    scene_id: int = Field(description="Número de escena secuencial (1, 2, 3...)")
    narration_text: str = Field(description="Texto exacto a ser narrado para esta escena (1 a 2 oraciones, 20 a 35 palabras)")
    visual_prompt: str = Field(
        description="Prompt en inglés detallado para generador de imágenes: estilo cinematográfico documental, 16:9, iluminación dramática, 8k, sin texto"
    )
    search_keywords: Optional[str] = Field(
        default=None,
        description="Términos de búsqueda visual en inglés (3 a 6 palabras) para archivo documental o histórico"
    )
    start_time: Optional[float] = Field(default=None, description="Segundo de inicio en la línea de tiempo")
    end_time: Optional[float] = Field(default=None, description="Segundo de finalización en la línea de tiempo")
    duration: Optional[float] = Field(default=None, description="Duración exacta en segundos")


class ScriptOutput(BaseModel):
    metadata: VideoMetadata
    narration_full: str = Field(description="Guion completo concatenado para narración continua")
    scenes: List[Scene] = Field(description="Lista de escenas ordenadas secuencialmente (entre 15 y 25 escenas)")


def _build_system_prompt(duration_minutes: float, target_words: int, num_scenes: int, aspect_ratio: str = "16:9") -> str:
    is_vertical = aspect_ratio == "9:16"
    format_desc = "VERTICAL 9:16 (Shorts/Reels/TikTok)" if is_vertical else "PANORÁMICO 16:9 (Documental horizontal)"
    ratio_guidance = (
        "Es un video VERTICAL 9:16 para smartphones (TikTok/Shorts/Reels). La composición visual de cada escena debe ser en orientación vertical ('portrait orientation, vertical 9:16 mobile format'), con el sujeto focal perfectamente centrado en el tercio medio."
        if is_vertical
        else "Es un video PANORÁMICO 16:9 cinematográfico."
    )
    style_tag = (
        "vertical 9:16 portrait orientation, mobile format, cinematic 8k, photorealistic, volumetric lighting, unreal engine 5 render, award winning sci-fi concept art, no text, no watermark"
        if is_vertical
        else "cinematic 8k, photorealistic, volumetric lighting, unreal engine 5 render, award winning sci-fi concept art, no text, no watermark"
    )

    return f"""Eres un director audiovisual de documentales científicos e históricos de élite (estilo BBC, Netflix, National Geographic) y estratega de alta retención en YouTube y redes sociales de video vertical.
Tu objetivo es producir un guion completo para un video documental {format_desc} de aproximadamente {duration_minutes:.1f} minutos de duración.

Formato y composición visual: {ratio_guidance}

Parámetros clave de producción:
1. Longitud total: Alrededor de {target_words} palabras narradas (ritmo cautivador de ~140 palabras por minuto).
2. División en escenas: Debes dividir el guion en EXACTAMENTE entre {max(3, num_scenes - 1)} y {num_scenes + 1} escenas cortas y dinámicas.
3. Cada escena debe contener entre 20 y 35 palabras (equivalente a 6 a 12 segundos de locución por escena).
4. El guion debe estar redactado en español neutro, apasionante, riguroso y con giros que mantengan al espectador pegado a la pantalla.
5. 'narration_full' debe ser exactamente la concatenación de todas las escenas en orden.
6. Para cada escena, escribe un 'visual_prompt' en inglés extraordinariamente detallado para un modelo generativo en formato {aspect_ratio}:
   - Debe describir con riqueza el sujeto visual, perspectiva de cámara, colores, ambiente y composición adaptada al formato {aspect_ratio}.
   - Es OBLIGATORIO incluir textualmente los siguientes términos de estilo: "{style_tag}".
7. Para cada escena, incluye 'search_keywords' con 3 a 6 términos clave en inglés que resuman el sujeto exacto para consulta en archivos históricos o científicos.
8. Metadatos optimizados para YouTube: Título con alto gancho emocional y de curiosidad (añade '#Shorts' si el formato es 9:16), descripción completa y lista de tags de alto volumen.
9. Dicción y términos extranjeros: El texto narrado debe sonar fluido y natural al ser leído en voz alta por un locutor hispanohablante. Para conceptos técnicos, científicos o militares, prioriza términos en español natural cuando existan. Si usas nombres propios extranjeros indispensables (ej. 'Pearl Harbor', 'Winston Churchill', 'Blitzkrieg'), asegúrate de que encajen con cadencia rítmica limpia y natural dentro de la oración.
"""



def _clean_json_response(raw_text: str) -> str:
    """Limpia bloques de código markdown de una respuesta JSON."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def _generate_with_gemini(topic: str, duration_minutes: float, target_words: int, num_scenes: int, aspect_ratio: str = "16:9") -> ScriptOutput:
    """Genera el guion de larga duración utilizando la API de Google Gemini."""
    logger.info("Solicitando guion documental a Google Gemini ({}) - Objetivo: {:.1f} min ({} palabras, {} escenas, formato: {})", settings.GEMINI_MODEL, duration_minutes, target_words, num_scenes, aspect_ratio)
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
        model=settings.GEMINI_MODEL,
        contents=[user_prompt],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
            response_mime_type="application/json",
            response_schema=ScriptOutput,
        ),
    )

    if not response.text:
        raise ValueError("Google Gemini devolvió una respuesta vacía.")

    data = json.loads(response.text)
    return ScriptOutput.model_validate(data)


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


def _is_wwii_or_war_topic(topic: str) -> bool:
    t = topic.lower()
    war_terms = [
        "guerra", "mundial", "ww2", "wwii", "world war", "militar",
        "batalla", "soldad", "hitler", "churchill", "stalingrad",
        "normand", "nazi", "aliados", "ejercit", "pearl harbor", "conflicto"
    ]
    return any(term in t for term in war_terms)


def _is_quantum_or_multiverse_topic(topic: str) -> bool:
    t = topic.lower()
    quantum_terms = [
        "multiverso", "cuantic", "cuántic", "everett", "inmortalidad cuantica",
        "suicidio cuantico", "muchos mundos", "superposicion", "schrodinger", "schrödinger"
    ]
    return any(term in t for term in quantum_terms)


def _generate_wwii_fallback_script(aspect_ratio: str = "16:9") -> ScriptOutput:
    """
    Genera un documental histórico completo de 18 escenas sobre la Segunda Guerra Mundial (1939-1945).
    100% enfocado en el conflicto histórico con precisión cronológica y prompts cinemáticos.
    """
    logger.warning("Generando guion documental histórico completo para: 'Segunda Guerra Mundial' (18 escenas, {})", aspect_ratio)
    if aspect_ratio == "9:16":
        style_suffix = ", vertical 9:16 portrait orientation, mobile format, centered composition, cinematic 8k, photorealistic, volumetric lighting, unreal engine 5 render, award winning history concept art, no text, no watermark"
    else:
        style_suffix = ", cinematic 8k, photorealistic, volumetric lighting, unreal engine 5 render, award winning history concept art, no text, no watermark"

    scenes = [
        Scene(
            scene_id=1,
            narration_text="Entre 1939 y 1945, el planeta presenció el enfrentamiento más colosal y devastador de la historia: la Segunda Guerra Mundial, una conflagración que redefinió fronteras, imperios y el destino de la humanidad.",
            visual_prompt="Dramatic cinematic archival photography, wide shot of European wartime 1940s landscape, dramatic stormy skies with beams of sunlight breaking through dark clouds, vintage military map in the foreground, epic documentary scale" + style_suffix,
            search_keywords="World War II Europe map 1939",
        ),
        Scene(
            scene_id=2,
            narration_text="Las semillas del conflicto germinaron en las cenizas de la Primera Guerra Mundial. Las severas sanciones del Tratado de Versalles y la Gran Depresión alimentaron el ascenso del totalitarismo en Europa.",
            visual_prompt="Historical documentary photography, the Hall of Mirrors at Versailles with vintage political delegates seated at tables, dramatic chiaroscuro illumination, sepia tones with rich contrast, 1920s European history" + style_suffix,
            search_keywords="Treaty of Versailles Hall of Mirrors 1919",
        ),
        Scene(
            scene_id=3,
            narration_text="El primero de septiembre de 1939, las tropas alemanas cruzaron la frontera polaca. En respuesta, Gran Bretaña y Francia declararon la guerra, desatando una espiral que pronto envolvería a decenas de naciones.",
            visual_prompt="Authentic historical wartime scene, September 1939 European border barrier being dismantled, military columns advancing on a country road, dramatic documentary film grain, monochrome with subtle sepia warmth" + style_suffix,
            search_keywords="Invasion of Poland September 1939",
        ),
        Scene(
            scene_id=4,
            narration_text="Empleando la revolucionaria táctica de la Blitzkrieg o guerra relámpago, blindados coordinados con aviación rompieron las defensas aliadas en las Ardenas, forzando la sorpresiva capitulación de Francia en 1940.",
            visual_prompt="Cinematic shot of 1940s armored tanks maneuvering through a misty forest road in the Ardennes, smoke in the distance, high contrast dramatic cinematic lighting, authentic historical atmosphere" + style_suffix,
            search_keywords="French campaign 1940 tanks Ardennes",
        ),
        Scene(
            scene_id=5,
            narration_text="Gran Bretaña resistió en solitario. En los cielos sobre Londres y el Canal de la Mancha, pilotos de la Royal Air Force combatieron ferozmente en cazas Spitfire frente a la Luftwaffe durante la Batalla de Inglaterra.",
            visual_prompt="Epic aerial view of British Supermarine Spitfire fighter aircraft soaring through dramatic sunlit clouds over the English Channel coast, propellers spinning, hyper-realistic vintage aviation cinematography" + style_suffix,
            search_keywords="Supermarine Spitfire Battle of Britain 1940",
        ),
        Scene(
            scene_id=6,
            narration_text="En junio de 1941, Alemania quebró el pacto con la Unión Soviética e inició la Operación Barbarroja, movilizando a más de tres millones de soldados a lo largo de un colosal frente de miles de kilómetros.",
            visual_prompt="Vast panoramic view of the Eastern Front steppe under an immense stormy sky, endless military convoys stretching to the horizon, dust clouds, dramatic historical realism" + style_suffix,
            search_keywords="Operation Barbarossa 1941 Eastern Front",
        ),
        Scene(
            scene_id=7,
            narration_text="El 7 de diciembre de 1941, la aviación naval japonesa ejecutó un ataque sorpresa sobre Pearl Harbor en Hawái. El presidente Roosevelt anunció que la fecha viviría en la infamia, y Estados Unidos entró formalmente en la contienda.",
            visual_prompt="Dramatic historical documentary view of Pearl Harbor naval base with naval warships, smoke rising in the distance, dramatic sunrise illumination casting long golden shadows over Pacific waters" + style_suffix,
            search_keywords="Attack on Pearl Harbor December 7 1941",
        ),
        Scene(
            scene_id=8,
            narration_text="Seis meses después, en la Batalla de Midway en junio de 1942, la flota estadounidense hundió cuatro portaaviones japoneses en cuestión de minutos, transformando para siempre el equilibrio de poder en el Pacífico.",
            visual_prompt="Cinematic Pacific Ocean naval confrontation, aircraft carrier navigating vast blue ocean swells, Dauntless dive bombers in formation above, dramatic cinematic lighting, 1942 naval battle" + style_suffix,
            search_keywords="Battle of Midway 1942 aircraft carrier",
        ),
        Scene(
            scene_id=9,
            narration_text="En el Frente Oriental, la Batalla de Stalingrado se convirtió en el punto de inflexión definitivo. Entre escombros y temperaturas extremas, el Ejército Rojo cercó al Sexto Ejército alemán en una victoria decisiva.",
            visual_prompt="Atmospheric historical scene of ruined urban architecture in winter snow, industrial silhouettes against a dramatic freezing sunset, dramatic cinematic realism, Stalingrad 1943 documentary aesthetic" + style_suffix,
            search_keywords="Battle of Stalingrad 1943 ruins winter",
        ),
        Scene(
            scene_id=10,
            narration_text="En las arenas del desierto del Norte de África, los tanques del general británico Montgomery frenaron el avance de Rommel en El Alamein, protegiendo las vitales rutas petrolíferas del Canal de Suez.",
            visual_prompt="Cinematic desert landscape with military armor moving across sweeping golden sand dunes, dust plumes catching the warm desert sun, vast horizon, authentic 1942 North African campaign" + style_suffix,
            search_keywords="Battle of El Alamein 1942 desert tanks",
        ),
        Scene(
            scene_id=11,
            narration_text="Lejos del frente, la guerra total transformó la sociedad. Millones de mujeres asumieron el control de fábricas de armamento, astilleros y suministros, sosteniendo el esfuerzo productivo de las naciones.",
            visual_prompt="Documentary photography of a massive 1940s industrial assembly factory, dramatic shafts of sunlight piercing through industrial windows, sparks flying, historic women industrial workers, cinematic realism" + style_suffix,
            search_keywords="World War II home front factory workers 1943",
        ),
        Scene(
            scene_id=12,
            narration_text="El conflicto reveló también la mayor atrocidad del siglo: el Holocausto sistemático que arrebató la vida a más de seis millones de judíos y millones de inocentes, dejando una herida imborrable en la conciencia moral.",
            visual_prompt="Somber and deeply respectful documentary view of a stone historical memorial monument, soft overcast daylight, quiet autumn leaves, reflective solemn atmosphere, black and white fine art photography" + style_suffix,
            search_keywords="Holocaust memorial solemn historical monument",
        ),
        Scene(
            scene_id=13,
            narration_text="El 6 de junio de 1944, el Día D, se ejecutó la mayor operación anfibia jamás concebida. Más de ciento cincuenta mil soldados aliados desembarcaron en las playas fortificadas de Normandía bajo intenso fuego.",
            visual_prompt="Epic cinematic historical recreation of the Normandy coast on June 6 1944, landing craft approaching sandy shores under dramatic morning mist, coastal bluffs, authentic historical documentary masterpiece" + style_suffix,
            search_keywords="Normandy landings D-Day June 1944 Omaha beach",
        ),
        Scene(
            scene_id=14,
            narration_text="Con los Aliados avanzando desde el oeste y las fuerzas soviéticas desde el este, la Batalla de Berlín en la primavera de 1945 selló el colapso absoluto del régimen nazi en el continente europeo.",
            visual_prompt="Historic view of the Brandenburg Gate in Berlin 1945 surrounded by wartime debris, majestic historical architecture standing resilient under dramatic post-battle twilight sky" + style_suffix,
            search_keywords="Brandenburg Gate Berlin 1945 historical",
        ),
        Scene(
            scene_id=15,
            narration_text="El 8 de mayo de 1945 se proclamó el Día de la Victoria en Europa. Ciudades enteras como Londres, París y Nueva York celebraron el fin de casi seis años de ocupación y combate incesante.",
            visual_prompt="Vintage documentary photograph of historic Paris and London streets with joyful civilian crowds celebrating peace in May 1945, fluttering flags, vintage confetti, genuine emotional capture" + style_suffix,
            search_keywords="VE Day celebrations Paris London May 1945",
        ),
        Scene(
            scene_id=16,
            narration_text="En agosto de 1945, el uso de las primeras bombas atómicas sobre Hiroshima y Nagasaki precipitó la rendición incondicional de Japón, marcando el nacimiento de la era atómica mundial.",
            visual_prompt="Historical documentary photograph of the Hiroshima Peace Memorial Genbaku Dome standing preserved under a clear blue sky, solemn historic preservation, peaceful commemorative atmosphere" + style_suffix,
            search_keywords="Hiroshima Peace Memorial Genbaku Dome historical",
        ),
        Scene(
            scene_id=17,
            narration_text="Los Juicios de Núremberg establecieron por primera vez la justicia penal internacional por crímenes contra la humanidad, mientras la fundación de las Naciones Unidas buscó evitar una nueva catástrofe global.",
            visual_prompt="Historic courtroom of the Nuremberg Trials 1945, judges bench and international flags, dramatic wood paneling, documentary judicial photography, solemn historical record" + style_suffix,
            search_keywords="Nuremberg trials courtroom 1945 1946",
        ),
        Scene(
            scene_id=18,
            narration_text="Con un saldo de más de setenta millones de vidas perdidas, la Segunda Guerra Mundial nos recuerda la fragilidad de la civilización y el valor incalculable de la paz. Suscríbete para preservar la memoria histórica.",
            visual_prompt="Panoramic view of an eternal flame peace memorial at dusk, warm flame glowing gently against a tranquil violet twilight sky, reflecting pool, timeless cinematic documentary photography" + style_suffix,
            search_keywords="World peace memorial eternal flame dusk",
        ),
    ]

    full_narration = " ".join([s.narration_text for s in scenes])
    metadata = VideoMetadata(
        title="Segunda Guerra Mundial: El Conflicto Que Transformó Para Siempre la Historia",
        description=(
            "Un documental completo y cronológico sobre la Segunda Guerra Mundial (1939-1945). "
            "Desde las causas y la Blitzkrieg hasta la Batalla de Stalingrado, el Desembarco de Normandía "
            "y las lecciones para la paz mundial.\n\n"
            "Capítulos:\n"
            "00:00 El estallido del conflicto (1939)\n"
            "00:25 La Blitzkrieg y la caída de Francia\n"
            "00:50 La Batalla de Inglaterra\n"
            "01:15 Operación Barbarroja y el Frente Oriental\n"
            "01:40 El ataque a Pearl Harbor\n"
            "02:05 La Batalla de Stalingrado: Punto de inflexión\n"
            "02:30 El Día D: Desembarco en Normandía\n"
            "02:55 El avance final sobre Berlín\n"
            "03:20 Hiroshima, Nagasaki y el fin de la guerra\n"
            "03:45 El legado y las lecciones para la humanidad\n\n"
            "🔔 Suscríbete para más documentales históricos y educativos de élite.\n"
            "#SegundaGuerraMundial #HistoriaMilitar #Documental #DíaD #Stalingrado #SigloXX #Educación"
        ),
        tags=[
            "Segunda Guerra Mundial",
            "Historia Universal",
            "Documental Histórico",
            "Día D",
            "Stalingrado",
            "Pearl Harbor",
            "Blitzkrieg",
            "Normandía",
            "Siglo XX",
            "Educación",
            "Batallas Históricas",
            "Churchill",
            "Hiroshima",
            "Aliados",
        ],
    )
    return ScriptOutput(metadata=metadata, narration_full=full_narration, scenes=scenes)


def _generate_quantum_fallback_script(aspect_ratio: str = "16:9") -> ScriptOutput:
    """
    Genera el documental científico de 18 escenas sobre física cuántica, multiverso e inmortalidad cuántica.
    """
    logger.warning("Generando guion documental de cosmología: 'Muerte Cuántica y el Multiverso' ({})", aspect_ratio)
    if aspect_ratio == "9:16":
        style_suffix = ", vertical 9:16 portrait orientation, mobile format, centered composition, cinematic 8k, photorealistic, volumetric lighting, unreal engine 5 render, award winning sci-fi concept art, no text, no watermark"
    else:
        style_suffix = ", cinematic 8k, photorealistic, volumetric lighting, unreal engine 5 render, award winning sci-fi concept art, no text, no watermark"

    scenes = [
        Scene(
            scene_id=1,
            narration_text="¿Qué ocurre en el instante exacto en que dejamos de existir? La física moderna plantea una respuesta que desafía nuestra comprensión de la realidad: la existencia de infinitos universos paralelos.",
            visual_prompt="Cinematic documentary photography, 16:9 widescreen, an eye reflecting cosmic nebulae and infinite branching corridors of light, mysterious deep blue and amber illumination, hyper-detailed" + style_suffix,
            search_keywords="Deep space cosmic nebula multiverse",
        ),
        Scene(
            scene_id=2,
            narration_text="Durante milenios, la muerte fue considerada un punto final absoluto. Sin embargo, en la frontera de la mecánica cuántica, ese punto final podría ser solo una bifurcación.",
            visual_prompt="Ancient stone astronomical observatory under a starry night sky, illuminated by soft moonlight, warm torchlight on stone arches, documentary style" + style_suffix,
            search_keywords="Astronomical observatory starry night sky",
        ),
        Scene(
            scene_id=3,
            narration_text="En 1957, el físico estadounidense Hugh Everett Tercero formuló una de las hipótesis más audaces de la ciencia: la interpretación de los muchos mundos.",
            visual_prompt="Vintage 1950s physics laboratory, chalkboards filled with complex quantum wave equations, glowing vacuum tubes and antique oscilloscopes, dramatic warm sidelighting" + style_suffix,
            search_keywords="Vintage physics laboratory blackboard equations",
        ),
        Scene(
            scene_id=4,
            narration_text="Everett propuso que la función de onda nunca colapsa. Cada vez que ocurre un evento con múltiples probabilidades, el universo se divide en ramas paralelas simultáneas.",
            visual_prompt="Stunning visual representation of reality splitting into infinite translucent holographic layers, geometric fractal universe, glowing cyan and gold light rays" + style_suffix,
            search_keywords="Fractal geometry quantum physics visualization",
        ),
        Scene(
            scene_id=5,
            narration_text="Décadas después, los teóricos llevaron esta idea a su consecuencia más extrema a través de un experimento mental revolucionario: el suicidio cuántico.",
            visual_prompt="Futuristic quantum experimental apparatus inside a dark minimalist scientific chamber, laser beams crossing optical mirrors, high tech atmosphere" + style_suffix,
            search_keywords="Quantum optics laser experiment laboratory",
        ),
        Scene(
            scene_id=6,
            narration_text="Imagina un dispositivo letal activado por la desintegración de una partícula cuántica. En un universo, el arma se dispara; en otro universo idéntico, falla por completo.",
            visual_prompt="Intricate metallic quantum mechanism with glowing atomic sensors, macro close-up view, intense cinematic shadows and razor-sharp metallic reflections" + style_suffix,
            search_keywords="Precision atomic sensor scientific apparatus",
        ),
        Scene(
            scene_id=7,
            narration_text="Desde la perspectiva de los observadores externos, el sujeto puede perecer. Pero desde la perspectiva consciente del propio individuo, solo puede experimentar las ramas donde sobrevive.",
            visual_prompt="Silhouetted human figure standing before a massive glowing portal showing countless diverging destinies, epic atmospheric perspective, volumetric fog" + style_suffix,
            search_keywords="Cosmic perspective human silhouette stars",
        ),
        Scene(
            scene_id=8,
            narration_text="Este fenómeno es conocido como la hipótesis de la inmortalidad cuántica: la consciencia solo es capaz de percibir los hilos del multiverso donde continúa existiendo.",
            visual_prompt="Abstract ethereal representation of human consciousness as an interconnected network of golden neural fibers flowing across celestial space" + style_suffix,
            search_keywords="Neural network consciousness galaxy visualization",
        ),
        Scene(
            scene_id=9,
            narration_text="Cada microsegundo, millones de procesos cuánticos en nuestro cuerpo toman caminos divergentes, creando infinitas copias de nuestra propia historia.",
            visual_prompt="Biological cells and DNA double helix radiating quantum energy particles, microscopic scientific visualization, deep ultraviolet and emerald colors" + style_suffix,
            search_keywords="DNA double helix glowing microscopic",
        ),
        Scene(
            scene_id=10,
            narration_text="Científicos de renombre como Max Tegmark han debatido intensamente si esta lógica matemática se sostiene ante las leyes de la termodinámica y la biología celular.",
            visual_prompt="Prestigious auditorium of theoretical physicists watching a glowing mathematical holographic sphere on stage, soft ambient illumination" + style_suffix,
            search_keywords="Theoretical physics conference auditorium",
        ),
        Scene(
            scene_id=11,
            narration_text="El gran obstáculo radica en el envejecimiento: un cuerpo biológico no se extingue por un solo evento cuántico, sino por un colapso gradual de sus sistemas vitales.",
            visual_prompt="Artistic hourglass with glowing sand particles transitioning into stardust, dramatic chiaroscuro lighting, timeless philosophical aesthetic" + style_suffix,
            search_keywords="Hourglass sand stardust cosmos",
        ),
        Scene(
            scene_id=12,
            narration_text="Aun así, físicos cuánticos sugieren que en algún rincón inexplorado del multiverso infinito, siempre existe una rama donde las probabilidades imposibles se vuelven realidad.",
            visual_prompt="Panoramic cosmic landscape displaying dozens of distinct Earth-like planets aligned across an infinite nebula, majestic scale, awe-inspiring cinematography" + style_suffix,
            search_keywords="Exoplanets deep space nebula cosmic",
        ),
        Scene(
            scene_id=13,
            narration_text="Físicos como Roger Penrose sugieren además que la consciencia podría no ser un simple cómputo cerebral, sino una propiedad fundamental del tejido del espacio-tiempo.",
            visual_prompt="Intricate structural grid of space-time fabric curving around glowing gravitational masses, Einsteinian curvature, elegant cosmological rendering" + style_suffix,
            search_keywords="Spacetime curvature gravitational fabric",
        ),
        Scene(
            scene_id=14,
            narration_text="Si el tiempo no es una línea que fluye sino un bloque tetradimensional donde todo momento ya existe, pasado, presente y futuro conviven eternamente.",
            visual_prompt="Futuristic dimensional clock tower where time gears interlock with spinning galaxies, golden warm hour reflections, surreal architecture" + style_suffix,
            search_keywords="Astronomical clock galaxy celestial time",
        ),
        Scene(
            scene_id=15,
            narration_text="La muerte, por lo tanto, dejaría de ser la aniquilación de una vida, transformándose en la frontera geométrica de una trayectoria en el cosmos.",
            visual_prompt="Atmospheric misty shoreline where the calm ocean meets a horizon of twilight aurora borealis, reflective water surface, peaceful contemplative mood" + style_suffix,
            search_keywords="Aurora borealis twilight calm ocean",
        ),
        Scene(
            scene_id=16,
            narration_text="Aunque estas ideas desafían el sentido común, nos obligan a replantearnos el mayor misterio de todos: qué significa realmente estar vivos y ser conscientes.",
            visual_prompt="A solitary telescope in a high mountain observatory under the Milky Way arch, starlight reflecting on the curved dome glass, documentary realism" + style_suffix,
            search_keywords="Milky Way mountain observatory telescope",
        ),
        Scene(
            scene_id=17,
            narration_text="Quizás en este preciso instante, en otra rama del multiverso, otra versión de ti está reflexionando exactamente sobre estas mismas preguntas.",
            visual_prompt="Two ethereal mirror reflections of the same individual looking at each other across a glowing dimensional glass surface, deep emotional resonance" + style_suffix,
            search_keywords="Ethereal reflection deep cosmic perspective",
        ),
        Scene(
            scene_id=18,
            narration_text="En este universo, tu viaje continúa. Suscríbete para seguir explorando los límites más profundos de la ciencia, el cosmos y la consciencia humana.",
            visual_prompt="Breathtaking deep space shot of our luminous Earth rising over the moon's curved horizon with a brilliant sunrise, cinematic documentary masterpiece" + style_suffix,
            search_keywords="Earth rise over moon horizon sunrise space",
        ),
    ]

    full_narration = " ".join([s.narration_text for s in scenes])
    metadata = VideoMetadata(
        title="¿Qué Pasa Cuando Morimos? La Teoría del Multiverso y la Inmortalidad Cuántica",
        description=(
            "¿Es la muerte un final absoluto o simplemente una bifurcación en el multiverso? "
            "En este documental exploramos la teoría de los muchos mundos de Hugh Everett, "
            "el experimento del suicidio cuántico y las implicaciones más profundas de la física teórica sobre la consciencia.\n\n"
            "Capítulos:\n"
            "00:00 El enigma del final\n"
            "00:30 La interpretación de los muchos mundos\n"
            "01:15 El experimento del suicidio cuántico\n"
            "02:00 Inmortalidad cuántica y consciencia\n"
            "02:45 El tejido del espacio-tiempo y conclusiones\n\n"
            "🔔 Suscríbete para más viajes a la frontera de la ciencia y el universo.\n"
            "#FísicaCuántica #Multiverso #Documental #Ciencia #MisteriosDelUniverso"
        ),
        tags=[
            "Multiverso",
            "Física Cuántica",
            "Muerte y Multiverso",
            "Inmortalidad Cuántica",
            "Hugh Everett",
            "Mecánica Cuántica",
            "Documental",
            "Ciencia",
            "Cosmología",
            "Consciencia Humana",
            "Espacio Tiempo",
            "Universos Paralelos",
            "Educación",
        ],
    )
    return ScriptOutput(metadata=metadata, narration_full=full_narration, scenes=scenes)


def _generate_dynamic_topic_fallback(topic: str, duration_minutes: float, target_words: int, num_scenes: int, aspect_ratio: str = "16:9") -> ScriptOutput:
    """
    Genera un documental dinámico de 18 escenas cortas (>500 palabras, >3 minutos)
    adaptado contextualmente a cualquier temática educativa, histórica, científica o cultural,
    sin mezclas ni contaminaciones de otros temas.
    """
    clean_topic = topic.strip()
    logger.warning("Generando guion documental dinámico adaptado específicamente para: '{}' (18 escenas, {})", clean_topic, aspect_ratio)
    if aspect_ratio == "9:16":
        style_suffix = ", vertical 9:16 portrait orientation, mobile format, centered composition, cinematic 8k, photorealistic, volumetric lighting, unreal engine 5 render, award winning documentary concept art, no text, no watermark"
    else:
        style_suffix = ", cinematic 8k, photorealistic, volumetric lighting, unreal engine 5 render, award winning documentary concept art, no text, no watermark"

    arc_blueprints = [
        ("A lo largo de las épocas, pocas materias han transformado tanto nuestra comprensión del mundo como {topic}. Explorar su verdadero alcance revela fascinantes interrogantes.", "Cinematic documentary photography, wide panoramic atmospheric view representing {topic}, dramatic lighting and thoughtful composition"),
        ("Para comprender la esencia de {topic}, es indispensable viajar hacia sus raíces originales, donde los primeros indicios comenzaron a cambiar la historia.", "Historical documentary setting with vintage archives, warm amber sidelighting and authentic period details regarding {topic}"),
        ("El punto de partida no fue fortuito: surgió como una respuesta necesaria ante desafíos fundamentales que la sociedad de su época no podía ignorar.", "Authentic archival scene with intellectuals and pioneers examining blueprints and manuscripts related to {topic}"),
        ("Grandes mentes e investigadores pioneros dedicaron sus vidas a dar forma a las bases que hoy sustentan nuestra comprensión de {topic}.", "Dramatic portrait of visionary pioneers working in a classic historical workshop or laboratory studying {topic}"),
        ("Sin embargo, los comienzos estuvieron marcados por la resistencia. Las ideas tradicionales chocaron frontalmente con los revolucionarios conceptos de {topic}.", "Intense debate in a grand historic hall, dramatic chiaroscuro lighting, emotional tension surrounding the breakthrough of {topic}"),
        ("En su núcleo operativo, {topic} se sostiene sobre mecanismos y principios rigurosos que operan con una precisión verdaderamente admirable.", "Detailed visualization of the intricate internal mechanisms and structural concepts driving {topic}, macro cinematography"),
        ("Con el correr de las décadas, la influencia de {topic} comenzó a expandirse rápidamente, superando fronteras geográficas e impactando a diversas culturas.", "Epic visual map and connecting network lines glowing over continents, illustrating the global spread of {topic}"),
        ("Todo avance determinante atraviesa una crisis. En un momento decisivo, {topic} se vio sometido a pruebas extremas que amenazaron su continuidad.", "Dramatic stormy atmospheric landscape symbolizing crisis and high stakes confrontation in the history of {topic}"),
        ("Lejos de claudicar, esa etapa crítica desató una ola de genialidad que permitió perfeccionar y afianzar para siempre el desarrollo de {topic}.", "Brilliant sunbeam breaking through dark clouds illuminating majestic modern architectural achievement related to {topic}"),
        ("El impacto pronto se tornó internacional. Naciones e instituciones unieron esfuerzos para integrar las aportaciones de {topic} a escala masiva.", "Panoramic international assembly or landmark institution collaborating on the advancement of {topic}"),
        ("En la vida cotidiana, las consecuencias prácticas de {topic} se hicieron palpables, transformando la rutina y las oportunidades de millones de personas.", "Candid documentary photograph of ordinary people whose daily lives were transformed by {topic}, authentic emotional depth"),
        ("Pero cada gran transformación plantea dilemas éticos y desafíos morales que los especialistas debieron aprender a sopesar con cautela.", "Reflective philosophical scene, balanced scales of justice in a neoclassical chamber, thoughtful mood regarding {topic}"),
        ("Al ingresar en la modernidad, la llegada de nuevas tecnologías potenció exponencialmente el rendimiento y las aplicaciones de {topic}.", "High-tech research center with cutting-edge displays and advanced analysis equipment dedicated to {topic}"),
        ("Descubrimientos contemporáneos continúan aportando datos reveladores, obligando a replantear teorías que se creían totalmente consolidadas sobre {topic}.", "Modern scientific laboratory with researchers observing groundbreaking data about {topic}, sleek futuristic realism"),
        ("Hoy en día, {topic} ocupa un lugar privilegiado en la vanguardia del conocimiento, siendo referencia obligada en la educación global.", "Inspiring academic lecture theater filled with engaged students watching an illuminated presentation on {topic}"),
        ("A pesar de los extraordinarios progresos, aún persisten enigmas sin resolver que desafían a las mentes más brillantes de nuestra generación.", "Mysterious dramatic vista with open horizon and uncharted territory, symbolizing the unsolved frontiers of {topic}"),
        ("Analizar en profundidad {topic} es, en última instancia, una oportunidad para reflexionar sobre nuestro propio potencial y rumbo colectivo.", "Contemplative human silhouette looking out over an expansive sunrise horizon, peaceful and deeply inspiring atmosphere"),
        ("El fascinante recorrido de {topic} nos demuestra que el conocimiento nunca se detiene. Suscríbete para continuar explorando los mayores hitos de nuestra historia.", "Panoramic cinematic view of an iconic landmark or monument celebrating human knowledge and {topic}, majestic golden hour illumination"),
    ]

    selected_blueprints = arc_blueprints[:num_scenes] if num_scenes and num_scenes < len(arc_blueprints) else arc_blueprints
    scenes = []
    for idx, (narr_template, prompt_template) in enumerate(selected_blueprints, start=1):
        narr_text = narr_template.replace("{topic}", clean_topic)
        vis_prompt = prompt_template.replace("{topic}", clean_topic) + style_suffix
        kw = f"{clean_topic} history documentary"
        scenes.append(
            Scene(
                scene_id=idx,
                narration_text=narr_text,
                visual_prompt=vis_prompt,
                search_keywords=kw,
            )
        )

    full_narration = " ".join([s.narration_text for s in scenes])
    metadata = VideoMetadata(
        title=f"{clean_topic.title()}: La Historia Completa y sus Grandes Revelaciones" + (" #Shorts" if aspect_ratio == "9:16" else ""),
        description=(
            f"Un documental exhaustivo y cautivador sobre {clean_topic}. "
            "Exploramos sus orígenes históricos, hitos decisivos, transformaciones clave "
            "y el impacto trascendental que tiene en nuestro mundo actual.\n\n"
            "Capítulos:\n"
            "00:00 Introducción y enigma inicial\n"
            "00:40 Orígenes y primeros antecedentes\n"
            "01:20 Los pioneros y el punto de quiebre\n"
            "02:00 Transformación y expansión global\n"
            "02:40 El impacto en el presente y futuro\n\n"
            f"🔔 Suscríbete para más documentales sobre historia, ciencia y conocimiento.\n"
            f"#{clean_topic.title().replace(' ', '')} #Documental #Historia #Educación #Conocimiento"
        ),
        tags=[
            clean_topic.title(),
            "Documental",
            "Historia",
            "Ciencia",
            "Educación",
            "Grandes Descubrimientos",
            "Conocimiento",
            "Cultura General",
            "Investigación",
        ],
    )
    return ScriptOutput(metadata=metadata, narration_full=full_narration, scenes=scenes)


def _is_dimension_or_senses_topic(topic: str) -> bool:
    t = topic.lower()
    dimension_keywords = ["dimension", "dimensión", "4ta", "cuarta", "4 dimension", "teseracto", "tesseract", "hipercubo", "sentido", "sentidos", "propiocep", "cronocep"]
    return any(k in t for k in dimension_keywords)


def _generate_dimension_and_senses_fallback_script(aspect_ratio: str = "9:16") -> ScriptOutput:
    logger.info("Cargando guion documental maestro especializado: 'La Cuarta Dimensión y los Sentidos Ocultos' ({})", aspect_ratio)
    if aspect_ratio == "9:16":
        style_suffix = ", vertical 9:16 portrait orientation, mobile format, cinematic 8k, photorealistic, volumetric lighting, unreal engine 5 render, award winning sci-fi concept art, no text, no watermark"
    else:
        style_suffix = ", cinematic 8k, photorealistic, volumetric lighting, unreal engine 5 render, award winning sci-fi concept art, no text, no watermark"

    scenes_data = [
        (
            1,
            "Desde niños nos enseñaron que el mundo tiene tres dimensiones y que solo poseemos cinco sentidos. Ambas afirmaciones son completamente falsas.",
            "Surreal glowing human silhouette standing before an unfolding geometric 4D tesseract in deep cosmic hyperspace, volumetric neon lighting",
            "fourth dimension tesseract hyperspace human silhouette"
        ),
        (
            2,
            "La neurociencia moderna confirma que poseemos al menos nueve sentidos. Uno de los más fascinantes es la propiocepción: la capacidad de saber exactamente dónde está cada parte de tu cuerpo incluso con los ojos cerrados.",
            "Artistic medical visualization of human neural pathways glowing through muscles and joints, proprioception sensory grid in blue and gold light, photorealistic",
            "proprioception sensory neuroscience human body glowing nerves"
        ),
        (
            3,
            "Otro sentido vital es la equilibriocepción, gobernada por los canales del oído interno, detectando la aceleración y la gravedad para mantenernos en pie en un planeta en constante movimiento.",
            "Intricate close-up of human inner ear vestibular system transformed into luminous cosmic gyroscopes and fluid dynamics, photorealistic",
            "vestibular system balance sense inner ear gyroscope"
        ),
        (
            4,
            "A ellos se suman la termocepción, que mide el flujo de temperatura, y la interocepción, el radar biológico interno que lee los latidos del corazón y las señales de los órganos vitales.",
            "Ethereal translucent human torso with pulsing anatomical heart and thermal energy radiance, warm red and cool cyan tones, cinematic lighting",
            "interoception human heart thermal imaging anatomical glowing"
        ),
        (
            5,
            "Nuestros sentidos evolucionaron para sobrevivir en un espacio tridimensional: longitud, anchura y altura. Pero, ¿qué ocurre si el universo contiene dimensiones superiores?",
            "Cosmic spatial grid bending and twisting into higher geometric folds, celestial event horizon, dramatic volumetric shadows, photorealistic",
            "spatial dimensions grid bending higher geometry universe"
        ),
        (
            6,
            "Imagina una criatura bidimensional viviendo en una hoja de papel plano. Si una esfera tridimensional atraviesa su plano, el ser plano solo vería un círculo que crece y se encoge de la nada.",
            "Conceptual visualization of a luminous 3D glass sphere passing through a dark glowing 2D geometric plane, neon slice rings expanding, surreal conceptual art",
            "flatland concept 3D sphere passing through 2D plane geometry"
        ),
        (
            7,
            "De la misma manera, los seres humanos no podemos ver la cuarta dimensión espacial directamente; únicamente podemos observar sus sombras tridimensionales proyectadas en nuestro espacio.",
            "A complex four-dimensional hypercube tesseract casting a shifting three-dimensional geometric shadow onto a reflective dark surface, dramatic studio lighting",
            "tesseract 4D shadow projected in 3D space reflective floor"
        ),
        (
            8,
            "Esta figura geométrica es el teseracto o hipercubo: un cubo cuyos vértices se extienden en un ángulo perpendicular de noventa grados que nuestro cerebro no puede concebir.",
            "Hypnotic 3D rendering of a translucent glass and neon tesseract rotating infinitely into itself, sacred geometry, cybernetic hyperdimensional aura",
            "hypercube tesseract rotating geometry glass neon glowing"
        ),
        (
            9,
            "En la teoría de la relatividad de Einstein, el tiempo actúa como una cuarta dimensión inseparable del espacio, formando el tejido elástico del espacio-tiempo donde pasado, presente y futuro coexisten.",
            "Fabric of spacetime warped like a liquid glass vortex, clocks melting and bending along cosmic gravitational waves, interstellar aesthetics",
            "spacetime fabric relativity warping time dimension gravity"
        ),
        (
            10,
            "Para navegar esta coordenada temporal, poseemos la cronocepción: la red neuronal de relojes biológicos en el cerebro que nos permite experimentar el paso del tiempo.",
            "Futuristic brain neural synapses glowing like constellations intertwined with ancient golden clockwork mechanisms, atmospheric particle dust",
            "chronoception brain neural clocks time perception glowing"
        ),
        (
            11,
            "La física teórica sugiere que el cosmos podría tener hasta once dimensiones, enrolladas a una escala cuántica invisible a nuestros ojos biológicos.",
            "Intricate Calabi-Yau manifold floating in deep space, hyper-detailed quantum multidimensional geometry, iridescent colors",
            "string theory calabi yau manifold quantum dimensions cosmos"
        ),
        (
            12,
            "Nuestros sentidos no fueron diseñados para mostrarnos la totalidad de la realidad, sino únicamente la pequeña porción necesaria para garantizar la supervivencia de nuestra especie.",
            "Human eye iris expanding into an infinite fractal kaleidoscope of hidden dimensions and galaxies, macro cinematography",
            "human eye iris macro universe hidden dimensions fractal"
        ),
        (
            13,
            "La física moderna y la neurociencia revelan una misma verdad: el cosmos es infinitamente más vasto que las tres dimensiones y los cinco sentidos que creemos dominar.",
            "Awe-inspiring view of an astronomer standing on a cliff gazing at cosmic multidimensional aurora borealis across the night sky, epic scale, photorealistic",
            "astronomer cliff night sky cosmos multidimensional aurora"
        ),
        (
            14,
            "¿Qué sentido oculto te gustaría desbloquear para percibir la cuarta dimensión? Déjalo en los comentarios y suscríbete para expandir tu mente todos los días.",
            "Majestic floating golden portal transitioning between human anatomy and higher-dimensional geometry, warm radiant light, cinematic masterpiece",
            "cosmic golden portal higher dimension human mind transcendence"
        )
    ]

    scenes = [
        Scene(
            scene_id=sid,
            narration_text=text,
            visual_prompt=prompt + style_suffix,
            search_keywords=kw,
        )
        for sid, text, prompt, kw in scenes_data
    ]

    full_narration = " ".join([s.narration_text for s in scenes])
    metadata = VideoMetadata(
        title="La Cuarta Dimensión y los Sentidos Ocultos de tu Cerebro #Shorts",
        description=(
            "¿Solo tenemos 5 sentidos y vivimos en 3 dimensiones? La ciencia demuestra que ambas ideas son falsas. "
            "Descubre los sentidos ocultos del cuerpo humano (propiocepción, equilibriocepción, cronocepción) "
            "y cómo la física explica la fascinante cuarta dimensión y el teseracto.\n\n"
            "🔔 Suscríbete para explorar los mayores enigmas de la ciencia y la mente humana.\n"
            "#CuartaDimension #SentidosOcultos #Teseracto #Neurociencia #Fisica #Shorts #Documental"
        ),
        tags=[
            "Cuarta Dimension",
            "Teseracto",
            "Sentidos Ocultos",
            "Propiocepcion",
            "Neurociencia",
            "Fisica Cuantica",
            "Espacio Tiempo",
            "Ciencia",
            "Documental",
            "Educacion",
            "Curiosidades",
            "Shorts",
        ],
    )
    return ScriptOutput(metadata=metadata, narration_full=full_narration, scenes=scenes)


def _generate_fallback_script(topic: str, duration_minutes: float, target_words: int, num_scenes: int, aspect_ratio: str = "16:9") -> ScriptOutput:
    """
    Genera un guion documental profundo y completo de escenas cortas
    seleccionando inteligentemente el contenido según la temática solicitada para evitar cualquier mezcla.
    """
    if _is_wwii_or_war_topic(topic):
        return _generate_wwii_fallback_script(aspect_ratio=aspect_ratio)
    elif _is_quantum_or_multiverse_topic(topic):
        return _generate_quantum_fallback_script(aspect_ratio=aspect_ratio)
    elif _is_dimension_or_senses_topic(topic):
        return _generate_dimension_and_senses_fallback_script(aspect_ratio=aspect_ratio)
    else:
        return _generate_dynamic_topic_fallback(topic, duration_minutes, target_words, num_scenes, aspect_ratio=aspect_ratio)


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
    """
    # Ritmo estándar de 140 palabras por minuto
    calculated_words = target_words or int(duration_minutes * 140)
    # Entre 3 y 25 escenas adaptadas al metraje real (promedio de 7 a 11 segundos por escena)
    calculated_scenes = max(3, min(25, int(duration_minutes * 5.5)))

    selected_provider = (provider or settings.LLM_PROVIDER).lower()

    # 1. Intentar proveedor seleccionado
    if selected_provider == "gemini" and settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "tu_clave_gemini_aqui":
        try:
            return _generate_with_gemini(topic, duration_minutes, calculated_words, calculated_scenes, aspect_ratio=aspect_ratio)
        except Exception as e:
            logger.error("Fallo con Gemini: {}. Buscando alternativas...", e)
    elif selected_provider == "deepseek" and settings.DEEPSEEK_API_KEY and settings.DEEPSEEK_API_KEY != "tu_clave_deepseek_aqui":
        try:
            return _generate_with_deepseek(topic, duration_minutes, calculated_words, calculated_scenes, aspect_ratio=aspect_ratio)
        except Exception as e:
            logger.error("Fallo con DeepSeek: {}. Buscando alternativas...", e)

    # 2. Intentar proveedor alternativo si el principal no funcionó
    if selected_provider != "gemini" and settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "tu_clave_gemini_aqui":
        try:
            return _generate_with_gemini(topic, duration_minutes, calculated_words, calculated_scenes, aspect_ratio=aspect_ratio)
        except Exception as e:
            logger.error("Fallo alternativo con Gemini: {}", e)

    if selected_provider != "deepseek" and settings.DEEPSEEK_API_KEY and settings.DEEPSEEK_API_KEY != "tu_clave_deepseek_aqui":
        try:
            return _generate_with_deepseek(topic, duration_minutes, calculated_words, calculated_scenes, aspect_ratio=aspect_ratio)
        except Exception as e:
            logger.error("Fallo alternativo con DeepSeek: {}", e)

    # 3. Fallback estructurado de alta densidad
    return _generate_fallback_script(topic, duration_minutes, calculated_words, calculated_scenes, aspect_ratio=aspect_ratio)



def save_script_to_disk(script_output: ScriptOutput, target_path = None) -> None:
    """Persiste el guion estructurado en formato JSON en disco."""
    path = target_path or settings.SCRIPT_JSON_PATH
    with open(path, "w", encoding="utf-8") as f:
        f.write(script_output.model_dump_json(indent=2))
    logger.success("Guion estructurado guardado exitosamente en: {}", path)
