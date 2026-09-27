<#
  Instalador de Gwensper para Windows.

  Uso normal: descarga Instalar-Gwensper.bat desde la página de Releases y dale doble clic.
  O en PowerShell:
    & ([scriptblock]::Create((irm https://raw.githubusercontent.com/whosluisnoris/gwensper/main/install/install.ps1).TrimStart([char]0xFEFF)))

  Qué hace:
    1. Busca Python 3.10-3.13 de 64 bits; si no hay, instala Python 3.12 (con winget o desde python.org).
    2. Crea un entorno propio en %LOCALAPPDATA%\Programs\Gwensper (no toca el resto de tu PC).
    3. Instala Gwensper y sus librerías; si hay una GPU NVIDIA funcionando, también las de CUDA.
    4. Descarga el modelo de voz.
    5. Crea el acceso directo en el menú Inicio y registra Gwensper en "Aplicaciones instaladas".
    6. Abre Gwensper.

  Volver a ejecutarlo actualiza Gwensper a la última versión.
  Opciones avanzadas y de prueba: -Source (zip, URL o carpeta), -InstallDir, -Mode cpu|gpu,
  -Model, -Python (ruta a python.exe), -NoShortcut (sin acceso directo ni registro),
  -NoLaunch, -NoPause.
#>
param(
    [string]$Source = "https://github.com/whosluisnoris/gwensper/archive/refs/heads/main.zip",
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\Gwensper",
    [ValidateSet("auto", "cpu", "gpu")][string]$Mode = "auto",
    [string]$Model = "",
    [string]$Python = "",  # ruta a un python.exe concreto (salta la búsqueda)
    [switch]$NoShortcut,
    [switch]$NoLaunch,
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest es mucho más rápido sin barra
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Version = "0.2"
$InstallDir = $InstallDir.TrimEnd("\")
$MinorMin = 10
$MinorMax = 13  # versiones de Python con librerías disponibles (ctranslate2, PySide6, av)

function Step([string]$text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Info([string]$text) { Write-Host "    $text" }
function Done([string]$text) { Write-Host "    $text" -ForegroundColor Green }
function Stop-WithError([string]$text) {
    Write-Host ""
    Write-Host "  No se pudo completar la instalación: $text" -ForegroundColor Red
    Write-Host "  Si el problema sigue, abre un issue en https://github.com/whosluisnoris/gwensper/issues" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "Presiona Enter para cerrar" | Out-Null }
    # throw en lugar de exit: ejecutado como scriptblock, exit cerraría la ventana de PowerShell.
    throw "GWENSPER_INSTALL_FAILED"
}

# Cualquier error inesperado (sin internet, permisos…) termina con un mensaje entendible.
trap {
    if ("$_" -ne "GWENSPER_INSTALL_FAILED") {
        Write-Host ""
        Write-Host "  No se pudo completar la instalación: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  Revisa tu conexión a internet y vuelve a intentarlo." -ForegroundColor Red
        if (-not $NoPause) { Read-Host "Presiona Enter para cerrar" | Out-Null }
    }
    break
}

# Ejecuta un programa y falla con un mensaje claro si termina con error.
function Invoke-Checked([string]$what, [string]$exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { Stop-WithError "$what (código $LASTEXITCODE)." }
}

# Describe un Python: versión, 64 bits y si es el de la Microsoft Store. $null si no funciona.
function Get-PythonInfo([string]$exe, [string[]]$prefix) {
    $ErrorActionPreference = "Continue"  # un aviso en stderr no debe descartar un Python válido
    $code = "import sys, struct; print('%d.%d %d %s' % (sys.version_info[0], sys.version_info[1], struct.calcsize('P') * 8, sys.base_prefix))"
    try { $out = & $exe @prefix -c $code 2>$null } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    $parts = "$out".Trim().Split(" ", 3)
    $ver = $parts[0].Split(".")
    return @{
        Version = $parts[0]; Major = [int]$ver[0]; Minor = [int]$ver[1]
        Bits = [int]$parts[1]; Store = ($parts[2] -match "\\WindowsApps\\")
    }
}

function Find-Python {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        # Las versiones probadas primero, en orden de preferencia (no la más nueva a ciegas).
        foreach ($v in @("3.12", "3.11", "3.13", "3.10")) { $candidates += , @("py", @("-$v")) }
    }
    $dirs = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*" -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch "-32$" } | Sort-Object { [int]($_.Name -replace "\D", "") } -Descending
    foreach ($d in $dirs) { $candidates += , @((Join-Path $d.FullName "python.exe"), @()) }
    foreach ($name in @("python", "python3")) {
        if (Get-Command $name -ErrorAction SilentlyContinue) { $candidates += , @($name, @()) }
    }
    foreach ($c in $candidates) {
        $info = Get-PythonInfo $c[0] $c[1]
        if (-not $info) { continue }
        if ($info.Major -ne 3 -or $info.Minor -lt $MinorMin -or $info.Minor -gt $MinorMax) { continue }
        if ($info.Bits -ne 64) { continue }
        # El Python de la Microsoft Store redirige carpetas del usuario: el entorno podría
        # quedar donde el instalador no lo encuentra. Mejor instalar uno normal.
        if ($info.Store) { continue }
        return @{ Exe = $c[0]; Prefix = $c[1]; Version = $info.Version }
    }
    return $null
}

# /passive muestra la barra de progreso de Python (sin preguntas). Se omiten las pruebas,
# la documentación y Tcl/Tk: Gwensper no los usa y alargan varios minutos la instalación.
$PythonInstallArgs = "/passive /norestart InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 Include_doc=0 Include_tcltk=0"

function Install-Python {
    Info "Voy a instalar Python 3.12 (solo para tu usuario). Tarda de 2 a 5 minutos"
    Info "y verás su barra de progreso. No cierres esta ventana."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        & winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --override $PythonInstallArgs | Out-Host
        if ($LASTEXITCODE -eq 0) { return }
        Info "winget no pudo; lo intento con el instalador de python.org."
    }
    $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    $installer = Join-Path $env:TEMP "python-3.12.10-amd64.exe"
    Info "Descargando Python 3.12 desde python.org…"
    Invoke-WebRequest $url -OutFile $installer -UseBasicParsing
    $p = Start-Process $installer -ArgumentList $PythonInstallArgs -Wait -PassThru
    Remove-Item $installer -ErrorAction SilentlyContinue
    if ($p.ExitCode -notin 0, 3010) { Stop-WithError "el instalador de Python terminó con código $($p.ExitCode)." }
}

# Solo cuenta como GPU utilizable si hay una NVIDIA y su controlador responde.
function Test-NvidiaGpu {
    try {
        if (-not (Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match "NVIDIA" })) { return $false }
        $ErrorActionPreference = "Continue"
        & nvidia-smi -L *> $null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

# Busca cuBLAS y cuDNN de CUDA 12 ya instalados (p. ej. dentro de PyTorch o de un CUDA
# Toolkit con cuDNN). Si están, no hace falta descargar ~1.3 GB del extra [cuda].
function Find-CudaDlls {
    $dirs = @()
    $sitePackages = @(
        "$env:LOCALAPPDATA\Packages\PythonSoftwareFoundation.Python*\LocalCache\local-packages\Python3*\site-packages",
        "$env:LOCALAPPDATA\Programs\Python\Python3*\Lib\site-packages",
        "$env:APPDATA\Python\Python3*\site-packages",
        "C:\Program Files\Python3*\Lib\site-packages"
    )
    foreach ($pattern in $sitePackages) {
        foreach ($sp in (Get-ChildItem $pattern -Directory -ErrorAction SilentlyContinue)) {
            $dirs += Join-Path $sp.FullName "torch\lib"
        }
    }
    if ($env:CUDA_PATH) { $dirs += Join-Path $env:CUDA_PATH "bin" }
    foreach ($d in $dirs) {
        if ((Test-Path (Join-Path $d "cublas64_12.dll")) -and (Test-Path (Join-Path $d "cublasLt64_12.dll")) -and
            (Test-Path (Join-Path $d "cudnn64_9.dll")) -and (Test-Path (Join-Path $d "cudnn_ops64_9.dll"))) {
            return $d
        }
    }
    return $null
}

# Cierra Gwensper si corre desde esta instalación. El Python real de la app es un proceso
# hijo cuya ruta está fuera de la carpeta, por eso también se busca en la línea de comandos.
function Stop-InstalledApp([string]$dir) {
    $prefix = "$dir\"
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.CommandLine.IndexOf($prefix, [StringComparison]::OrdinalIgnoreCase) -ge 0)
    } | Where-Object { $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Write-Uninstaller([string]$path) {
    $content = @'
# Desinstalador de Gwensper (generado por el instalador).
param([switch]$Quiet)
$ErrorActionPreference = "Continue"
$dir = (Split-Path -Parent $MyInvocation.MyCommand.Path).TrimEnd("\")
$prefix = "$dir\"
Write-Host "Desinstalando Gwensper..." -ForegroundColor Cyan

# Cierra solo esta instalación (gwensper.exe y su Python, que es un proceso hijo).
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) -or
    ($_.CommandLine -and $_.CommandLine.IndexOf($prefix, [StringComparison]::OrdinalIgnoreCase) -ge 0)
} | Where-Object { $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800

# Solo borra accesos directos que apunten a ESTA instalación (puede haber otra, p. ej. de desarrollo).
$programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$shell = New-Object -ComObject WScript.Shell
foreach ($link in @((Join-Path $programs "Gwensper.lnk"), (Join-Path $programs "Startup\Gwensper.lnk"))) {
    if ((Test-Path $link) -and $shell.CreateShortcut($link).TargetPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item $link -ErrorAction SilentlyContinue
    }
}
$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Gwensper"
$registered = (Get-ItemProperty $key -ErrorAction SilentlyContinue).InstallLocation
if ($registered -and $registered.TrimEnd("\") -eq $dir) { Remove-Item $key -Recurse -ErrorAction SilentlyContinue }

if (-not $Quiet) {
    Write-Host ""
    Write-Host "Los modelos de voz ocupan entre 75 MB y 3 GB. Otras apps que usen faster-whisper"
    Write-Host "pueden compartirlos."
    $answer = Read-Host "¿Borrar también tu configuración y los modelos de voz de Gwensper? (s/N)"
    if ($answer -match '^[sS]') {
        $vpy = Join-Path $dir "venv\Scripts\python.exe"
        if (Test-Path $vpy) {
            # Usa la API de la caché de Hugging Face: libera también los archivos compartidos.
            & $vpy -c "from gwensper import models; [models.delete(m.name) for m in models.CATALOG]"
        }
        Remove-Item (Join-Path $env:APPDATA "Gwensper") -Recurse -Force -ErrorAction SilentlyContinue
        Get-ChildItem "$env:LOCALAPPDATA\Packages\PythonSoftwareFoundation.Python*\LocalCache\Roaming\Gwensper" -Directory -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Configuración y modelos borrados."
    }
}

# La carpeta se borra al final desde otro proceso, porque este script vive dentro de ella.
$quoted = $dir.Replace("'", "''")
Start-Process powershell -WindowStyle Hidden -WorkingDirectory $env:TEMP -ArgumentList "-NoProfile -Command `"Start-Sleep 2; Remove-Item -LiteralPath '$quoted' -Recurse -Force`""
Write-Host "Gwensper se desinstaló." -ForegroundColor Green
if (-not $Quiet) { Start-Sleep 2 }
'@
    # UTF-8 con BOM: PowerShell 5.1 lo necesita para leer bien los acentos con -File.
    [System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding $true))
}

# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  Gwensper $($Version): dictado por voz con Whisper" -ForegroundColor White
Write-Host "  Se instalará en $InstallDir"

Step "Buscando Python"
if ($Python) {
    $info = Get-PythonInfo $Python @()
    if (-not $info) { Stop-WithError "no pude ejecutar $Python." }
    $pyInfo = @{ Exe = $Python; Prefix = @(); Version = $info.Version }
} else {
    $pyInfo = Find-Python
}
if (-not $pyInfo) {
    Info "No hay un Python que Gwensper pueda usar en tu PC (necesita 3.$MinorMin a 3.$MinorMax de 64 bits)."
    Install-Python
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    $pyInfo = Find-Python
    if (-not $pyInfo) { Stop-WithError "no encontré Python después de instalarlo. Cierra esta ventana y vuelve a ejecutar el instalador." }
}
Done "Python $($pyInfo.Version)"

$gpu = switch ($Mode) { "gpu" { $true } "cpu" { $false } default { Test-NvidiaGpu } }
$cudaDir = $null
if ($gpu) {
    $cudaDir = Find-CudaDlls
    if ($cudaDir) {
        Info "Detecté una GPU NVIDIA y ya tienes las librerías de CUDA en:"
        Info "  $cudaDir"
        Info "Gwensper usará esas; no hace falta descargar 1.3 GB más."
    } else {
        Info "Detecté una GPU NVIDIA: instalaré la aceleración CUDA (unos 1.3 GB extra)."
    }
} else {
    Info "Sin GPU NVIDIA: Gwensper funcionará con el procesador."
}

Stop-InstalledApp $InstallDir

Step "Preparando el entorno de Gwensper"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$venv = Join-Path $InstallDir "venv"
$vpy = Join-Path $venv "Scripts\python.exe"
if (Test-Path $vpy) {
    # Un entorno roto (Python base desinstalado, creación interrumpida) se rehace.
    $ErrorActionPreference = "Continue"
    & $vpy -m pip --version *> $null
    $broken = $LASTEXITCODE -ne 0
    $ErrorActionPreference = "Stop"
    if ($broken) { Info "El entorno anterior estaba dañado; lo creo de nuevo."; Remove-Item $venv -Recurse -Force }
}
if (-not (Test-Path $vpy)) {
    Invoke-Checked "no se pudo crear el entorno de Python" $pyInfo.Exe ($pyInfo.Prefix + @("-m", "venv", $venv))
    if (-not (Test-Path $vpy)) { Stop-WithError "el entorno de Python no quedó en $venv." }
}
Done "Entorno listo"

Step "Instalando Gwensper y sus librerías (puede tardar varios minutos, no cierres esta ventana)"
$withCuda = $gpu -and -not $cudaDir
if ($Source -match "^https?://") {
    $spec = if ($withCuda) { "gwensper[cuda] @ $Source" } else { "gwensper @ $Source" }
} else {
    $spec = if ($withCuda) { "$Source[cuda]" } else { $Source }
}
Invoke-Checked "no se pudo actualizar pip" $vpy @("-m", "pip", "install", "--upgrade", "--quiet", "--disable-pip-version-check", "pip")
Invoke-Checked "no se pudieron instalar las librerías" $vpy @("-m", "pip", "install", "--upgrade", "--quiet", "--disable-pip-version-check", $spec)
# Fuerza la versión más reciente de Gwensper aunque el número de versión no haya cambiado.
Invoke-Checked "no se pudo instalar Gwensper" $vpy @("-m", "pip", "install", "--upgrade", "--force-reinstall", "--no-deps", "--quiet", "--disable-pip-version-check", $Source)
if ($cudaDir) {
    # Guarda en la configuración de Gwensper dónde están las DLL de CUDA existentes.
    $env:GWENSPER_CUDA_PATH = $cudaDir
    Invoke-Checked "no se pudo guardar la configuración" $vpy @("-c", "import os; from gwensper.config import Config; c = Config.load(); c.cuda_path = os.environ['GWENSPER_CUDA_PATH']; c.save()")
}
Done "Librerías instaladas"

Step "Descargando el modelo de voz"
if (-not $Model) { $Model = if ($gpu) { "large-v3-turbo" } else { "small" } }
Invoke-Checked "no se pudo descargar el modelo" $vpy @("-m", "gwensper", "--download-model", $Model)

Step "Registrando Gwensper en Windows"
$exe = Join-Path $venv "Scripts\gwensper.exe"
$uninstaller = Join-Path $InstallDir "desinstalar.ps1"
Write-Uninstaller $uninstaller
if (-not $NoShortcut) {
    Invoke-Checked "no se pudo crear el acceso directo" $vpy @("-m", "gwensper", "--install-shortcut")
    $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Gwensper"
    New-Item -Path $key -Force | Out-Null
    $values = @{
        DisplayName          = "Gwensper"
        DisplayVersion       = $Version
        Publisher            = "Luis Noris Garcia"
        DisplayIcon          = (Join-Path $venv "Lib\site-packages\gwensper\assets\icon.ico")
        InstallLocation      = $InstallDir
        URLInfoAbout         = "https://github.com/whosluisnoris/gwensper"
        UninstallString      = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstaller`""
        QuietUninstallString = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstaller`" -Quiet"
    }
    foreach ($k in $values.Keys) { Set-ItemProperty -Path $key -Name $k -Value $values[$k] }
    Set-ItemProperty -Path $key -Name NoModify -Value 1 -Type DWord
    Set-ItemProperty -Path $key -Name NoRepair -Value 1 -Type DWord
    Done "Acceso directo en el menú Inicio y entrada en Aplicaciones instaladas"
}

Write-Host ""
Write-Host "  Gwensper quedó instalado." -ForegroundColor Green
if ($NoShortcut) { Write-Host "  Ábrelo con: $exe" }
else { Write-Host "  Búscalo como 'Gwensper' en el menú Inicio." }
Write-Host "  Para dictar, presiona Ctrl+Alt+D en cualquier app."
if (-not $NoLaunch) { Start-Process $exe }
if (-not $NoPause) { Read-Host "Presiona Enter para cerrar" | Out-Null }
