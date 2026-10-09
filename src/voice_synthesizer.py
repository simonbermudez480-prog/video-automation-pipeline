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


import shutil
import subprocess


def _master_audio(input_path: Path, output_path: Path) -> bool:
    """
    Cadena de masterización acústica profesional para TikTok, Shorts y Reels:
    1. High-Pass Filter (80Hz): Elimina retumbos y suciedad de frecuencias subgraves.
    2. Ecualización de Presencia (+2.5dB en 3.5kHz): Brillo y nitidez en altavoces de smartphone.
    3. Compresión Dinámica (3:1, -18dB): Empareja susurros y picos de voz para presencia densa.
    4. Normalización a -14 LUFS (Estándar de TikTok / YouTube Shorts).
    """
    if not getattr(settings, "ENABLE_AUDIO_MASTERING", True):
        if input_path != output_path:
            shutil.copy2(input_path, output_path)
        return True

    temp_mastered = output_path.parent / f"mastered_{output_path.name}"
    filter_chain = (
        "highpass=f=80,"
        "equalizer=f=3500:t=q:w=1:g=2.5,"
        "acompressor=threshold=-18dB:ratio=3:attack=15:release=100,"
        "loudnorm=I=-14:LRA=7:TP=-1.5"
    )

    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-af", filter_chain,
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(temp_mastered)
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and temp_mastered.exists() and temp_mastered.stat().st_size > 0:
            if output_path.exists():
                output_path.unlink()
            temp_mastered.rename(output_path)
            logger.info("Audio masterizado profesionalmente para TikTok/Shorts (-14 LUFS, Presencia 3.5kHz)")
            return True
        else:
            logger.warning("FFmpeg no pudo aplicar masterización (usando audio original): {}", res.stderr.decode(errors='ignore')[:150])
    except Exception as e:
        logger.warning("Error en masterización de audio: {}", e)

    if input_path != output_path:
        shutil.copy2(input_path, output_path)
    return True


def _synthesize_gemini_tts(text: str, output_path: Path, voice_name: str, model_name: str) -> bool:
    """Genera locución humana y expresiva utilizando Google Gemini TTS nativo."""
    logger.info("Iniciando síntesis de voz con Google Gemini TTS ({}, Voz: '{}')...", model_name, voice_name)
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=model_name,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        ),
    )

    audio_bytes = None
    if response.parts:
        for p in response.parts:
            if p.inline_data and p.inline_data.data:
                audio_bytes = p.inline_data.data
                break

    if not audio_bytes:
        logger.error("Gemini TTS ({}) no devolvió datos de audio en la respuesta.", model_name)
        return False

    temp_raw_wav = output_path.parent / f"gemini_raw_{output_path.stem}.wav"
    temp_raw_wav.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_raw_wav, "wb") as f:
        f.write(audio_bytes)

    # Masterizar y codificar a MP3
    _master_audio(temp_raw_wav, output_path)
    if temp_raw_wav.exists():
        temp_raw_wav.unlink(missing_ok=True)

    logger.success("Voz humana de Gemini TTS generada y masterizada con éxito en: {}", output_path)
    return True


def _synthesize_gemini_tts_cascade(text: str, output_path: Path, voice_name: str) -> bool:
    """
    Ejecuta cascada de modelos Gemini TTS (gemini-3.8-flash-tts, gemini-3.8-flash-lite-tts, etc.)
    para sortear rate limits temporales.
    """
    candidates = settings.get_gemini_tts_candidates()
    for idx, model in enumerate(candidates, 1):
        try:
            logger.info("Cascada Gemini TTS [{}/{}]: Probando modelo '{}'...", idx, len(candidates), model)
            if _synthesize_gemini_tts(text, output_path, voice_name, model):
                return True
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                logger.warning("Cuota / Rate Limit agotado para Gemini TTS '{}' (429). Probando siguiente...", model)
            elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                logger.warning("Alta demanda en Gemini TTS '{}' (503). Probando siguiente...", model)
            else:
                logger.warning("Fallo en Gemini TTS '{}': {}. Probando siguiente...", model, err_msg)

    return False


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
            "stability": 0.40,
            "similarity_boost": 0.85,
            "style": 0.35,
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

    temp_eleven = output_path.parent / f"eleven_raw_{output_path.name}"
    temp_eleven.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_eleven, "wb") as f:
        for chunk in response.iter_content(chunk_size=4096):
            if chunk:
                f.write(chunk)

    _master_audio(temp_eleven, output_path)
    if temp_eleven.exists():
        temp_eleven.unlink(missing_ok=True)

    logger.success("Voz de ElevenLabs generada y masterizada en: {}", output_path)
    return True


