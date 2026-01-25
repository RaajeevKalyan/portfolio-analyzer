# Docker Setup - Portfolio Risk Analyzer

## Container Architecture

**IMPORTANT**: This setup uses **2 Docker containers** (not 3). SQLite is NOT a container - it's a database file accessed via volume mount.

### Services Overview
```
┌──────────────────────────────────────────────────────┐
│                  Docker Compose                       │
│                    (2 Containers)                     │
│                                                       │
│  ┌────────────────┐         ┌──────────────────┐    │
│  │  CONTAINER 1   │────────▶│  CONTAINER 2     │    │
│  │  nginx         │  proxy  │  Flask App       │    │
│  │  (Port 443)    │         │  (Gunicorn)      │    │
│  │                │         │  Port 5000       │    │
│  └────────────────┘         └─────────┬────────┘    │
│         │                             │              │
│         │                             │ File I/O     │
│         ▼                             ▼              │
│  ┌────────────────┐         ┌──────────────────┐    │
│  │  /ssl volume   │         │  NOT A CONTAINER │    │
│  │  cert.pem      │         │  SQLite File     │    │
│  │  key.pem       │         │  portfolio.db    │    │
│  └────────────────┘         └──────────────────┘    │
│                                                       │
│  Volume Mounts (Host → Container):                   │
│  • ./data/portfolio.db → /app/data/portfolio.db     │
│  • ./nginx/ssl/*.pem   → /etc/nginx/ssl/*.pem       │
│  • ./logs/             → /app/logs/                  │
└──────────────────────────────────────────────────────┘
```

### Why Only 2 Containers?

**SQLite is NOT a database server** - it's just a file (`portfolio.db`) that the Flask app reads/writes directly:
- ✅ No separate database container needed
- ✅ Simpler architecture (fewer moving parts)
- ✅ Perfect for single-user applications
- ✅ Easy backups (just copy the `.db` file)
- ✅ No network overhead between app and database

**If you used PostgreSQL or MongoDB**, you'd have 3 containers:
```
Container 1: nginx (reverse proxy)
Container 2: Flask app
Container 3: postgres/mongodb (database server)
```

But with SQLite, the database is just a file accessed via volume mount.

## File Structure

```
portfolio-analyzer/
├── docker-compose.yml
├── Dockerfile (Flask app)
├── .env.example
├── .env (gitignored)
├── .dockerignore
├── requirements.txt
├── nginx/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── ssl/
│       ├── generate_cert.sh
│       ├── cert.pem (generated, gitignored)
│       └── key.pem (generated, gitignored)
├── data/ (gitignored, volume mount)
│   └── portfolio.db
├── logs/ (gitignored, volume mount)
│   └── app.log
└── app/
    ├── (application code)
```

## Docker Compose Configuration

**Note**: This configuration defines **2 services/containers** (nginx + app). There is no database container because SQLite is file-based.

### docker-compose.yml
```yaml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: portfolio-app
    restart: unless-stopped
    environment:
      - FLASK_ENV=production
      - PYTHONUNBUFFERED=1
    env_file:
      - .env
    volumes:
      - ./data:/app/data:rw
      - ./logs:/app/logs:rw
    networks:
      - portfolio-network
    expose:
      - "5000"
    command: gunicorn --bind 0.0.0.0:5000 --workers 3 --timeout 120 --access-logfile /app/logs/access.log --error-logfile /app/logs/error.log app.main:app
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  nginx:
    build:
      context: ./nginx
      dockerfile: Dockerfile
    container_name: portfolio-nginx
    restart: unless-stopped
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - ./logs:/var/log/nginx:rw
    networks:
      - portfolio-network
    depends_on:
      - app
    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  portfolio-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/24

# No volume definitions needed - using bind mounts
# SQLite database is just a file in ./data/portfolio.db (not a container)
```

### Service Breakdown

