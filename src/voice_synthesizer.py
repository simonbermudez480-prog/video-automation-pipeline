"""
Módulo de Síntesis de Voz (TTS).
Soporta:
1. ElevenLabs API (voces ultra-realistas con eleven_multilingual_v2).
2. Fallback automático a Microsoft Edge-TTS (100% gratuito, sin API key, calidad neural en español).
"""
import asyncio
import re
from pathlib import Path
from typing import Optional, Dict
import requests

from src.config import settings
from src.logger import logger

# Diccionario fonético especializado para narración documental en español
# Permite que las voces neurales pronuncien términos anglosajones, alemanes y científicos de forma natural
PHONETIC_DICTIONARY: Dict[str, str] = {
    # Segunda Guerra Mundial / Militar
    r"\bPearl\s+Harbor\b": "Pörl Járbor",
    r"\bBlitzkrieg\b": "Blitskrig",
    r"\bLuftwaffe\b": "Luftvafe",
    r"\bWehrmacht\b": "Vermajt",
    r"\bWinston\s+Churchill\b": "Uinston Chérchil",
    r"\bChurchill\b": "Chérchil",
    r"\bFranklin\s+(?:D\.\s+)?Roosevelt\b": "Franklin Rúsevelt",
    r"\bRoosevelt\b": "Rósevelt",
    r"\bOppenheimer\b": "Openjáimer",
    r"\bJ\.\s*Robert\s+Oppenheimer\b": "Robert Openjáimer",
    r"\bManhattan\s+Project\b": "Manjatan Proyekt",
    r"\bProyecto\s+Manhattan\b": "Proyecto Manjatan",
    r"\bAuschwitz\b": "Áushvits",
    r"\bD-Day\b": "Di-Dei",
    r"\bSpitfire\b": "Spitfáier",
    r"\bU-Boat\b": "U-Bot",
    r"\bReich\b": "Ráij",
    r"\bFührer\b": "Fíurer",
    r"\bStuka\b": "Stúka",
    r"\bPanzer\b": "Pánzer",
    # Ciencia / Multiverso / Cosmología
    r"\bBig\s+Bang\b": "Big Beng",
    r"\bQuantum\b": "Kuantum",
    r"\bSchrödinger\b": "Shrodinger",
    r"\bStephen\s+Hawking\b": "Stiven Jóquin",
    r"\bHawking\b": "Jóquin",
    r"\bAlbert\s+Einstein\b": "Albert Áinstain",
    r"\bEinstein\b": "Áinstain",
    r"\bHeisenberg\b": "Jaisenberg",
    r"\bNiels\s+Bohr\b": "Nils Bor",
    r"\bRichard\s+Feynman\b": "Ríchard Fáinman",
    r"\bFeynman\b": "Fáinman",
    r"\bHubble\b": "Jábol",
    r"\bJames\s+Webb\b": "Yeims Ueb",
    r"\bSpaceX\b": "Speis Eks",
    # Tecnología y términos universales
    r"\bHigh-tech\b": "Jai-tek",
    r"\bShockwave\b": "Shokueiv",
    r"\bStreaming\b": "Striming",
    r"\bSoftware\b": "Softuer",
    r"\bHardware\b": "Jarduer",
}


def _apply_phonetic_normalization(text: str) -> str:
    """
    Aplica adaptaciones fonéticas sutiles exclusivamente al flujo enviado al TTS
    para evitar que los términos en inglés/alemán suenen forzados o deformados.
    El texto original del guion y los subtítulos se conservan 100% intactos.
    """
    modified_text = text
    applied = []
    for pattern, replacement in PHONETIC_DICTIONARY.items():
        if re.search(pattern, modified_text, flags=re.IGNORECASE):
            modified_text = re.sub(pattern, replacement, modified_text, flags=re.IGNORECASE)
            applied.append(replacement)
    if applied:
        logger.info("Adaptación fonética aplicada a {} términos para dicción natural: {}", len(applied), applied[:4])
    return modified_text


def _synthesize_elevenlabs(text: str, output_path: Path, voice_id: str, api_key: str) -> bool:
    """Genera locución utilizando la API de ElevenLabs."""
    logger.info("Iniciando síntesis de voz con ElevenLabs (Voice ID: {})...", voice_id)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }
    
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.50,
            "similarity_boost": 0.80,
            "style": 0.15,
            "use_speaker_boost": True,
        },
    }

    response = requests.post(url, json=data, headers=headers, timeout=60, stream=True)
    if response.status_code != 200:
        logger.error(
            "ElevenLabs API error [HTTP {}]: {}",
            response.status_code,
            response.text[:250],
        )
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=4096):
            if chunk:
                f.write(chunk)

    logger.success("Voz de ElevenLabs generada y guardada en: {}", output_path)
    return True


async def _synthesize_edge_tts_async(text: str, output_path: Path, voice: str) -> None:
    """Función asíncrona interna para sintetizar con Edge-TTS."""
    import edge_tts

    communicate = edge_tts.Communicate(text=text, voice=voice)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    await communicate.save(str(output_path))


def _synthesize_edge_tts(text: str, output_path: Path, voice: str) -> bool:
    """Genera locución utilizando Microsoft Edge-TTS (Red neural de alta calidad)."""
    logger.info("Iniciando síntesis de voz con Edge-TTS (Voz: {})...", voice)
    try:
        asyncio.run(_synthesize_edge_tts_async(text, output_path, voice))
        logger.success("Voz de Edge-TTS generada exitosamente en: {}", output_path)
        return True
    except Exception as e:
        logger.error("Error al sintetizar con Edge-TTS: {}", e)
        return False


def synthesize_voice(
    text: str,
    output_path: Optional[Path] = None,
    provider: Optional[str] = None,
) -> Path:
    """
    Punto de entrada principal para síntesis de voz.
    Si ElevenLabs está configurado, lo intenta. Si falla o no tiene clave,
    recurre a Microsoft Edge-TTS de manera 100% transparente.
    """
    dest = output_path or settings.NARRATION_AUDIO_PATH
    selected_provider = (provider or settings.TTS_PROVIDER).lower()

    # Sanitizar texto para mejorar pausas y entonación
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("El texto de narración está vacío.")

    # Normalización fonética para términos extranjeros/complejos si está habilitada
    spoken_text = clean_text
    if getattr(settings, "ENABLE_PHONETIC_CORRECTION", True):
        spoken_text = _apply_phonetic_normalization(clean_text)

    # 1. Intentar ElevenLabs si fue elegido o si la API key existe
    if selected_provider == "elevenlabs" or (
        settings.ELEVENLABS_API_KEY
        and settings.ELEVENLABS_API_KEY != "tu_clave_elevenlabs_aqui"
    ):
        if settings.ELEVENLABS_API_KEY and settings.ELEVENLABS_API_KEY != "tu_clave_elevenlabs_aqui":
            success = _synthesize_elevenlabs(
                spoken_text,
                dest,
                settings.ELEVENLABS_VOICE_ID,
                settings.ELEVENLABS_API_KEY,
            )
            if success and dest.exists() and dest.stat().st_size > 0:
                return dest
            logger.warning("ElevenLabs falló o no completó la descarga. Recurriendo a fallback Edge-TTS...")
        else:
            logger.warning("ELEVENLABS_API_KEY no está configurada. Usando Edge-TTS automático...")

    # 2. Fallback a Edge-TTS
    success = _synthesize_edge_tts(spoken_text, dest, settings.EDGE_TTS_VOICE)
    if not success or not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError("No se pudo sintetizar el audio con ningún proveedor.")

    return dest