async def _synthesize_edge_tts_async(text: str, output_path: Path, voice: str, rate: str = "+10%") -> None:
    """Función asíncrona interna para sintetizar con Edge-TTS con velocidad acelerada."""
    import edge_tts

    temp_edge = output_path.parent / f"edge_raw_{output_path.name}"
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    await communicate.save(str(temp_edge))

    _master_audio(temp_edge, output_path)
    if temp_edge.exists():
        temp_edge.unlink(missing_ok=True)


def _synthesize_edge_tts(text: str, output_path: Path, voice: str, rate: str = "+10%") -> bool:
    """Genera locución utilizando Microsoft Edge-TTS (Red neural de alta calidad con modulación)."""
    logger.info("Iniciando síntesis de voz con Edge-TTS (Voz: {}, Velocidad: {})...", voice, rate)
    try:
        asyncio.run(_synthesize_edge_tts_async(text, output_path, voice, rate=rate))
        logger.success("Voz de Edge-TTS generada y masterizada exitosamente en: {}", output_path)
        return True
    except Exception as e:
        logger.error("Error al sintetizar con Edge-TTS: {}", e)
        return False


def synthesize_voice(
    text: str,
    output_path: Optional[Path] = None,
    provider: Optional[str] = None,
    voice: Optional[str] = None,
) -> Path:
    """
    Punto de entrada principal para síntesis de voz.
    1. Gemini 3.8 Flash TTS nativo (ultra-humano, expresivo, sin costo adicional).
    2. ElevenLabs (si está configurado con clave válida).
    3. Microsoft Edge-TTS con aceleración TikTok (+10%) y masterización sonora.
    """
    dest = output_path or settings.NARRATION_AUDIO_PATH
    selected_provider = (provider or settings.TTS_PROVIDER).lower()

    # Sanitizar texto para mejorar pausas y entonación
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("El texto de narración está vacío.")

    spoken_text = clean_text
    if getattr(settings, "ENABLE_PHONETIC_CORRECTION", True):
        spoken_text = _apply_phonetic_normalization(clean_text)

    # Definir orden de intentos según el proveedor seleccionado
    providers_order = [selected_provider]
    for fallback in ["gemini", "elevenlabs", "edge-tts"]:
        if fallback not in providers_order:
            providers_order.append(fallback)

    for prov in providers_order:
        if prov == "gemini":
            if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "tu_clave_gemini_aqui":
                gemini_voice = voice if selected_provider == "gemini" and voice else settings.GEMINI_TTS_VOICE
                try:
                    success = _synthesize_gemini_tts_cascade(spoken_text, dest, gemini_voice)
                    if success and dest.exists() and dest.stat().st_size > 0:
                        return dest
                except Exception as e:
                    logger.warning("Error en cascada Gemini TTS: {}", e)
                logger.warning("Gemini TTS no completó la síntesis. Pasando a siguiente proveedor...")
        elif prov == "elevenlabs":
            if settings.ELEVENLABS_API_KEY and settings.ELEVENLABS_API_KEY != "tu_clave_elevenlabs_aqui":
                eleven_voice = voice if selected_provider == "elevenlabs" and voice else settings.ELEVENLABS_VOICE_ID
                try:
                    success = _synthesize_elevenlabs(
                        spoken_text,
                        dest,
                        eleven_voice,
                        settings.ELEVENLABS_API_KEY,
                    )
                    if success and dest.exists() and dest.stat().st_size > 0:
                        return dest
                except Exception as e:
                    logger.warning("Error en ElevenLabs: {}", e)
                logger.warning("ElevenLabs no completó la síntesis. Pasando a siguiente proveedor...")
        elif prov == "edge-tts":
            edge_voice = voice if selected_provider == "edge-tts" and voice else settings.EDGE_TTS_VOICE
            edge_rate = settings.EDGE_TTS_RATE
            try:
                success = _synthesize_edge_tts(spoken_text, dest, edge_voice, rate=edge_rate)
                if success and dest.exists() and dest.stat().st_size > 0:
                    return dest
            except Exception as e:
                logger.warning("Error en Edge-TTS: {}", e)
            logger.warning("Edge-TTS no completó la síntesis. Pasando a siguiente proveedor...")

    raise RuntimeError("No se pudo sintetizar el audio con ningún proveedor disponible.")

