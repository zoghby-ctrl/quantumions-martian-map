Add-Type -AssemblyName System.Drawing
$videoSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'MakeMarswalkVideo.cs') -Raw
$drawingAssembly = [System.Drawing.Bitmap].Assembly.Location
Add-Type -TypeDefinition $videoSource -ReferencedAssemblies $drawingAssembly -ErrorAction Stop
$outputPath = Join-Path (Split-Path $PSScriptRoot -Parent) 'outputs\Marswalk_backup_60s.avi'
[MarswalkVideo.Maker]::Make($outputPath)
Get-Item -LiteralPath $outputPath | Select-Object FullName,Length
