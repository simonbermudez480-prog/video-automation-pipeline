# Instalador de Videos Educativos (Fase 19). Se ejecuta con doble clic en instalar.bat.
# -SinAccesoDirecto: no crea el acceso directo del escritorio (para pruebas).
param([switch]$SinAccesoDirecto)
# Instala lo necesario solo para este usuario y dentro de esta carpeta, sin permisos de administrador.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # descargas mucho más rápidas en PowerShell 5.1
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$PythonVersion = "3.12.6"
$FfmpegUrls = @(
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
)

function Paso($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }
function Ok($texto) { Write-Host "    [OK] $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "    [!] $texto" -ForegroundColor Yellow }
function Fallo($texto) {
    Write-Host ""; Write-Host "    [X] $texto" -ForegroundColor Red
    Write-Host "    La instalación no terminó. Revisa tu conexión a internet y vuelve a ejecutar instalar.bat." -ForegroundColor Red
    exit 1
}

function Buscar-Python {
    $candidatos = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
    )
    foreach ($c in $candidatos) { if (Test-Path $c) { return $c } }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $ruta = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ruta) { return $ruta.Trim() }
    }
    $p = Get-Command python -ErrorAction SilentlyContinue
    if ($p -and $p.Source -notlike "*WindowsApps*") { return $p.Source }  # el de WindowsApps es solo un acceso a la Tienda
    return $null
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Instalador de Videos Educativos" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# 0. Ruta corta: Windows no admite rutas de más de 260 caracteres y las librerías crean carpetas muy profundas
if ($Root.Length -gt 90) {
    Fallo "La carpeta del programa está en una ruta demasiado larga ($($Root.Length) caracteres): $Root. Mueve la carpeta VideosEducativos a un lugar más corto, por ejemplo Documentos, y vuelve a ejecutar instalar.bat."
}

# 1. Python
Paso "1/6 Comprobando Python"
$Python = Buscar-Python
if ($Python) {
    $ver = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])"
    if ([version]$ver -lt [version]"3.10") { Aviso "Python $ver es demasiado antiguo; se instalará $PythonVersion."; $Python = $null }
}
if (-not $Python) {
    $instalador = Join-Path $env:TEMP "python-$PythonVersion-amd64.exe"
    Write-Host "    Descargando Python $PythonVersion (unos 25 MB)..."
    try { Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe" -OutFile $instalador }
    catch { Fallo "No se pudo descargar Python: $($_.Exception.Message)" }
    Write-Host "    Instalando Python (solo para este usuario, puede tardar 1-2 minutos)..."
    $proc = Start-Process $instalador -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_tcltk=1 Include_launcher=1 Include_test=0" -Wait -PassThru
    if ($proc.ExitCode -ne 0) { Fallo "El instalador de Python terminó con código $($proc.ExitCode)." }
    $Python = Buscar-Python
    if (-not $Python) { Fallo "Python se instaló pero no se encuentra." }
}
Ok "Python: $Python"
& $Python -c "import tkinter" 2>$null
if ($LASTEXITCODE -ne 0) { Fallo "Este Python no tiene Tkinter (necesario para la ventana). Reinstala Python marcando 'tcl/tk and IDLE'." }

# 2. Entorno y librerías
Paso "2/6 Instalando las librerías del programa (puede tardar 5-10 minutos la primera vez)"
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fallo "No se pudo crear el entorno de Python (.venv)." }
}
& $VenvPy -m pip install --upgrade pip --disable-pip-version-check -q
& $VenvPy -m pip install -r requirements.txt --disable-pip-version-check -q
if ($LASTEXITCODE -ne 0) { Fallo "No se pudieron instalar las librerías (pip)." }
Ok "Librerías instaladas en .venv"

# 3. FFmpeg (dentro de la carpeta del programa)
Paso "3/6 Comprobando FFmpeg (montaje de video)"
$FfmpegBin = Join-Path $Root "tools\ffmpeg\bin"
if (Test-Path (Join-Path $FfmpegBin "ffmpeg.exe")) {
    Ok "FFmpeg ya está en tools\ffmpeg"
} elseif (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Ok "FFmpeg ya está instalado en el sistema"
} else {
    $zip = Join-Path $env:TEMP "ffmpeg-essentials.zip"
    $tmp = Join-Path $env:TEMP "ffmpeg-extract"
    $descargado = $false
    foreach ($url in $FfmpegUrls) {
        Write-Host "    Descargando FFmpeg (unos 100-200 MB) desde $(([uri]$url).Host)..."
        if (Test-Path $zip) { Remove-Item $zip -Force }
        # curl.exe viene con Windows 10/11: reanuda y reintenta si el servidor corta la conexión
        & curl.exe -L --fail --retry 5 --retry-delay 3 --retry-all-errors -C - -o $zip $url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $zip) -and (Get-Item $zip).Length -gt 30MB) { $descargado = $true; break }
        Aviso "Esa descarga falló; probando otra fuente..."
    }
    if (-not $descargado) { Fallo "No se pudo descargar FFmpeg de ninguna fuente." }
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive $zip -DestinationPath $tmp -Force
    $bin = Get-ChildItem $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    if (-not $bin) { Fallo "El archivo de FFmpeg no contiene ffmpeg.exe." }
    New-Item -ItemType Directory -Force $FfmpegBin | Out-Null
    Copy-Item (Join-Path $bin.DirectoryName "*.exe") $FfmpegBin -Force
    Remove-Item $tmp -Recurse -Force; Remove-Item $zip -Force
    Ok "FFmpeg instalado en tools\ffmpeg"
}
$env:PATH = "$FfmpegBin;$env:PATH"

# 4. Claves (.env)
Paso "4/6 Comprobando el archivo de claves (.env)"
if (Test-Path (Join-Path $Root ".env")) {
    Ok "Archivo .env encontrado"
} else {
    Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
    Aviso "No había .env: se creó uno vacío desde .env.example. Debes completar las claves antes de crear videos."
}

# 5. Prueba de arranque
Paso "5/6 Probando que el programa arranca"
$env:PYTHONIOENCODING = "utf-8"
$LogPrueba = Join-Path $env:TEMP "videos_educativos_prueba.log"
# El registro del programa sale por la salida de errores: se redirige con cmd para que PowerShell 5.1 no lo trate como fallo
cmd /c "`"$VenvPy`" main.py --topic `"Prueba de instalacion`" --dry-run > `"$LogPrueba`" 2>&1"
if ($LASTEXITCODE -ne 0) { Fallo "La prueba de arranque falló. Detalle en $LogPrueba" }
cmd /c "`"$VenvPy`" -c `"import app`" >> `"$LogPrueba`" 2>&1"
if ($LASTEXITCODE -ne 0) { Fallo "La ventana del programa no se pudo cargar. Detalle en $LogPrueba" }
Ok "El programa arranca correctamente"

# 6. Acceso directo
Paso "6/6 Creando el acceso directo en el escritorio"
if ($SinAccesoDirecto) { Aviso "Omitido (-SinAccesoDirecto)." } else {
$escritorio = [Environment]::GetFolderPath("Desktop")
$acceso = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $escritorio "Videos Educativos.lnk"))
$acceso.TargetPath = Join-Path $Root "Abrir_Videos_Educativos.bat"
$acceso.WorkingDirectory = $Root
$acceso.WindowStyle = 7
$acceso.Description = "Crear, revisar y publicar videos educativos"
$acceso.Save()
Ok "Acceso directo 'Videos Educativos' creado en el escritorio"
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "   Instalación completada" -ForegroundColor Green
Write-Host "   Abre 'Videos Educativos' desde el escritorio." -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
exit 0
