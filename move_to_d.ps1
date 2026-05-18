# Copy the project folder to D:\project_180 (Windows PowerShell)
$src = (Get-Location).Path
$dst = "D:\project_180"

if (!(Test-Path -Path $dst)) {
    New-Item -ItemType Directory -Path $dst -Force | Out-Null
}

Write-Output "Copying files from $src to $dst ..."
Copy-Item -Path "$src\*" -Destination $dst -Recurse -Force
Write-Output "Copy complete. Open D:\project_180 in VS Code to continue."