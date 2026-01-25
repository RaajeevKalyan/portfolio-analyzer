# Security Specification - Portfolio Risk Analyzer

## Overview
This document outlines all security measures implemented to protect sensitive financial data, broker credentials, and ensure the application follows OWASP Top 10 best practices.

## Threat Model

### Assets to Protect
1. **OAuth Tokens**: Broker access/refresh tokens
2. **Portfolio Data**: Holdings, positions, account balances
3. **Personal Information**: Account numbers, transaction history
4. **Application Integrity**: Prevent unauthorized access/modifications

### Threat Actors
- **External Attackers**: Network-based attacks against localhost
- **Local Malware**: Processes running on same machine
- **Physical Access**: Someone with access to host machine
- **Insider (User)**: Accidental misconfiguration or data exposure

### Attack Vectors
- Man-in-the-middle attacks (TLS)
- SQL injection (database queries)
- XSS attacks (user inputs)
- CSRF attacks (form submissions)
- Credential theft (encrypted storage)
- Session hijacking (cookie security)
- Path traversal (file operations)
- OAuth redirect attacks

## OWASP Top 10 (2021) Mitigations

### A01:2021 – Broken Access Control
**Mitigations:**
- Single-user mode (no authorization bypass risk)
- Session management via Flask-Session
- CSRF tokens on all state-changing operations
- No direct object references in URLs (use session-based IDs)
- Server-side validation of all user inputs

**Implementation:**
```python
# CSRF protection
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)

# All forms include CSRF token
{{ csrf_token() }}

# API endpoints verify CSRF
@app.route('/api/refresh', methods=['POST'])
@csrf_protect
def refresh_portfolio():
    ...
```

### A02:2021 – Cryptographic Failures
**Mitigations:**
- TLS 1.2+ with strong cipher suites (nginx)
- Fernet symmetric encryption for OAuth tokens at rest
- No hardcoded secrets (environment variables)
- Secure random number generation for tokens
- HSTS headers to enforce HTTPS

**Implementation:**
```python
from cryptography.fernet import Fernet
import os

# Key generation (one-time, store in .env)
encryption_key = Fernet.generate_key()

# Encryption
cipher = Fernet(os.getenv('ENCRYPTION_KEY'))
encrypted_token = cipher.encrypt(access_token.encode())

# Decryption
decrypted_token = cipher.decrypt(encrypted_token).decode()
```

**nginx TLS Configuration:**
```nginx
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
ssl_prefer_server_ciphers on;
```

### A03:2021 – Injection
**Mitigations:**
- SQLAlchemy ORM (no raw SQL queries)
- Parameterized queries for all database operations
- Input validation and sanitization
- Context-aware output encoding
- No shell command execution with user input

**Implementation:**
```python
# Safe: SQLAlchemy ORM
holding = Holding.query.filter_by(symbol=symbol).first()

# Never do this:
# cursor.execute(f"SELECT * FROM holdings WHERE symbol = '{symbol}'")

# Input validation
from wtforms import StringField, validators

class BrokerForm(FlaskForm):
    broker_name = StringField('Broker', [
        validators.DataRequired(),
        validators.AnyOf(['schwab', 'robinhood', 'merrill', 'fidelity'])
    ])
```

### A04:2021 – Insecure Design
**Mitigations:**
- Secure OAuth flow implementation (PKCE where supported)
- Rate limiting on OAuth callbacks (prevent brute force)
- State parameter in OAuth to prevent CSRF
- No sensitive data in logs
- Fail-secure defaults (deny by default)

**Implementation:**
```python
# OAuth state parameter (CSRF protection)
import secrets
state = secrets.token_urlsafe(32)
session['oauth_state'] = state

# Verify on callback
if request.args.get('state') != session.get('oauth_state'):
    abort(400, 'Invalid state parameter')
```

### A05:2021 – Security Misconfiguration
**Mitigations:**
- Debug mode disabled in production
- Remove default credentials (N/A - no defaults)
- Disable directory listing (nginx)
- Remove unnecessary services/endpoints
- Secure headers (nginx + Flask)
- Regular dependency updates

**nginx Hardening:**
```nginx
# Disable server tokens
server_tokens off;

# Disable directory listing
autoindex off;

# Security headers
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

# Hide nginx version
more_clear_headers Server;
```

