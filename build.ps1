$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildPython = "$ProjectRoot\.venv-build\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $BuildPython)) {
    python -m venv "$ProjectRoot\.venv-build"
}
& $BuildPython -m pip install -r "$ProjectRoot\requirements-build.txt"
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }

Push-Location "$ProjectRoot\frontend"
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally {
    Pop-Location
}

$LicenseOutput = Join-Path $ProjectRoot 'docs\THIRD_PARTY_LICENSES.txt'
$LicenseRoots = @(
    (Join-Path $ProjectRoot '.venv-build\Lib\site-packages'),
    (Join-Path $ProjectRoot 'frontend\node_modules')
)
$LicenseRecords = foreach ($Root in $LicenseRoots) {
    Get-ChildItem -LiteralPath $Root -File -Recurse | Where-Object {
        $_.Name -match '^(LICENSE|LICENCE|COPYING|NOTICE)(\..*)?$'
    } | ForEach-Object {
        $LicensePath = $_.FullName
        try {
            $Content = [IO.File]::ReadAllText($LicensePath)
            $Bytes = [Text.Encoding]::UTF8.GetBytes($Content)
            $Hasher = [Security.Cryptography.SHA256]::Create()
            try {
                $Hash = [BitConverter]::ToString($Hasher.ComputeHash($Bytes)).Replace('-', '')
            } finally {
                $Hasher.Dispose()
            }
            [PSCustomObject]@{
                Hash = $Hash
                Path = $LicensePath.Substring($ProjectRoot.Length + 1)
                Content = $Content
            }
        } catch {
            Write-Warning "License file skipped: $LicensePath"
        }
    }
}
$Builder = [Text.StringBuilder]::new("D5 Macro third-party license texts`r`n")
foreach ($Group in ($LicenseRecords | Group-Object Hash | Sort-Object Name)) {
    [void]$Builder.AppendLine("`r`n================================================================================")
    [void]$Builder.AppendLine("Included by:")
    foreach ($Record in $Group.Group) { [void]$Builder.AppendLine("- $($Record.Path)") }
    [void]$Builder.AppendLine("================================================================================`r`n")
    [void]$Builder.AppendLine($Group.Group[0].Content)
}
[IO.File]::WriteAllText($LicenseOutput, $Builder.ToString(), [Text.UTF8Encoding]::new($false))

Push-Location $ProjectRoot
try {
    & $BuildPython -m PyInstaller --clean --noconfirm D5Macro.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    $Iscc = Get-Command iscc -ErrorAction SilentlyContinue
    $IsccPath = if ($Iscc) { $Iscc.Source } else { "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" }
    if (Test-Path -LiteralPath $IsccPath) {
        & $IsccPath "$ProjectRoot\installer\D5Macro.iss"
        if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
    } else {
        Write-Warning 'Inno Setup is not installed. The app bundle was created in dist\D5Macro; install Inno Setup and rerun to create the setup EXE.'
    }
} finally {
    Pop-Location
}
