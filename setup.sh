#!/bin/bash

# Portfolio Risk Analyzer - Initial Setup Script

set -e

echo "🚀 Setting up Portfolio Risk Analyzer..."
echo ""

# Create directories
echo "📁 Creating directories..."
mkdir -p data logs nginx/ssl app/uploads scripts

# Generate .env if not exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    
    # Generate a random secret key
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    
    # Update .env with generated secret key
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s/change-this-to-a-random-secret-key-generate-with-secrets-token-hex/$SECRET_KEY/" .env
    else
        # Linux
        sed -i "s/change-this-to-a-random-secret-key-generate-with-secrets-token-hex/$SECRET_KEY/" .env
    fi
    
    echo "✅ .env file created with random SECRET_KEY"
else
    echo "ℹ️  .env file already exists, skipping..."
fi

# Generate SSL certificates
echo ""
echo "🔐 Generating SSL certificates..."
cd nginx/ssl

if [ ! -f cert.pem ] || [ ! -f key.pem ]; then
    chmod +x generate_cert.sh
    ./generate_cert.sh
else
    echo "ℹ️  SSL certificates already exist, skipping..."
fi

cd ../..

# Build Docker images
echo ""
echo "🐳 Building Docker images..."
docker-compose build

echo ""
echo "✅ Setup complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Next steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Start services:"
echo "   docker-compose up -d"
echo ""
echo "2. View logs:"
echo "   docker-compose logs -f"
echo ""
echo "3. Access application:"
echo "   https://localhost:8443"
echo "   (Accept the self-signed certificate warning)"
echo ""
echo "4. Stop services:"
echo "   docker-compose down"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"