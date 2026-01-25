#!/bin/bash

# Script to generate self-signed SSL certificate for localhost

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔐 Generating self-signed SSL certificate for localhost..."

# Generate private key
openssl genrsa -out key.pem 2048

# Generate certificate signing request
openssl req -new -key key.pem -out cert.csr \
    -subj "/C=US/ST=State/L=City/O=Personal/CN=localhost"

# Generate self-signed certificate (valid for 1 year)
openssl x509 -req -days 365 -in cert.csr -signkey key.pem -out cert.pem \
    -extensions v3_ca -extfile <(cat <<EOF
[v3_ca]
subjectAltName = DNS:localhost,IP:127.0.0.1
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
EOF
)

# Clean up CSR
rm cert.csr

# Set permissions
chmod 600 key.pem
chmod 644 cert.pem

echo ""
echo "✅ SSL certificates generated successfully!"
echo "   Certificate: $SCRIPT_DIR/cert.pem"
echo "   Private Key: $SCRIPT_DIR/key.pem"
echo ""
echo "⚠️  Note: This is a self-signed certificate."
echo "   Your browser will show a security warning."
echo "   This is expected for local development."
echo ""
echo "To trust the certificate in your browser:"
echo "  1. Access https://localhost"
echo "  2. Click 'Advanced' on the security warning"
echo "  3. Click 'Proceed to localhost (unsafe)'"
echo ""
echo "For production, use Let's Encrypt or a commercial CA."