#### Service 1: `app` (Flask Application)
- **Container Name**: `portfolio-app`
- **Purpose**: Web application, business logic, API endpoints
- **Port**: 5000 (internal only, not exposed to host)
- **Volumes**: 
  - `./data:/app/data` - SQLite database file location
  - `./logs:/app/logs` - Application logs
- **Network**: `portfolio-network` (internal Docker network)

#### Service 2: `nginx` (Reverse Proxy)
- **Container Name**: `portfolio-nginx`
- **Purpose**: HTTPS termination, reverse proxy, security hardening
- **Ports**: 
  - `443:443` - HTTPS (exposed to host)
  - `80:80` - HTTP redirect only (exposed to host)
- **Volumes**:
  - `./nginx/ssl:/etc/nginx/ssl` - SSL certificates
  - `./logs:/var/log/nginx` - nginx access/error logs
- **Network**: `portfolio-network` (communicates with app container)

#### NOT a Service: SQLite Database
- **What it is**: A single file `portfolio.db` on the host
- **Location**: `./data/portfolio.db` (host) → `/app/data/portfolio.db` (in app container)
- **Accessed by**: Flask app via Python SQLite library (no network connection)
- **Why not a container**: SQLite is embedded, file-based database (not client-server)

### Container Communication

```
Browser (localhost:443)
    ↓ HTTPS
nginx container (:443)
    ↓ HTTP (internal network)
app container (:5000)
    ↓ File I/O (volume mount)
portfolio.db (host filesystem)
```

## Migration to PostgreSQL (If Needed Later)

If you need multi-user support, you'd add a 3rd container:

```yaml
services:
  app:
    depends_on:
      - postgres
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/portfolio
  
  nginx:
    # ... same as current
  
  postgres:  # NEW: 3rd container
    image: postgres:15-alpine
    container_name: portfolio-db
    environment:
      POSTGRES_DB: portfolio
      POSTGRES_USER: portfolio_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - portfolio-network

volumes:
  postgres_data:  # Managed Docker volume
```

But for single-user, SQLite file is simpler and sufficient.

## Application Dockerfile

### Dockerfile
```dockerfile
# Multi-stage build for smaller final image
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=appuser:appuser ./app /app/app
COPY --chown=appuser:appuser ./scripts /app/scripts

# Set permissions
RUN chmod 700 /app/data && \
    chmod 755 /app/logs

# Switch to non-root user
USER appuser

# Expose port (internal to Docker network)
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Default command (overridden in docker-compose.yml)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "app.main:app"]
```

### .dockerignore
```
# Version control
.git
.gitignore
.gitattributes

# Python
__pycache__
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
.venv

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# Data and logs
data/
logs/
*.db
*.log

# Environment
.env
.env.local

# SSL certificates
nginx/ssl/*.pem

# Documentation
README.md
docs/
*.md

# Tests
tests/
.pytest_cache/
.coverage
htmlcov/

# OS
.DS_Store
Thumbs.db

# Build artifacts
build/
dist/
*.egg-info/
```

## nginx Dockerfile

### nginx/Dockerfile
```dockerfile
FROM nginx:1.25-alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Create SSL directory
RUN mkdir -p /etc/nginx/ssl && \
    chmod 700 /etc/nginx/ssl

# Create nginx user if not exists
RUN addgroup -g 101 -S nginx || true && \
    adduser -S -D -H -u 101 -h /var/cache/nginx -s /sbin/nologin -G nginx -g nginx nginx || true

# Expose ports
EXPOSE 80 443

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
    CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
```