**Flask Configuration:**
```python
# Production config
class ProductionConfig:
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.getenv('SECRET_KEY')
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
```

### A06:2021 – Vulnerable and Outdated Components
**Mitigations:**
- Pin dependency versions in requirements.txt
- Regular security audits (`pip-audit`)
- Automated dependency updates (Dependabot)
- Use official, maintained libraries only
- Docker base image updates

**Implementation:**
```bash
# requirements.txt with version pins
Flask==3.0.0
SQLAlchemy==2.0.23
cryptography==41.0.7

# Regular audits
pip-audit

# Update dependencies
pip install --upgrade pip-tools
pip-compile --upgrade requirements.in
```

### A07:2021 – Identification and Authentication Failures
**Mitigations:**
- Secure session management (Flask-Session)
- Session timeout (2 hours default)
- Secure cookie attributes (httponly, secure, samesite)
- OAuth token refresh before expiration
- No password storage (OAuth only)

**Implementation:**
```python
# Session configuration
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# OAuth token refresh
def get_valid_token(broker_name):
    cred = BrokerCredential.query.filter_by(broker_name=broker_name).first()
    if cred.token_expires_at < datetime.utcnow() + timedelta(minutes=5):
        # Refresh token
        new_tokens = refresh_oauth_token(cred)
        cred.update_tokens(new_tokens)
    return cred.decrypted_access_token
```

### A08:2021 – Software and Data Integrity Failures
**Mitigations:**
- No CDN usage (all assets served locally)
- Integrity checks on file uploads (if added)
- Signed commits (development best practice)
- Docker image verification
- No auto-update mechanism (manual control)

**Implementation:**
```dockerfile
# Use official base images with digest
FROM python:3.11-slim@sha256:abc123...

# Verify checksums for downloads
RUN curl -O https://example.com/file.tar.gz \
    && echo "sha256sum file.tar.gz" | sha256sum -c -
```

### A09:2021 – Security Logging and Monitoring Failures
**Mitigations:**
- Comprehensive logging (errors, auth attempts, data changes)
- No sensitive data in logs (tokens, account numbers)
- Log rotation and retention
- Alerting on suspicious activity (optional)
- Centralized logging (Docker logs)

**Implementation:**
```python
import logging
from logging.handlers import RotatingFileHandler

# Configure logging
handler = RotatingFileHandler(
    'logs/app.log',
    maxBytes=10485760,  # 10MB
    backupCount=10
)
handler.setLevel(logging.INFO)

# Log security events
logger.info(f'OAuth callback received for {broker_name}')
logger.warning(f'Failed OAuth attempt: {error}')
logger.error(f'Database error: {exception}')

# Sanitize logs
def sanitize_log(data):
    # Remove tokens, account numbers, etc.
    if 'access_token' in data:
        data['access_token'] = '***REDACTED***'
    return data
```

### A10:2021 – Server-Side Request Forgery (SSRF)
**Mitigations:**
- Whitelist allowed broker API endpoints
- Validate OAuth redirect URIs
- No user-controlled URLs in API calls
- Network segmentation (Docker network)

**Implementation:**
```python
# Whitelist broker API domains
ALLOWED_BROKER_DOMAINS = [
    'api.schwab.com',
    'api.robinhood.com',
    'api.ml.com',
    'api.fidelity.com',
]

def validate_broker_url(url):
    parsed = urlparse(url)
    if parsed.netloc not in ALLOWED_BROKER_DOMAINS:
        raise ValueError(f'Invalid broker domain: {parsed.netloc}')
    return url
```

## Credential Encryption

### Fernet Encryption Details
```python
# app/encryption.py
from cryptography.fernet import Fernet
import os
import base64

class CredentialEncryption:
    def __init__(self):
        key = os.getenv('ENCRYPTION_KEY')
        if not key:
            raise ValueError('ENCRYPTION_KEY not set')
        self.cipher = Fernet(key.encode())
    
    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a string and return bytes"""
        return self.cipher.encrypt(plaintext.encode())
    
    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt bytes and return string"""
        return self.cipher.decrypt(ciphertext).decode()

# Usage in models
class BrokerCredential(db.Model):
    encrypted_access_token = db.Column(db.LargeBinary, nullable=False)
    
    @property
    def access_token(self):
        encryptor = CredentialEncryption()
        return encryptor.decrypt(self.encrypted_access_token)
    
    @access_token.setter
    def access_token(self, value):
        encryptor = CredentialEncryption()
        self.encrypted_access_token = encryptor.encrypt(value)
```

