# 🚢 Spider AI - Production Deployment Guide

This document provides complete instructions for deploying **Spider AI** into production across Docker containers, Linux virtual machines (systemd + Gunicorn), and Cloud platforms.

---

## 📋 Pre-Deployment Security Checklist

Before deploying to a public or production environment, ensure you verify each item:

| Setting | Recommendation | Purpose |
| :--- | :--- | :--- |
| `DJANGO_DEBUG` | `False` | Prevents exposing sensitive stack traces, debug information, and internal state. |
| `DJANGO_SECRET_KEY` | High-entropy random 64-char string | Used for cryptographic signing of session cookies and tokens. |
| `ALLOWED_HOSTS` | Exact domains (e.g. `spider-ai.yourdomain.com`) | Mitigates HTTP Host header poisoning attacks. |
| `CSRF_TRUSTED_ORIGINS` | `https://yourdomain.com` | Prevents Cross-Site Request Forgery on incoming POST/PUT requests. |
| `GEMINI_API_KEY` | Set securely via Environment or Secret Manager | Required for all agent cognitive reasoning and synthesis. |
| `Database & Storage` | Persistent Docker volumes or managed DB | Ensures conversational history and uploads survive container rebuilds. |

Generate a cryptographically secure Django Secret Key:
```bash
python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

---

## 🐳 Deployment Method 1: Docker & Docker Compose (Recommended)

Docker Compose provides container isolation, automated restart policies, and persistent storage volumes.

### 1. Configure Production Environment Variables
Create the `.env` file from the provided template:
```bash
cp .env.example .env
chmod 600 .env
```
Edit `.env` with production values:
```ini
GEMINI_API_KEY=your_actual_google_gemini_api_key
DJANGO_SECRET_KEY=your_generated_random_secret_key
DJANGO_DEBUG=False
ALLOWED_HOSTS=spider-ai.yourdomain.com,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://spider-ai.yourdomain.com
PORT=8000
```

### 2. Build and Launch Containers
```bash
docker compose up -d --build
```

### 3. Verify Deployment & Health Check
```bash
# Check container status
docker compose ps

# Follow container runtime logs
docker compose logs -f web

# Verify HTTP response
curl -I http://localhost:8000/
```

### 4. Updating to Latest Code
```bash
git pull origin main
docker compose build --no-cache web
docker compose up -d
```

---

## 🔒 Production Nginx Reverse Proxy & SSL Setup

In production, run Nginx in front of Spider AI to handle TLS termination, request buffering, and static asset caching.

### Sample Nginx Virtual Host (`/etc/nginx/sites-available/spider-ai`)
```nginx
server {
    listen 80;
    server_name spider-ai.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name spider-ai.yourdomain.com;

    # SSL Certificates (managed via Certbot Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/spider-ai.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/spider-ai.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Maximum file upload size for documents and audio recordings
    client_max_body_size 64M;

    # Proxy headers
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Server-Sent Events (SSE) buffering disabled for real-time streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 600s;
    }
}
```

Enable the configuration and obtain free SSL via Certbot:
```bash
sudo ln -s /etc/nginx/sites-available/spider-ai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d spider-ai.yourdomain.com
```

---

## 🐧 Deployment Method 2: Systemd & Native Linux Host

If deploying directly onto an Ubuntu/Debian Linux VM:

### 1. Install System Dependencies & Setup User
```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip libnss3 libatk1.0-0 libcups2 libdrm2 libgbm1 libasound2 ffmpeg
sudo useradd -m -s /bin/bash spiderapp
sudo -u spiderapp git clone https://github.com/JoshkefGhost6958/spider-ai.git /home/spiderapp/app
```

### 2. Install Virtualenv and Playwright
```bash
cd /home/spiderapp/app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python manage.py migrate
python manage.py collectstatic --noinput
```

### 3. Configure Systemd Service (`/etc/systemd/system/spider-ai.service`)
```ini
[Unit]
Description=Spider AI Gunicorn Daemon
After=network.target

[Service]
User=spiderapp
Group=spiderapp
WorkingDirectory=/home/spiderapp/app
EnvironmentFile=/home/spiderapp/app/.env
ExecStart=/home/spiderapp/app/.venv/bin/gunicorn \
          --workers 3 \
          --timeout 120 \
          --bind 127.0.0.1:8000 \
          --access-logfile /home/spiderapp/app/gunicorn-access.log \
          --error-logfile /home/spiderapp/app/gunicorn-error.log \
          config.wsgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable spider-ai
sudo systemctl start spider-ai
sudo systemctl status spider-ai
```

---

## ☁️ Deployment Method 3: Cloud Run / Container Platforms

Spider AI is fully OCI container compliant. You can deploy to Google Cloud Run, AWS ECS, or Render:

### Google Cloud Run
```bash
# 1. Build and submit container image
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/spider-ai:latest

# 2. Deploy to Cloud Run with environment secrets
gcloud run deploy spider-ai \
    --image gcr.io/YOUR_PROJECT_ID/spider-ai:latest \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars DJANGO_DEBUG=False,ALLOWED_HOSTS=* \
    --set-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest,DJANGO_SECRET_KEY=DJANGO_SECRET_KEY:latest \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300
```

---

## 🔍 Post-Deployment Verification & Troubleshooting

1. **Verify Web Interface**:
   Navigate to `https://spider-ai.yourdomain.com` and ensure the landing interface loads.
2. **Execute a Test Investigation**:
   Submit a test query (e.g., *"What are the latest updates on Raila Odinga International Stadium?"*).
3. **Verify Audio Fallback**:
   Click the microphone button to confirm voice dictation and server-side fallback succeed.
4. **Inspect Diagnostic Logs**:
   - Docker: `docker compose logs --tail=100 -f web`
   - Systemd: `journalctl -u spider-ai -e -f`