### nginx/nginx.conf
```nginx
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';
    access_log /var/log/nginx/access.log main;

    # Performance
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Security
    server_tokens off;
    client_max_body_size 10M;
    client_body_buffer_size 128k;
    client_header_buffer_size 1k;
    large_client_header_buffers 4 8k;

    # Timeouts
    client_body_timeout 12;
    client_header_timeout 12;
    send_timeout 10;

    # Gzip
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript 
               application/json application/javascript application/xml+rss;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=5r/m;

    # Upstream
    upstream flask_app {
        server app:5000;
        keepalive 32;
    }

    # HTTPS Server
    server {
        listen 443 ssl http2;
        server_name localhost;

        # SSL Configuration
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;

        # SSL Protocols and Ciphers (A+ Rating)
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
        ssl_prefer_server_ciphers off;

        # SSL Session
        ssl_session_timeout 1d;
        ssl_session_cache shared:SSL:50m;
        ssl_session_tickets off;

        # HSTS (31536000 seconds = 1 year)
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

        # Security Headers
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'self';" always;
        add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

        # Root location
        location / {
            limit_req zone=general burst=20 nodelay;
            
            proxy_pass http://flask_app;
            proxy_http_version 1.1;
            
            # Proxy headers
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-Host $host;
            proxy_set_header X-Forwarded-Port $server_port;
            
            # WebSocket support (if needed in future)
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            
            # Timeouts
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
            
            # Buffering
            proxy_buffering on;
            proxy_buffer_size 4k;
            proxy_buffers 8 4k;
            proxy_busy_buffers_size 8k;
        }

        # OAuth callbacks (stricter rate limiting)
        location ~ ^/oauth/callback/ {
            limit_req zone=auth burst=3 nodelay;
            
            proxy_pass http://flask_app;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Static files
        location /static/ {
            expires 1y;
            add_header Cache-Control "public, immutable";
            proxy_pass http://flask_app;
        }

        # Health check endpoint (no rate limit)
        location /health {
            access_log off;
            proxy_pass http://flask_app;
        }

        # Deny access to hidden files
        location ~ /\. {
            deny all;
            access_log off;
            log_not_found off;
        }
    }

    # HTTP to HTTPS redirect
    server {
        listen 80;
        server_name localhost;
        
        # ACME challenge (if using Let's Encrypt)
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
        
        # Redirect all other traffic to HTTPS
        location / {
            return 301 https://$host$request_uri;
        }
    }
}
```

## SSL Certificate Setup

### nginx/ssl/generate_cert.sh
```bash
#!/bin/bash

# Script to generate self-signed SSL certificate for localhost

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Generating self-signed SSL certificate for localhost..."

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
```

## Environment Configuration

### .env.example
```bash
# Flask Configuration
FLASK_ENV=production
SECRET_KEY=change-this-to-a-random-secret-key

# Database
DATABASE_URL=sqlite:///data/portfolio.db

# Encryption
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=change-this-to-a-fernet-key

# Logging
LOG_LEVEL=INFO

# Broker API Credentials (obtain from broker developer portals)
# Schwab
SCHWAB_CLIENT_ID=your-schwab-client-id
SCHWAB_CLIENT_SECRET=your-schwab-client-secret

# Robinhood
ROBINHOOD_CLIENT_ID=your-robinhood-client-id
ROBINHOOD_CLIENT_SECRET=your-robinhood-client-secret

# Merrill Lynch
MERRILL_CLIENT_ID=your-merrill-client-id
MERRILL_CLIENT_SECRET=your-merrill-client-secret

# Fidelity
FIDELITY_CLIENT_ID=your-fidelity-client-id
FIDELITY_CLIENT_SECRET=your-fidelity-client-secret
```

## Build and Deployment

### Initial Setup
```bash
#!/bin/bash
# setup.sh - Initial setup script

set -e

echo "🚀 Setting up Portfolio Risk Analyzer..."

# Create directories
mkdir -p data logs nginx/ssl

# Generate .env if not exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your credentials!"
fi

# Generate SSL certificates
echo "🔐 Generating SSL certificates..."
cd nginx/ssl
chmod +x generate_cert.sh
./generate_cert.sh
cd ../..

# Build Docker images
echo "🐳 Building Docker images..."
docker-compose build

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your broker credentials"
echo "  2. Start services: docker-compose up -d"
echo "  3. Access app: https://localhost"
echo "  4. View logs: docker-compose logs -f"
```

### Start Services
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f app
docker-compose logs -f nginx

# Check service status
docker-compose ps
```

### Stop Services
```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes database!)
docker-compose down -v

