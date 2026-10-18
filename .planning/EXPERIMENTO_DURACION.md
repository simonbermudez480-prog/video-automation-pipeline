# Experimento de duración (tarea 22.8, FR-19.8)

**Pregunta:** ¿retienen más los videos de ~1 min que los de ~2,5 min en TikTok, YouTube Shorts e Instagram Reels?

## Diseño
- 6 videos: 3 de **1 min** (A) y 3 de **2,5 min** (B), del mismo tipo de tema (historia insólita con un hecho concreto).
- Se alternan A y B: A, B, A, B, A, B. Uno por día a la misma hora, para que el día y la hora no decidan el resultado.
- Todo lo demás igual: gancho, pregunta final, voz, revisión de imágenes. Solo se publican videos que **superan el control de calidad**.
- En la interfaz: duración «1 min» o «2,5 min» en *Crear video*.

## Temas propuestos (se sortea cuál va en A o en B)
1. El soldado japonés que siguió luchando 29 años después de la guerra (Hiroo Onoda)
2. La noche en que una inundación de melaza arrasó Boston (1919)
3. El hombre que sobrevivió a las dos bombas atómicas (Tsutomu Yamaguchi)
4. La epidemia de baile de Estrasburgo (1518)
5. El oso que fue soldado del ejército polaco (Wojtek)
6. El faro de las islas Flannan y sus tres guardianes desaparecidos (1900)

## Qué medir (a las 48 h y a los 7 días de cada publicación)
En TikTok Studio, YouTube Studio e Instagram (Estadísticas del reel):

| # | Tema | Duración | Plataforma | Vistas 48 h | Tiempo medio visto (s) | % que lo termina | Segundo donde más gente se va | Me gusta | Comentarios |
|---|------|----------|------------|-------------|------------------------|------------------|-------------------------------|----------|-------------|
| 1 |      |          | TikTok     |             |                        |                  |                               |          |             |

## Cómo decidir
- Métrica principal: **% de la duración visto** (tiempo medio / duración) y **vistas a 48 h** en TikTok.
- Si A supera a B en ambas en al menos 2 de las 3 parejas, la duración por defecto pasa a 1 min (`DEFAULT_DURATION_MINUTES=1.0`).
- Si B consigue más tiempo total visto (vistas × tiempo medio) sin perder vistas, se mantiene 2,5 min.
- Con resultados mezclados, se repite con 3 parejas más antes de cambiar nada.

## Estado
- [ ] Usuario aprueba temas y calendario.
- [ ] Producir y revisar los 6 videos.
- [ ] Publicar en días alternos.
- [ ] Rellenar la tabla y decidir.
