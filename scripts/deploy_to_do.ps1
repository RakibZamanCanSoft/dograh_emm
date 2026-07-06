param (
    [Parameter(Mandatory=$true)]
    [string]$Target,
    
    [Parameter(Mandatory=$false)]
    [string]$KeyPath
)

$ErrorActionPreference = "Stop"

$KeyArgs = @()
if ($KeyPath) {
    $KeyArgs += "-i", "$KeyPath"
}

Write-Host "[*] Archiving local files (excluding local configs, databases, and node_modules)..." -ForegroundColor Cyan

# Define exclusions for tar
$ExcludeList = @(
    "venv", "node_modules", ".env", "ui/.env", "api/.env", ".git", 
    "__pycache__", ".next", "postgres_data", "redis_data", "minio-data", 
    "docker-compose-local.yaml", ".gemini", ".agent", "deploy_archive.tar.gz", "deploy_remote.sh", "logs"
)

# Build the tar command
$TarArgs = @("-czf", "deploy_archive.tar.gz")
foreach ($Exclude in $ExcludeList) {
    $TarArgs += "--exclude=$Exclude"
}
$TarArgs += "."

# Run tar
& tar @TarArgs

Write-Host "[*] Creating remote execution script..." -ForegroundColor Cyan

$Lines = @(
    "mkdir -p ~/dograh",
    "tar -xzf ~/dograh_deploy.tar.gz -C ~/dograh",
    "rm ~/dograh_deploy.tar.gz",
    "cd ~/dograh",
    "if [ ! -f `"docker-compose.override.yaml`" ]; then",
    "    echo `"[*] First time deployment detected! Generating docker-compose.override.yaml...`"",
    "    cat > docker-compose.override.yaml << 'OVERRIDE'",
    "services:",
    "  api:",
    "    image: dograh-api:local",
    "    build:",
    "      context: .",
    "      dockerfile: api/Dockerfile",
    "  ui:",
    "    image: dograh-ui:local",
    "    build:",
    "      context: .",
    "      dockerfile: ui/Dockerfile",
    "OVERRIDE",
    "fi",
    "if [ ! -f `".env`" ]; then",
    "    echo `"[*] No .env file found on the server.`"",
    "    echo `"[*] Please log into the droplet and run: cd ~/dograh && ./scripts/setup_remote.sh`"",
    "else",
    "    echo `"[*] Building Docker images from source and restarting...`"",
    "    find scripts deploy -type f -name '*.sh' -o -name '*.template' | xargs sed -i 's/\r//g' 2>/dev/null || true",
    "    find scripts -type f -name '*.sh' -exec chmod +x {} + 2>/dev/null || true",
    "    docker compose --profile remote up -d --build",
    "    echo `"[*] Server successfully updated and restarted!`"",
    "fi"
)

Set-Content -Path "deploy_remote.sh" -Value $Lines -Encoding ASCII

Write-Host "[*] Transferring archive to $Target..." -ForegroundColor Cyan
& scp @KeyArgs deploy_archive.tar.gz "$($Target):~/dograh_deploy.tar.gz"
& scp @KeyArgs deploy_remote.sh "$($Target):~/deploy_remote.sh"

Write-Host "[*] Extracting and building on remote server..." -ForegroundColor Cyan
& ssh @KeyArgs $Target "sed -i 's/\r//g' ~/deploy_remote.sh && bash ~/deploy_remote.sh; rm ~/deploy_remote.sh"

Write-Host "[*] Cleaning up local files..." -ForegroundColor Cyan
Remove-Item deploy_archive.tar.gz
Remove-Item deploy_remote.sh

Write-Host "[*] Deployment push completed!" -ForegroundColor Green
