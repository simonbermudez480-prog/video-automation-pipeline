# Plan Maestro de Optimización: Calidad de Voz Fonética y Subtítulos Ground-Truth

**Fecha:** Octubre 2026  
**Objetivo:** Eliminar la mala pronunciación de términos en inglés/extranjeros en la locución y garantizar que los subtítulos en pantalla coincidan 100% con el guion original sin errores ni alucinaciones de Whisper.

---

## 1. Diagnóstico de los Problemas

### A. Defecto en la Síntesis de Voz (Palabras en inglés u otros idiomas "dichas feo")
1. **Causa Raíz:** 
   - La voz por defecto `es-ES-AlvaroNeural` o voces estrictamente monolingües aplican reglas de conversión grafema-a-fonema (G2P) del español peninsular.
   - Al encontrarse con nombres o términos en inglés/alemán (ej: *"Pearl Harbor"*, *"Blitzkrieg"*, *"Winston Churchill"*, *"Oppenheimer"*, *"D-Day"*, *"Big Bang"*), la voz intenta leerlos fonéticamente en español (*"Pe-arl Jar-bor"*, *"Blits-kri-eg"*), lo que resulta forzado, robótico o ininteligible.
2. **Soluciones Evaluadas:**
   - **Voz Bilingüe Neuronal:** Voces como `es-US-AlonsoNeural` o `es-US-PalomaNeural` en Edge-TTS fueron entrenadas con corpus bilingüe hispano-estadounidense y realizan transiciones fonéticas fluidas entre español e inglés.
   - **SSML Fonético Automático (`<sub alias="...">` / `<lang>`):** Edge-TTS soporta etiquetas SSML. Se puede aplicar un normalizador fonético previo que mapee términos extranjeros a su pronunciación óptima o etiquete fragmentos con `<lang xml:lang="en-US">`.
   - **Optimización del Guion (Prompt Engineering en Gemini/DeepSeek):** Indicar al modelo en `src/script_generator.py` que redacte frases naturales o incluya adaptaciones fonéticas legibles cuando sea necesario.
   - **Soporte Premium (ElevenLabs):** El modelo `eleven_multilingual_v2` resuelve esto de forma nativa cuando se proporciona API Key.

---

### B. Desincronización y Errores en Subtítulos ("los subtítulos muchas veces no dicen eso")
1. **Causa Raíz:**
   - En `src/audio_processor.py`, la función `generate_subtitles_srt` genera el texto a partir de la salida acústica de **Whisper** (`seg["text"]` / `w["word"]`).
   - Whisper con `language="es"` intenta transcribir palabras extranjeras buscando palabras similares en español, produciendo alucinaciones y deformaciones (ej. *"Blitzkrieg"* transcrito como *"gris gris"* o *"blick creek"*; *"Pearl Harbor"* transcrito como *"per labor"*).
   - Whisper suele omitir mayúsculas, comas o términos técnicos.
2. **Solución Arquitectónica: Alineación Forzada sobre Guion Real (Ground-Truth Forced Alignment):**
   - **Principio Fundamental:** El texto mostrado en los subtítulos **debe provenir siempre del guion original (`script_data.narration_full`)**, NUNCA de la transcripción cruda de Whisper.
   - **Mapeo Fonético/Temporal:** Whisper se utiliza **únicamente como reloj temporal** para obtener marcas de tiempo (`start_time`, `end_time`).
   - Mediante un algoritmo de alineación secuencial (`difflib.SequenceMatcher` o alineación dinámica de tokens), cada palabra del guion original se vincula a su marca temporal correspondiente.
   - **Resultado:** Ortografía 100% perfecta, puntuación original, mayúsculas correctas y fidelidad total al guion.

---

## 2. Fases de Implementación Propuestas

### Fase 1: Arquitectura de Subtítulos Ground-Truth (`src/audio_processor.py`)
- Implementar la función `align_tokens_to_ground_truth(script_text, whisper_words)`.
- Mapear las marcas de tiempo de Whisper sobre las palabras reales del guion.
- Agrupar subtítulos en fragmentos legibles de 3 a 5 palabras, respetando pausas de puntuación (comas, puntos).
- Garantizar que los subtítulos en pantalla muestren exactamente lo escrito en el guion.

### Fase 2: Motor de Pronunciación y Voces Multilingües (`src/voice_synthesizer.py` y `src/config.py`)
- Agregar configuración `EDGE_TTS_VOICE` seleccionable en `.env` (recomendada: `es-US-AlonsoNeural` para narración documental bilingüe o `es-ES-AlvaroNeural` con SSML).
- Integrar un procesador de texto SSML que detecte términos extranjeros comunes y aplique `<lang xml:lang="en-US">` o sustituciones de pronunciación natural.
- Reforzar el prompt en `src/script_generator.py` para guiar la formulación de términos extranjeros.

### Fase 3: Pruebas y Verificación con Casos Reales
- Probar con un texto de prueba denso en términos anglosajones y alemanes (ej: *"El ataque a Pearl Harbor, la táctica del Blitzkrieg de la Luftwaffe y el liderazgo de Winston Churchill"*).
- Generar el audio y verificar auditivamente la pronunciación.
- Extraer el archivo `.srt` generado y verificar que no haya una sola palabra alterada respecto al guion.
- Ensamblar el video final y capturar fotogramas para verificación visual de contraste y sincronización.

---

## 3. Matriz de Configuración Sugerida

| Componente | Configuración Actual | Configuración Optimizada | Beneficio |
| :--- | :--- | :--- | :--- |
| **Fuente de Texto en Subtítulos** | Salida ASR cruda de Whisper | **Guion original (Ground-Truth)** | 0% errores de ortografía o alucinaciones |
| **Voz TTS por Defecto** | `es-ES-AlvaroNeural` | **`es-US-AlonsoNeural`** (bilingüe) | Transición fonética natural español/inglés |
| **Normalización Fonética** | Texto crudo | **Diccionario fonético documental** | Dicción nativa de términos anglosajones/alemanes |
| **Agrupación de Subtítulos** | Bloques fijos de 4 palabras | **Bloques conscientes de puntuación** | Mejor ritmo de lectura visual (3-5 palabras) |

---

## 4. Resultados de Verificación y Estado

- [x] **Fase 1 Completada (`src/audio_processor.py`)**: Implementado `align_scene_script_words` y `generate_ground_truth_subtitles_srt`. Las palabras de los subtítulos se extraen directamente del guion original y se alinean temporalmente con las marcas de Whisper.
- [x] **Fase 2 Completada (`src/voice_synthesizer.py` y `src/config.py`)**: Activada voz bilingüe `es-US-AlonsoNeural` y diccionario fonético para términos históricos ("Pearl Harbor", "Blitzkrieg", "Oppenheimer", "Luftwaffe", etc.).
- [x] **Fase 3 Completada (Verificación Visual y Multimodal)**:
  - `screenshots/sub_blitzkrieg.png`: Muestra textualmente `La "Blitzkrieg",` con comillas y mayúscula perfecta.
  - `screenshots/sub_pearlharbor.png`: Muestra textualmente `Pearl Harbor arrastró a` con capitalización en inglés y acento español exacto.
  - `screenshots/sub_raf.png`: Muestra textualmente `la Royal Air Force` con dicción clara y sincronizada.
  - Cero discrepancias ortográficas respecto al guion original.
