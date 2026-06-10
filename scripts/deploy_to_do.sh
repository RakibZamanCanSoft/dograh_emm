#!/bin/bash

# Ensure we have arguments
if [ -z "$1" ]; then
    echo "Usage: ./scripts/deploy_to_do.sh <username@droplet-ip> [path/to/ssh/key]"
    echo "Example: ./scripts/deploy_to_do.sh root@192.168.1.10 ~/.ssh/id_rsa"
    exit 1
fi

TARGET=$1
KEY_ARGS=""
if [ -n "$2" ]; then
    KEY_ARGS="-i $2"
fi

echo "📦 Archiving local files (excluding local configs, databases, and node_modules)..."
tar -czf deploy_archive.tar.gz \
    --exclude='venv' \
    --exclude='node_modules' \
    --exclude='.env' \
    --exclude='ui/.env' \
    --exclude='api/.env' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='.next' \
    --exclude='postgres_data' \
    --exclude='redis_data' \
    --exclude='minio-data' \
    --exclude='docker-compose-local.yaml' \
    --exclude='.gemini' \
    --exclude='.agent' \
    .

echo "🚀 Transferring archive to $TARGET..."
scp $KEY_ARGS deploy_archive.tar.gz $TARGET:~/dograh_deploy.tar.gz

echo "⚙️ Extracting and building on remote server..."
ssh $KEY_ARGS $TARGET << 'EOF'
    mkdir -p ~/dograh
    tar -xzf ~/dograh_deploy.tar.gz -C ~/dograh
    rm ~/dograh_deploy.tar.gz
    cd ~/dograh
    
    # Check if this is a first-time build deployment
    if [ ! -f "docker-compose.override.yaml" ]; then
        echo "⚠️  First time deployment detected! Generating docker-compose.override.yaml for build mode..."
        cat > docker-compose.override.yaml << 'OVERRIDE'
services:
  api:
    image: dograh-api:local
    build:
      context: .
      dockerfile: api/Dockerfile
  ui:
    image: dograh-ui:local
    build:
      context: .
      dockerfile: ui/Dockerfile
OVERRIDE
    fi

    # Remind the user if they haven't set up the remote server credentials yet
    if [ ! -f ".env" ]; then
        echo "⚠️  No .env file found on the server."
        echo "⚠️  Please log into the droplet and run: cd ~/dograh && ./scripts/setup_remote.sh"
        echo "⚠️  This is required to generate the production SSL certificates and secrets!"
    else
        echo "🔨 Building Docker images from source and restarting..."
        # Rebuild the API and UI images from the fresh source code we just transferred
        docker compose --profile remote up -d --build
        echo "✅ Server successfully updated and restarted!"
    fi
EOF

echo "🧹 Cleaning up local archive..."
rm deploy_archive.tar.gz

echo "✅ Deployment push completed!"
