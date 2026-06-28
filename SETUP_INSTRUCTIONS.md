# Nexus-Brain Sprint 1 - SETUP INSTRUCTIONS

## Status: ✅ Ready to Deploy

You have a complete **Sprint 1 skeleton** ready to copy into your `C:\Projects\nexus` folder.

---

## 📋 Files Created

All these files are ready in `/mnt/user-data/outputs/`:

```
✅ requirements.txt              - Python dependencies
✅ .env.example                   - Environment template
✅ docker-compose.yml             - Local infrastructure (Postgres, Redis, FastAPI, Celery)
✅ Dockerfile                     - Container definition
✅ src/main.py                    - FastAPI app entry point
✅ src/core/config.py             - Settings management
✅ src/core/logging_config.py     - Structured logging
✅ src/api/health_router.py       - Health endpoints
✅ src/api/telegram_router.py     - Telegram webhook (with security)
✅ src/api/memory_router.py       - Memory endpoints (TODO in Sprint 2)
✅ tests/unit/test_health.py      - Basic tests
✅ pytest.ini                      - Test configuration
✅ .gitignore                      - Git ignore rules
✅ .github/workflows/ci-cd.yml    - GitHub Actions pipeline
✅ README.md                       - Documentation
✅ This file                       - Setup guide
```

---

## 🚀 Step 1: Copy Files to Your Project

Since I can't directly create files in `C:\Projects\nexus`, you'll **copy/paste from outputs**.

### Option A: Manual Copy (Fast)

1. **Open each file in outputs**
2. **Copy the content**
3. **Create corresponding file** in your VS Code
4. **Paste content**

### Option B: Automated (Faster)

If you have `git`, I'll show you how to clone a template repo.

---

## 📁 Step 2: Create Folder Structure

In VS Code terminal (`Ctrl + `` `), run:

```powershell
# Create directories
mkdir src\api
mkdir src\core
mkdir src\agents
mkdir src\tools
mkdir src\tasks
mkdir src\models
mkdir tests\unit
mkdir tests\integration
mkdir tests\fixtures
mkdir deployment\migrations
mkdir .github\workflows
mkdir logs

# Create __init__.py files
echo. > src\__init__.py
echo. > src\api\__init__.py
echo. > src\core\__init__.py
echo. > src\agents\__init__.py
echo. > src\tools\__init__.py
echo. > src\tasks\__init__.py
echo. > src\models\__init__.py
echo. > tests\__init__.py
echo. > tests\unit\__init__.py
```

---

## 📋 Step 3: Copy Each File

For each file in the list above:

1. **Download from outputs** (or copy from my artifact)
2. **Create in VS Code:**
   - `File` → `New File`
   - Paste path from list (e.g., `src/main.py`)
   - Paste content
   - `Ctrl+S` to save

---

## 🔑 Step 4: Create `.env` File

```powershell
# Copy .env.example to .env
copy .env.example .env
```

**Edit `.env` with your API keys:**

```powershell
# Windows PowerShell
code .env
```

**Minimum required:**
```
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
OPENAI_API_KEY=sk-your_key
SUPABASE_URL=https://your_project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_JWT_SECRET=super-secret-jwt-token
REDIS_URL=redis://localhost:6379/0
PII_MASTER_KEY=generate_with_fernet_see_below
```

**Generate Fernet Key (for PII encryption):**

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy output → paste into `.env` as `PII_MASTER_KEY=`

---

## 💻 Step 5: Setup Python Environment

```powershell
# Create virtual environment
python -m venv venv

# Activate it
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify
python --version
pip list | grep fastapi
```

---

## 🐳 Step 6: Start Docker

```powershell
# Make sure Docker Desktop is running!
# (Check Windows taskbar, start if needed)

# Start infrastructure
docker-compose up -d

# Verify services are running
docker-compose ps

# Should see:
# postgres    ✓ healthy
# redis       ✓ healthy
# pgadmin     ✓ running
# redis-commander ✓ running
```