# Stop and remove images
docker-compose down --rmi all
```

### Update Application
```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose build app
docker-compose up -d app

# Or rebuild everything
docker-compose build
docker-compose up -d
```

## Backup and Restore

### Backup Script
```bash
#!/bin/bash
# backup.sh - Backup database and SSL certificates

BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "📦 Creating backup..."

# Backup database
cp data/portfolio.db "$BACKUP_DIR/"

# Backup SSL certificates
cp nginx/ssl/cert.pem "$BACKUP_DIR/"
cp nginx/ssl/key.pem "$BACKUP_DIR/"

# Backup .env (be careful with this!)
cp .env "$BACKUP_DIR/"

# Create tarball
tar -czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"
rm -rf "$BACKUP_DIR"

echo "✅ Backup created: $BACKUP_DIR.tar.gz"
```

### Restore Script
```bash
#!/bin/bash
# restore.sh - Restore from backup

if [ -z "$1" ]; then
    echo "Usage: ./restore.sh <backup-file.tar.gz>"
    exit 1
fi

BACKUP_FILE="$1"

echo "⚠️  This will overwrite existing data!"
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Stop services
docker-compose down

# Extract backup
TEMP_DIR=$(mktemp -d)
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"
BACKUP_CONTENTS=$(ls "$TEMP_DIR")

# Restore files
cp "$TEMP_DIR/$BACKUP_CONTENTS/portfolio.db" data/
cp "$TEMP_DIR/$BACKUP_CONTENTS/cert.pem" nginx/ssl/
cp "$TEMP_DIR/$BACKUP_CONTENTS/key.pem" nginx/ssl/
cp "$TEMP_DIR/$BACKUP_CONTENTS/.env" .

# Clean up
rm -rf "$TEMP_DIR"

# Start services
docker-compose up -d

echo "✅ Restore complete!"
```

## Monitoring and Logs

### Log Locations
```
./logs/
├── app.log          # Application logs
├── access.log       # Gunicorn access logs
├── error.log        # Gunicorn error logs
└── nginx/
    ├── access.log   # nginx access logs
    └── error.log    # nginx error logs
```

### Log Rotation
```bash
# logrotate.conf
/path/to/portfolio-analyzer/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 appuser appuser
    sharedscripts
    postrotate
        docker-compose exec app kill -USR1 $(cat /var/run/gunicorn.pid)
    endscript
}
```

### Health Checks
```bash
# Check application health
curl -k https://localhost/health

# Check nginx configuration
docker-compose exec nginx nginx -t

# Check SSL certificate
openssl s_client -connect localhost:443 -servername localhost < /dev/null
```

## Troubleshooting

### Common Issues

**1. Port 443 already in use**
```bash
# Find process using port 443
sudo lsof -i :443

# Stop the process or change port in docker-compose.yml
ports:
  - "8443:443"  # Use different external port
```

**2. SSL certificate not trusted**
- Expected behavior for self-signed certificates
- Click "Advanced" → "Proceed to localhost"
- Or import certificate into system trust store

**3. Database locked errors**
```bash
# Check if database file is accessible
ls -la data/portfolio.db

# Ensure no other processes are using it
docker-compose down
docker-compose up -d
```

**4. Permission errors**
```bash
# Fix data directory permissions
sudo chown -R 1000:1000 data/
sudo chmod 700 data/
```

**5. Can't connect to Flask app**
```bash
# Check if app is running
docker-compose ps

# View app logs
docker-compose logs app

# Restart app
docker-compose restart app
```

## Security Hardening

### Production Checklist
- [ ] Change all default secrets in .env
- [ ] Use strong encryption key (32 bytes)
- [ ] Restrict database file permissions (600)
- [ ] Enable firewall rules (allow only 443)
- [ ] Set up automated backups
- [ ] Configure log rotation
- [ ] Test SSL configuration (SSL Labs)
- [ ] Review and test all OAuth flows
- [ ] Set up monitoring/alerting
- [ ] Document disaster recovery plan