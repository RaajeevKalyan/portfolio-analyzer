# Distribution Guide - Portfolio Risk Analyzer

This guide explains how to create distributable Docker images for both x86_64 (Intel/AMD) and ARM64 (Apple Silicon M1/M2/M3) architectures.

---

## 📦 Strategy 1: Docker Image Export (Multi-Architecture)

This method creates standalone `.tar.gz` files containing Docker images that users can install without internet access.

### Prerequisites

- Docker Desktop installed with BuildKit enabled
- Sufficient disk space (~2GB for images)
- Clean working directory (all data removed)

---

## 🧹 Step 1: Clean Your Environment

Before creating distribution, remove ALL user data and generated files:

```bash
# Stop and remove containers
docker-compose down

# Remove user data
rm -rf data/
rm -rf logs/
rm -rf backups/
rm -rf app/uploads/

# Remove SSL certificates (users will generate their own)
rm -f nginx/ssl/*.pem

# Remove .env file (users will create from .env.example)
rm -f .env

# Verify clean state
git status

# Should show no untracked files in data/, logs/, nginx/ssl/, etc.
```

---

## 🏗️ Step 2: Build Multi-Architecture Images

### Option A: Build Separate Images for Each Platform

**For x86_64 (Intel/AMD):**
```bash
# Build app image for x86_64
docker buildx build --platform linux/amd64 \
  -t portfolio-analyzer-app:v1.0-amd64 \
  --load \
  -f Dockerfile .

# Build nginx image for x86_64
docker buildx build --platform linux/amd64 \
  -t portfolio-analyzer-nginx:v1.0-amd64 \
  --load \
  -f nginx/Dockerfile nginx/
```

**For ARM64 (Apple Silicon):**
```bash
# Build app image for ARM64
docker buildx build --platform linux/arm64 \
  -t portfolio-analyzer-app:v1.0-arm64 \
  --load \
  -f Dockerfile .

# Build nginx image for ARM64
docker buildx build --platform linux/arm64 \
  -t portfolio-analyzer-nginx:v1.0-arm64 \
  --load \
  -f nginx/Dockerfile nginx/
```

### Option B: Build Multi-Platform Images (Advanced)

**Create buildx builder:**
```bash
# One-time setup
docker buildx create --name multiplatform --use
docker buildx inspect --bootstrap
```

**Build for both platforms:**
```bash
# Build app for both platforms
docker buildx build --platform linux/amd64,linux/arm64 \
  -t portfolio-analyzer-app:v1.0 \
  --load \
  -f Dockerfile .

# Build nginx for both platforms
docker buildx build --platform linux/amd64,linux/arm64 \
  -t portfolio-analyzer-nginx:v1.0 \
  --load \
  -f nginx/Dockerfile nginx/
```

**Note:** Multi-platform `--load` may not work on all systems. If it fails, use Option A (separate builds).

---

## 💾 Step 3: Export Images to Files

### For Separate Platform Images:

**x86_64 (Intel/AMD):**
```bash
# Export app image
docker save portfolio-analyzer-app:v1.0-amd64 -o portfolio-app-v1.0-amd64.tar

# Export nginx image
docker save portfolio-analyzer-nginx:v1.0-amd64 -o portfolio-nginx-v1.0-amd64.tar

# Compress
gzip portfolio-app-v1.0-amd64.tar
gzip portfolio-nginx-v1.0-amd64.tar
```

**ARM64 (Apple Silicon):**
```bash
# Export app image
docker save portfolio-analyzer-app:v1.0-arm64 -o portfolio-app-v1.0-arm64.tar

# Export nginx image
docker save portfolio-analyzer-nginx:v1.0-arm64 -o portfolio-nginx-v1.0-arm64.tar

# Compress
gzip portfolio-app-v1.0-arm64.tar
gzip portfolio-nginx-v1.0-arm64.tar
```

### For Multi-Platform Images:

```bash
# Export multi-platform app image
docker save portfolio-analyzer-app:v1.0 -o portfolio-app-v1.0-multiarch.tar

# Export multi-platform nginx image
docker save portfolio-analyzer-nginx:v1.0 -o portfolio-nginx-v1.0-multiarch.tar

# Compress
gzip portfolio-app-v1.0-multiarch.tar
gzip portfolio-nginx-v1.0-multiarch.tar
```

---

## 📁 Step 4: Create Distribution Package

### Directory Structure:

```bash
# Create distribution directory
mkdir -p portfolio-analyzer-distribution
cd portfolio-analyzer-distribution

# Copy core files
cp ../docker-compose.yml .
cp ../.env.example .
cp ../setup.sh .
cp ../requirements.txt .
cp ../Dockerfile .

# Copy nginx files
mkdir -p nginx/ssl
cp ../nginx/Dockerfile nginx/
cp ../nginx/nginx.conf nginx/
cp ../nginx/ssl/generate_cert.sh nginx/ssl/

# Copy documentation
cp ../README.md .
cp ../QUICKSTART.md .
cp ../PHASE1_SETUP.md .
cp ../FILE_CHECKLIST.md .

# Copy app code (after Phase 2+, you'll have more files)
mkdir -p app
cp ../app/__init__.py app/
cp ../app/main.py app/
cp ../app/config.py app/
# Add more app files as you build them

# Copy scripts
mkdir -p scripts
# cp ../scripts/*.py scripts/  (after Phase 2+)
```

