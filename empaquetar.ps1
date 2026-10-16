# Genera dist\VideosEducativos_Instalador.exe: autoextraíble de 7-Zip cifrado (AES-256) con el programa y el .env.
param([string]$Password = "")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$SevenZip = @("$env:ProgramFiles\7-Zip\7z.exe", "${env:ProgramFiles(x86)}\7-Zip\7z.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $SevenZip) { Write-Host "Falta 7-Zip (https://www.7-zip.org). Instálalo y vuelve a ejecutar." -ForegroundColor Red; exit 1 }
$Sfx = Join-Path (Split-Path $SevenZip) "7z.sfx"
if (-not (Test-Path $Sfx)) { Write-Host "Falta el módulo 7z.sfx de 7-Zip." -ForegroundColor Red; exit 1 }
if (-not (Test-Path ".env")) { Write-Host "No existe el archivo .env en esta carpeta." -ForegroundColor Red; exit 1 }

if (-not $Password) {
    $s1 = Read-Host "Contraseña para el paquete (mínimo 12 caracteres)" -AsSecureString
    $s2 = Read-Host "Repite la contraseña" -AsSecureString
    $p1 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s1))
    $p2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s2))
    if ($p1 -ne $p2) { Write-Host "Las contraseñas no coinciden." -ForegroundColor Red; exit 1 }
    $Password = $p1
}
if ($Password.Length -lt 12) { Write-Host "La contraseña debe tener al menos 12 caracteres." -ForegroundColor Red; exit 1 }

# Solo lo necesario para instalar y usar el programa (sin videos, trabajos, backups ni historial de git)
$Incluir = @("main.py", "app.py", "requirements.txt", "instalar.bat", "instalar.ps1", "Abrir_Videos_Educativos.bat",
             "empaquetar.bat", "empaquetar.ps1", ".env.example", ".env", "README.md", "INSTALACION.md")
$Stage = Join-Path $Root "dist\staging\VideosEducativos"
if (Test-Path (Join-Path $Root "dist\staging")) { Remove-Item (Join-Path $Root "dist\staging") -Recurse -Force }
New-Item -ItemType Directory -Force (Join-Path $Stage "src") | Out-Null
foreach ($f in $Incluir) { Copy-Item (Join-Path $Root $f) $Stage }
Get-ChildItem (Join-Path $Root "src") -Filter *.py | Copy-Item -Destination (Join-Path $Stage "src")

$Out = Join-Path $Root "dist\VideosEducativos_Instalador.exe"
if (Test-Path $Out) { Remove-Item $Out -Force }
Push-Location (Join-Path $Root "dist\staging")
& $SevenZip a -t7z "-sfx$Sfx" "-p$Password" -mhe=on -mx=9 $Out "VideosEducativos" | Out-Null
$code = $LASTEXITCODE
Pop-Location
Remove-Item (Join-Path $Root "dist\staging") -Recurse -Force
if ($code -ne 0) { Write-Host "7-Zip falló (código $code)." -ForegroundColor Red; exit 1 }
$mb = [math]::Round((Get-Item $Out).Length / 1MB, 2)
Write-Host "Paquete creado: $Out ($mb MB)" -ForegroundColor Green
Write-Host "Pásalo a la otra PC y envía la contraseña por un canal distinto." -ForegroundColor Green
exit 0
