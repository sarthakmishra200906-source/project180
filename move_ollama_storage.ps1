# move_ollama_storage.ps1
# Run this script as Administrator in PowerShell to relocate Ollama models to D: drive

$oldPath = "$env:USERPROFILE\.ollama\models"
$newPath = "D:\Ollama_Models"

Write-Output "Stopping Ollama processes to release file locks..."
Stop-Process -Name "Ollama" -ErrorAction SilentlyContinue
Stop-Process -Name "ollama" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

if (!(Test-Path $newPath)) {
    New-Item -ItemType Directory -Force -Path $newPath | Out-Null
    Write-Output "Created new storage directory at $newPath"
}

if (Test-Path $oldPath) {
    $item = Get-Item $oldPath -ErrorAction SilentlyContinue
    if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Write-Output "Ollama models directory is already a reparse point (symlink/junction). Skipping move."
        exit
    }

    Write-Output "Copying existing models to D: drive (may take a long time)..."
    Copy-Item -Path "$oldPath\*" -Destination $newPath -Recurse -Force

    Write-Output "Removing old models directory from C: drive..."
    Remove-Item -Path $oldPath -Recurse -Force
}

Write-Output "Creating Directory Junction Link from $oldPath -> $newPath"
New-Item -ItemType Junction -Path $oldPath -Target $newPath

Write-Output "✅ SUCCESS! Ollama models now physically live on D: drive."
Write-Output "You can now restart the Ollama service or application."