### Copy Docker Images:

**For separate platform builds:**
```bash
# Copy x86_64 images
cp ../portfolio-app-v1.0-amd64.tar.gz .
cp ../portfolio-nginx-v1.0-amd64.tar.gz .

# Copy ARM64 images
cp ../portfolio-app-v1.0-arm64.tar.gz .
cp ../portfolio-nginx-v1.0-arm64.tar.gz .
```

**For multi-platform builds:**
```bash
# Copy multi-arch images
cp ../portfolio-app-v1.0-multiarch.tar.gz .
cp ../portfolio-nginx-v1.0-multiarch.tar.gz .
```

---

## 🚀 Step 5: Create Installation Script

Create `install.sh` in the distribution directory:

**For Separate Platform Builds:**

```bash
#!/bin/bash
# Portfolio Risk Analyzer - Installation Script
# Supports x86_64 (Intel/AMD) and ARM64 (Apple Silicon)

set -e

echo "🚀 Installing Portfolio Risk Analyzer v1.0"
echo ""

# Detect architecture
ARCH=$(uname -m)

if [ "$ARCH" = "x86_64" ]; then
    echo "📦 Detected x86_64 (Intel/AMD) architecture"
    APP_IMAGE="portfolio-app-v1.0-amd64.tar.gz"
    NGINX_IMAGE="portfolio-nginx-v1.0-amd64.tar.gz"
elif [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
    echo "📦 Detected ARM64 (Apple Silicon) architecture"
    APP_IMAGE="portfolio-app-v1.0-arm64.tar.gz"
    NGINX_IMAGE="portfolio-nginx-v1.0-arm64.tar.gz"
else
    echo "❌ Unsupported architecture: $ARCH"
    echo "Supported: x86_64, arm64"
    exit 1
fi

# Verify Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker Desktop first."
    echo "   Download from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Verify Docker is running
if ! docker info &> /dev/null; then
    echo "❌ Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Load Docker images
echo ""
echo "📦 Loading Docker images (this may take a few minutes)..."

if [ ! -f "$APP_IMAGE" ]; then
    echo "❌ Missing image file: $APP_IMAGE"
    exit 1
fi

if [ ! -f "$NGINX_IMAGE" ]; then
    echo "❌ Missing image file: $NGINX_IMAGE"
    exit 1
fi

echo "Loading app image..."
gunzip -c "$APP_IMAGE" | docker load

echo "Loading nginx image..."
gunzip -c "$NGINX_IMAGE" | docker load

# Tag images as 'latest' for docker-compose
echo ""
echo "🏷️  Tagging images..."
docker tag portfolio-analyzer-app:v1.0-${ARCH/x86_64/amd64} portfolio-analyzer-app:latest
docker tag portfolio-analyzer-nginx:v1.0-${ARCH/x86_64/amd64} portfolio-analyzer-nginx:latest

# Run setup script
echo ""
echo "🔧 Running setup..."
chmod +x setup.sh
./setup.sh

echo ""
echo "✅ Installation complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Next steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Start the application:"
echo "   docker-compose up -d"
echo ""
echo "2. Access the application:"
echo "   https://localhost:8443"
echo "   (Accept the self-signed certificate warning)"
echo ""
echo "3. View logs:"
echo "   docker-compose logs -f"
echo ""
echo "4. Stop the application:"
echo "   docker-compose down"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

**For Multi-Platform Builds:**

```bash
#!/bin/bash
# Portfolio Risk Analyzer - Installation Script
# Multi-architecture support (auto-detects platform)

set -e

echo "🚀 Installing Portfolio Risk Analyzer v1.0"
echo ""

# Verify Docker is installed and running
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker Desktop first."
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "❌ Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Load multi-platform Docker images
echo "📦 Loading Docker images (this may take a few minutes)..."

gunzip -c portfolio-app-v1.0-multiarch.tar.gz | docker load
gunzip -c portfolio-nginx-v1.0-multiarch.tar.gz | docker load

# Tag as latest
docker tag portfolio-analyzer-app:v1.0 portfolio-analyzer-app:latest
docker tag portfolio-analyzer-nginx:v1.0 portfolio-analyzer-nginx:latest

# Run setup
echo ""
echo "🔧 Running setup..."
chmod +x setup.sh
./setup.sh

echo ""
echo "✅ Installation complete!"
echo ""
echo "Start with: docker-compose up -d"
echo "Access at: https://localhost:8443"
```

Make it executable:
```bash
chmod +x install.sh
```

---

## 📦 Step 6: Create Final Distribution Archive

```bash
cd ..  # Go back to parent directory