**Check services:**

```powershell
# Postgres
psql -h localhost -U postgres -d nexus_brain

# Redis
redis-cli PING

# Web interfaces
# pgAdmin: http://localhost:5050
# Redis Commander: http://localhost:8081
```

---

## ✅ Step 7: Run Tests

```powershell
# Activate venv first
venv\Scripts\activate

# Run tests
pytest tests\unit\ -v

# Should see:
# test_root_endpoint PASSED
# test_health_endpoint PASSED
# test_docs_available PASSED
```

---

## 🎯 Step 8: Start FastAPI Server

```powershell
# Terminal 1: FastAPI server
uvicorn src.main:app --reload

# Should see:
# INFO:     Uvicorn running on http://127.0.0.1:8000
# INFO:     Application startup complete
```

---

## 🌐 Step 9: Test Endpoints

```powershell
# Terminal 2: Test endpoints
curl http://localhost:8000/

curl http://localhost:8000/api/health

# Or visit in browser:
# http://localhost:8000/docs (Swagger UI)
# http://localhost:8000/redoc (ReDoc)
```

---

## 🔄 Step 10: Verify All Services

Check everything is working:

```powershell
# ✅ FastAPI running
# http://localhost:8000/api/health

# ✅ PostgreSQL running
docker exec nexus-postgres psql -U postgres -d nexus_brain -c "SELECT version();"

# ✅ Redis running
docker exec nexus-redis redis-cli PING

# ✅ Tests passing
pytest tests\unit\ -v

# ✅ Git initialized (if starting fresh)
git init
git add .
git commit -m "Initial Sprint 1 skeleton"
```

---

## 🚨 Troubleshooting

### Docker won't start
```powershell
# Stop everything
docker-compose down -v

# Remove old volumes
docker volume prune

# Start fresh
docker-compose up -d
```

### Python modules not found
```powershell
# Make sure venv is activated
venv\Scripts\activate

# Reinstall
pip install -r requirements.txt --force-reinstall
```

### Port already in use
```powershell
# Check what's using port 8000
netstat -ano | findstr :8000

# Kill process (replace PID with actual number)
taskkill /PID 1234 /F

# Or change port in docker-compose.yml
```

### Telegram webhook not connecting
- Don't set up webhook yet (Sprint 2)
- For now, just verify endpoint exists
- Need: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`

---

## 📚 Next Steps (Sprint 2)

Once Sprint 1 is working:

1. **Database Migrations** - Create initial schema
2. **Telegram Idempotency** - Message deduplication
3. **PII Redaction** - Presidio integration
4. **RLS + JWT** - Multi-user security
5. **Ingestion Pipeline** - Celery tasks

All documented in `Handoff.v5.0.COMPLETE.md`

---

## ✨ Success Criteria

Sprint 1 is complete when:

- [x] Project skeleton created
- [x] All files in place
- [x] Virtual environment working
- [x] Docker services running
- [x] Tests passing
- [x] FastAPI server starts
- [x] Health endpoints respond
- [x] GitHub Actions workflow configured
- [ ] (Sprint 2) Database connected
- [ ] (Sprint 2) Telegram idempotency working

---

## 💡 Tips

1. **Keep `.env` safe** - Never commit to git
2. **Test often** - `pytest` after each change
3. **Check logs** - `docker-compose logs -f`
4. **Use Swagger UI** - `http://localhost:8000/docs` to test endpoints
5. **Git commits early** - `git commit` after each working feature

---

## Questions?

Check:
1. `README.md` - Overview and architecture
2. `Handoff.v5.0.COMPLETE.md` - Full specification
3. Docker logs - `docker-compose logs service_name`
4. Test output - `pytest -vv`

---

**You are ready to start coding! 🚀**

Next: Let me know when files are in place, and we'll start Sprint 1 work.