### Key Management
- **Generation**: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- **Storage**: `.env` file (not in version control)
- **Rotation**: Manual process (decrypt all, re-encrypt with new key)
- **Backup**: Store key securely in password manager

## OAuth Security

### Authorization Code Flow (PKCE)
```python
# OAuth initiation
import hashlib
import base64

# Generate code verifier
code_verifier = secrets.token_urlsafe(64)
session['code_verifier'] = code_verifier

# Generate code challenge
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).decode().rstrip('=')

# Redirect to broker with PKCE params
authorization_url = (
    f"{broker.auth_url}?"
    f"client_id={client_id}&"
    f"redirect_uri={redirect_uri}&"
    f"response_type=code&"
    f"state={state}&"
    f"code_challenge={code_challenge}&"
    f"code_challenge_method=S256"
)

# Token exchange callback
code_verifier = session.pop('code_verifier')
token_response = requests.post(broker.token_url, data={
    'grant_type': 'authorization_code',
    'code': auth_code,
    'redirect_uri': redirect_uri,
    'client_id': client_id,
    'code_verifier': code_verifier
})
```

### Redirect URI Validation
```python
ALLOWED_REDIRECT_URIS = {
    'schwab': 'https://localhost/oauth/callback/schwab',
    'robinhood': 'https://localhost/oauth/callback/robinhood',
    'merrill': 'https://localhost/oauth/callback/merrill',
    'fidelity': 'https://localhost/oauth/callback/fidelity',
}

@app.route('/oauth/callback/<broker>')
def oauth_callback(broker):
    if broker not in ALLOWED_REDIRECT_URIS:
        abort(400, 'Invalid broker')
    
    # Validate redirect_uri matches expected
    if request.url.split('?')[0] != ALLOWED_REDIRECT_URIS[broker]:
        abort(400, 'Invalid redirect URI')
    
    # Continue with OAuth flow...
```

## Database Security

### SQLite Configuration
```python
# app/database.py
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

# Enable SQLite foreign keys
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")  # Better concurrency
    cursor.close()

# Create engine with paranoid settings
engine = create_engine(
    'sqlite:///data/portfolio.db',
    echo=False,  # Don't log queries in production
    pool_pre_ping=True,  # Verify connections
    connect_args={
        'check_same_thread': False,
        'timeout': 30
    }
)
```

### File Permissions
```bash
# Set restrictive permissions on database file
chmod 600 /data/portfolio.db

# Set directory permissions
chmod 700 /data/

# Docker volume mount with restricted permissions
volumes:
  - ./data:/data:rw
```

## Network Security

### nginx SSL/TLS Configuration
```nginx
server {
    listen 443 ssl http2;
    server_name localhost;
    
    # SSL Certificate
    ssl_certificate /ssl/cert.pem;
    ssl_certificate_key /ssl/key.pem;
    
    # SSL Protocols and Ciphers (A+ rating)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    
    # SSL Session
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    
    # OCSP Stapling (for production)
    # ssl_stapling on;
    # ssl_stapling_verify on;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self';" always;
    
    # Additional Security
    server_tokens off;
    more_clear_headers Server;
    
    # Request size limits
    client_max_body_size 10M;
    client_body_buffer_size 128k;
    
    # Timeouts
    client_body_timeout 12;
    client_header_timeout 12;
    keepalive_timeout 15;
    send_timeout 10;
    
    # Proxy to Gunicorn
    location / {
        proxy_pass http://app:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_buffering off;
    }
}

# Disable HTTP (port 80)
server {
    listen 80;
    server_name localhost;
    return 301 https://$host$request_uri;
}
```

### SSL Certificate Generation
```bash
#!/bin/bash
# nginx/ssl/generate_cert.sh

# Generate self-signed certificate for localhost
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout key.pem \
  -out cert.pem \
  -subj "/C=US/ST=State/L=City/O=Personal/CN=localhost"

# Set permissions
chmod 600 key.pem
chmod 644 cert.pem

echo "SSL certificates generated successfully!"
echo "Note: This is a self-signed certificate. Your browser will show a warning."
echo "For production, use Let's Encrypt or a commercial CA."
```

