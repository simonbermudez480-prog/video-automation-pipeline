# Instalar Videos Educativos en otra PC

Guía para instalar el programa en una PC con Windows 10 u 11, sin usar comandos.

## Lo que necesitas

- El archivo **`VideosEducativos_Instalador.exe`** y su **contraseña** (te la pasan por separado).
- Conexión a internet (la primera instalación descarga unos 400 MB).
- Unos 3 GB libres en el disco.

## Pasos

1. **Copia** `VideosEducativos_Instalador.exe` a la PC (por USB o como te lo hayan enviado).
2. **Haz doble clic** en el archivo. Si Windows muestra "Windows protegió su PC", pulsa *Más información* → *Ejecutar de todas formas*.
3. **Escribe la contraseña** y elige dónde descomprimir, por ejemplo `C:\Users\TU_USUARIO\Documents`. Se crea la carpeta `VideosEducativos`.
4. Abre esa carpeta y haz **doble clic en `instalar.bat`**. Se abre una ventana negra que va mostrando los pasos:
   - instala Python si no lo tienes (solo para tu usuario, sin pedir permisos de administrador);
   - instala las librerías del programa (5–10 minutos la primera vez);
   - descarga FFmpeg dentro de la carpeta del programa;
   - comprueba el archivo de claves y que el programa arranca;
   - crea el acceso directo **"Videos Educativos"** en el escritorio.
5. Cuando diga **"Instalación completada"**, pulsa una tecla para cerrar.
6. Abre **"Videos Educativos"** desde el escritorio. En la pestaña **"4. Cola y estado"** todo debe aparecer en verde.

> Si un paso falla, el instalador lo dice en rojo. Normalmente basta con revisar internet y volver a ejecutar `instalar.bat`: retoma donde quedó.

## Uso

1. **Crear video:** escribe el tema y pulsa *Crear video* (15–20 minutos).
2. **Revisar y publicar:** mira la hoja de contacto y el video; si te gusta, pulsa *Publicar en YouTube, Instagram y TikTok*.
3. **Historial:** enlaces de lo publicado (doble clic para abrir).
4. **Cola y estado:** espacio en disco, saldo de imágenes y estado de las claves.

Si la carpeta del programa está dentro de OneDrive, ejecuta una vez `python mover_carpeta_trabajo.py`: guarda los videos y trabajos en `%USERPROFILE%\VideosEducativos_trabajo` para no llenar OneDrive.

## Seguridad de las claves

- El archivo `.env` dentro de la carpeta contiene las claves de Gemini, Buffer, Pollinations, Pexels y GitHub. **Con él se puede publicar en las 3 cuentas.** No lo compartas ni lo subas a internet.
- Las dos PCs usan las mismas claves: comparten la cuota diaria gratuita de Gemini y el saldo de imágenes de Pollinations.
- Si la PC se pierde o deja de usarse, revoca el token de GitHub y el de Buffer y crea otros nuevos.

## Para el dueño de la cuenta: crear el token de GitHub (una sola vez)

El programa sube cada video a un repositorio público de GitHub (`video-assets`) para que Buffer pueda leerlo. Para eso usa un token que **solo** puede escribir en ese repositorio.

1. Entra en https://github.com con tu cuenta (`simonbermudez480-prog`).
2. Arriba a la derecha: tu foto → **Settings** → abajo a la izquierda **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
3. Completa:
   - **Token name:** `Videos Educativos - subida de videos`
   - **Expiration:** 1 año (o la que prefieras; cuando caduque hay que crear otro).
   - **Resource owner:** `simonbermudez480-prog`
   - **Repository access:** *Only select repositories* → elige **`video-assets`**.
   - **Permissions → Repository permissions → Contents:** *Read and write*. No actives nada más.
4. Pulsa **Generate token** y **copia** el token (empieza por `github_pat_`). Solo se muestra una vez.
5. Abre el archivo `.env` de la carpeta del programa con el Bloc de notas y añade (o completa) la línea:
   ```
   GITHUB_CDN_TOKEN=github_pat_xxxxxxxxxxxxxxxx
   ```
   Guarda el archivo. No pegues el token en chats ni correos.

## Volver a generar el paquete (en la PC principal)

Doble clic en `empaquetar.bat`: pide una contraseña y crea `dist\VideosEducativos_Instalador.exe` con el código actual y el `.env`.
