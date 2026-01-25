# Quick Start Guide - Phase 1

## 🎯 Goal
Get "Hello World" running at `https://localhost:8443`

## 📦 What You're Installing
- 2 Docker containers (nginx + Flask)
- HTTPS-only access
- Self-signed SSL certificate
- Security-hardened nginx

---

## ⚡ 5-Minute Setup

### Step 1: Create Directory
```bash
mkdir portfolio-analyzer
cd portfolio-analyzer
```

### Step 2: Create ALL 14 Files

Copy content from artifacts to create these files:

**Root (8 files):**
1. `docker-compose.yml`
2. `Dockerfile`
3. `requirements.txt`
4. `.env.example`
5. `.gitignore`
6. `.dockerignore`
7. `setup.sh`
8. `PHASE1_SETUP.md`

**nginx/ (2 files):**
9. `nginx/Dockerfile`
10. `nginx/nginx.conf`

**nginx/ssl/ (1 file):**
11. `nginx/ssl/generate_cert.sh`

**app/ (3 files):**
12. `app/__init__.py`
13. `app/main.py`
14. `app/config.py`

### Step 3: Run Setup
```bash
chmod +x setup.sh
./setup.sh
```

### Step 4: Start Services
```bash
docker-compose up -d
```

### Step 5: Access App
Open browser: `https://localhost:8443`
- Click "Advanced" on SSL warning
- Click "Proceed to localhost"

---

## ✅ Success = You See This

**Welcome Page with:**
- Purple gradient background
- White card with "Portfolio Risk Analyzer" title
- 5 colored broker icons (red, green, purple, green, blue)
- "Application running successfully!" message

---

## 🧪 Quick Tests

```bash
# All containers running?
docker-compose ps

# Health check working?
curl -k https://localhost:8443/health

# Any errors?
docker-compose logs | grep -i error
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Port 8443 in use | Change to `9443:443` in docker-compose.yml |
| Permission denied | `sudo chown -R $USER:$USER .` |
| Can't connect | `docker-compose restart app` |
| SSL warning | Normal! Click "Advanced" → "Proceed" |

---

## 📞 Need Help?

See `PHASE1_SETUP.md` for detailed instructions and troubleshooting.

Use `FILE_CHECKLIST.md` to verify you created all files correctly.

---

## ⏭️ Next Steps

Once Phase 1 works, we'll add:
- **Phase 2:** Database models (SQLAlchemy)
- **Phase 3:** CSV upload for Merrill Lynch
- **Phase 4:** Risk analysis and charts