# Create tarball of entire distribution
tar -czf portfolio-analyzer-v1.0-distribution.tar.gz portfolio-analyzer-distribution/

# Check file size
ls -lh portfolio-analyzer-v1.0-distribution.tar.gz
# Expected: ~400-800MB depending on platform builds
```

---

## 📤 Step 7: Distribution Options

### Option A: GitHub Releases

1. Go to your GitHub repository
2. Click "Releases" → "Create a new release"
3. Tag: `v1.0.0`
4. Title: `Portfolio Risk Analyzer v1.0.0`
5. Upload `portfolio-analyzer-v1.0-distribution.tar.gz`
6. Publish release

Users download and extract:
```bash
wget https://github.com/yourusername/portfolio-analyzer/releases/download/v1.0.0/portfolio-analyzer-v1.0-distribution.tar.gz
tar -xzf portfolio-analyzer-v1.0-distribution.tar.gz
cd portfolio-analyzer-distribution
./install.sh
```

### Option B: Direct File Sharing

Share the `.tar.gz` file via:
- Cloud storage (Google Drive, Dropbox, etc.)
- USB drive
- Network share

---

## 👥 User Installation Instructions

**Provide users with these steps:**

### Prerequisites:
- Docker Desktop installed and running
- ~2GB free disk space
- macOS, Linux, or Windows with WSL2

### Installation:

```bash
# 1. Extract distribution
tar -xzf portfolio-analyzer-v1.0-distribution.tar.gz
cd portfolio-analyzer-distribution

# 2. Run installer (auto-detects architecture)
chmod +x install.sh
./install.sh

# 3. Start application
docker-compose up -d

# 4. Access application
# Open browser to: https://localhost:8443
# Click "Advanced" → "Proceed to localhost"

# 5. Stop application (when done)
docker-compose down
```

---

## 🔄 Updating to New Version

When you release v2.0:

```bash
# Clean environment
docker-compose down
rm -rf data/ logs/ nginx/ssl/*.pem .env

# Build new images
docker buildx build --platform linux/amd64,linux/arm64 \
  -t portfolio-analyzer-app:v2.0 \
  --load .

# Export
docker save portfolio-analyzer-app:v2.0 -o portfolio-app-v2.0.tar
gzip portfolio-app-v2.0.tar

# Create new distribution with version number
# ... repeat steps above
```

Users upgrade by:
```bash
docker-compose down
# Extract new version
./install.sh  # Loads new images
docker-compose up -d
```

---

## 📊 Distribution File Sizes (Approximate)

| File | Size (Compressed) | Architecture |
|------|------------------|--------------|
| portfolio-app-v1.0-amd64.tar.gz | ~300MB | x86_64 |
| portfolio-nginx-v1.0-amd64.tar.gz | ~50MB | x86_64 |
| portfolio-app-v1.0-arm64.tar.gz | ~280MB | ARM64 |
| portfolio-nginx-v1.0-arm64.tar.gz | ~45MB | ARM64 |
| **Full Distribution (both platforms)** | **~700MB** | Both |
| **Full Distribution (multi-arch)** | **~400MB** | Both |

---

## 🔐 Security Checklist Before Distribution

- [ ] All user data removed (`data/`, `logs/`)
- [ ] No `.env` file included (only `.env.example`)
- [ ] No SSL certificates included (`nginx/ssl/*.pem`)
- [ ] No uploaded CSV files (`app/uploads/`)
- [ ] `.gitignore` properly configured
- [ ] `setup.sh` generates random `SECRET_KEY`
- [ ] Installation script validates Docker installation
- [ ] Documentation includes security best practices

---

## 🐛 Troubleshooting

### Build fails with "no matching manifest"
**Solution:** Your system doesn't support the target platform. Build on the target platform or use Docker Buildx with QEMU:
```bash
docker run --privileged --rm tonistiigi/binfmt --install all
```

### Image load fails
**Solution:** Ensure Docker has enough disk space (2GB+):
```bash
docker system df  # Check disk usage
docker system prune  # Clean up
```

### "Architecture mismatch" error
**Solution:** User is loading wrong architecture image. Ensure `install.sh` detects architecture correctly or provide separate installers.

---

## 📝 Notes

- Images are **platform-specific** or **multi-platform** (fatter but convenient)
- Compressed images are ~60% smaller than uncompressed
- Multi-platform builds require Docker Buildx
- Users need **no internet connection** after downloading distribution
- First startup takes ~30s while containers initialize
- Database is created automatically on first run

---

## 🎯 Quick Reference Commands

```bash
# Build multi-platform
docker buildx build --platform linux/amd64,linux/arm64 -t IMAGE:TAG --load .

# Export image
docker save IMAGE:TAG -o file.tar && gzip file.tar

# Load image (for testing)
gunzip -c file.tar.gz | docker load

# Check image architecture
docker inspect IMAGE:TAG | grep Architecture

# Test on different platform (using QEMU)
docker run --platform linux/arm64 IMAGE:TAG
```