## Input Validation

### Form Validation
```python
# app/utils/validators.py
from wtforms import validators
import re

class StockSymbolValidator:
    def __call__(self, form, field):
        if not re.match(r'^[A-Z]{1,5}$', field.data):
            raise validators.ValidationError('Invalid stock symbol')

class BrokerNameValidator:
    def __call__(self, form, field):
        allowed = ['schwab', 'robinhood', 'merrill', 'fidelity']
        if field.data not in allowed:
            raise validators.ValidationError('Invalid broker')

# Usage
class SettingsForm(FlaskForm):
    snapshot_limit = IntegerField('Snapshot Limit', [
        validators.NumberRange(min=1, max=100)
    ])
```

### API Input Validation
```python
from functools import wraps
from flask import request, jsonify

def validate_json(*expected_args):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify({'error': 'Content-Type must be application/json'}), 400
            
            data = request.get_json()
            for arg in expected_args:
                if arg not in data:
                    return jsonify({'error': f'Missing required field: {arg}'}), 400
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

# Usage
@app.route('/api/update-settings', methods=['POST'])
@validate_json('snapshot_limit', 'theme')
def update_settings():
    data = request.get_json()
    # Validated data available
    ...
```

## Rate Limiting

### OAuth Callback Rate Limiting
```python
from collections import defaultdict
from datetime import datetime, timedelta

# Simple in-memory rate limiter
oauth_attempts = defaultdict(list)

def check_oauth_rate_limit(broker_name, max_attempts=5, window_minutes=15):
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=window_minutes)
    
    # Remove old attempts
    oauth_attempts[broker_name] = [
        ts for ts in oauth_attempts[broker_name] if ts > cutoff
    ]
    
    # Check if exceeded
    if len(oauth_attempts[broker_name]) >= max_attempts:
        return False
    
    # Record attempt
    oauth_attempts[broker_name].append(now)
    return True

# Usage
@app.route('/oauth/callback/<broker>')
def oauth_callback(broker):
    if not check_oauth_rate_limit(broker):
        abort(429, 'Too many authentication attempts. Please try again later.')
    
    # Continue with OAuth flow...
```

## Secrets Management

### Environment Variables
```bash
# .env.example
ENCRYPTION_KEY=your-32-byte-fernet-key-here
SECRET_KEY=your-flask-secret-key-here
DATABASE_URL=sqlite:///data/portfolio.db

# Broker API Credentials (if not using OAuth)
SCHWAB_CLIENT_ID=your-client-id
SCHWAB_CLIENT_SECRET=your-client-secret
# ... repeat for other brokers
```

### Loading Environment
```python
# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///data/portfolio.db')
    
    # Validate required secrets
    @classmethod
    def validate(cls):
        required = ['SECRET_KEY', 'ENCRYPTION_KEY']
        missing = [key for key in required if not getattr(cls, key)]
        if missing:
            raise ValueError(f'Missing required config: {", ".join(missing)}')
```

## Security Checklist

### Pre-Deployment
- [ ] Change all default secrets/keys
- [ ] Generate SSL certificate
- [ ] Set restrictive file permissions
- [ ] Review nginx configuration
- [ ] Enable CSRF protection
- [ ] Configure secure session cookies
- [ ] Set encryption key in .env
- [ ] Test OAuth flows
- [ ] Verify database encryption
- [ ] Check log sanitization

### Post-Deployment
- [ ] Test SSL configuration (https://www.ssllabs.com/ssltest/)
- [ ] Verify HTTPS redirect works
- [ ] Test CSRF protection
- [ ] Check security headers (securityheaders.com)
- [ ] Review application logs
- [ ] Test rate limiting
- [ ] Verify session timeout
- [ ] Backup encryption key

### Ongoing Maintenance
- [ ] Update dependencies monthly
- [ ] Run security audit (pip-audit)
- [ ] Rotate encryption key yearly
- [ ] Review access logs for anomalies
- [ ] Update SSL certificate before expiration
- [ ] Test backup/restore procedures
- [ ] Review and update CSP headers