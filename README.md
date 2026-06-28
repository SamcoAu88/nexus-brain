# Nexus-Brain v5.0

**State-of-the-art AI Second Brain with Telegram Interface**

- 🧠 Advanced memory system with semantic search
- 🤖 Multi-LLM support with smart routing
- 💬 Telegram chat interface
- 🚀 Production-ready architecture
- 🔐 Enterprise-grade security (RLS, encryption, GDPR compliant)

---

## Quick Start (5 Minutes)

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Git
- VS Code (optional, but recommended)

### Local Development Setup

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/nexus-brain.git
cd nexus-brain

# 2. Create Python virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment variables
cp .env.example .env
# Edit .env with your API keys

# 5. Start Docker services
docker-compose up -d

# 6. Run migrations
# (Will be automated in Sprint 2)

# 7. Run tests
pytest tests/unit/ -v

# 8. Start FastAPI server
uvicorn src.main:app --reload

# Server will be at http://localhost:8000
# Docs available at http://localhost:8000/docs
```

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     Telegram User                            │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │  FastAPI Webhook       │
            │  (Rate Limit)          │
            │  (IP Whitelist)        │
            └────────────┬───────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
        ┌──────────────┐   ┌─────────────────┐
        │   LangGraph  │   │   Celery Queue  │
        │   Agent      │   │   (Async Jobs)  │
        └──────┬───────┘   └────────┬────────┘
               │                    │
        ┌──────┴────────────────────┴──────┐
        │                                  │
        ▼                                  ▼
  ┌──────────────────┐          ┌─────────────────┐
  │  Supabase/PG     │          │   Redis Cache   │
  │  (Memory DB)     │          │   (Vectors)     │
  │  (RLS Security)  │          │   (Sessions)    │
  └──────────────────┘          └─────────────────┘
        │
        ├─ OpenAI / Anthropic / Groq (LLM)
        ├─ Ollama (Local embeddings)
        ├─ Tavily (Web search)
        └─ Presidio (PII detection)
```

---

## Key Directories

```
nexus-brain/
├── src/
│   ├── main.py                 # FastAPI app entry
│   ├── core/
│   │   ├── config.py           # Settings management
│   │   └── logging_config.py   # Structured logging
│   ├── api/
│   │   ├── telegram_router.py  # Webhook handler
│   │   ├── memory_router.py    # Memory CRUD
│   │   └── health_router.py    # Health checks
│   ├── agents/                 # LangGraph agents
│   ├── tools/                  # External tools
│   ├── tasks/                  # Celery tasks
│   └── models/                 # DB models
├── tests/
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   └── fixtures/               # Test fixtures
├── deployment/
│   └── migrations/             # DB migrations
├── .github/
│   └── workflows/              # GitHub Actions
├── docker-compose.yml          # Local dev stack
├── Dockerfile                  # Container definition
├── requirements.txt            # Python dependencies
├── .env.example                # Environment template
└── README.md                   # This file
```

---

## Development Workflow

### Running Tests

```bash
# All tests
pytest tests/ -v

# Only unit tests
pytest tests/unit/ -v

# With coverage
pytest --cov=src --cov-report=html
```

### Running Celery (for background jobs)

```bash
# Terminal 1: Celery worker
celery -A src.tasks.app worker --loglevel=info

# Terminal 2: Celery beat (scheduler)
celery -A src.tasks.app beat --loglevel=info
```

### Database Management

```bash
# Check migrations (Sprint 2)
# supabase migration list

# Create new migration
# supabase migration new add_feature_x

# Apply migrations
# supabase db push
```

### Debugging

```bash
# View FastAPI docs
# Open http://localhost:8000/docs

# View Celery tasks
celery -A src.tasks.app inspect active

# View Redis cache
redis-cli KEYS "cache:*"
```

---

## Configuration

All configuration via `.env` file (see `.env.example`).

**Critical variables:**
- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
- `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` - Database
- `OPENAI_API_KEY` - LLM provider
- `REDIS_URL` - Cache/message broker
- `PII_MASTER_KEY` - Encryption key for sensitive data

---

## API Endpoints

### Health Checks
- `GET /` - Service info
- `GET /api/health` - Health status
- `GET /api/health/ready` - Readiness probe
- `GET /api/health/live` - Liveness probe

### Telegram
- `POST /api/telegram/webhook` - Webhook receiver (secret + IP validated)
- `GET /api/telegram/webhook/status` - Webhook status

### Memory (TODO in Sprint 2)
- `GET /api/memories` - List memories
- `POST /api/memories/search` - Search memories
- `POST /api/memories/capture` - Capture new memory
- `GET /api/memories/{id}` - Get memory
- `DELETE /api/memories/{id}` - Delete memory

---

## Sprint 1 Checklist

- [x] Project skeleton created
- [x] Docker Compose setup
- [x] FastAPI application structure
- [x] Configuration management
- [x] Health check endpoints
- [x] Telegram webhook (basic)
- [x] Rate limiting framework
- [x] Testing setup
- [x] GitHub Actions workflow
- [ ] Telegram webhook idempotency (Spring 2)
- [ ] PII redaction module (Sprint 2)
- [ ] Database migrations (Sprint 2)
- [ ] Ingestion pipeline (Sprint 2)

---

## Next: Sprint 2 (Week 3-4)

Will implement:
1. Database schema & migrations
2. Telegram idempotency
3. PII redaction (Presidio)
4. RLS + JWT authentication
5. Memory ingestion pipeline
6. Hybrid search (BM25 + Vector)

See `Handoff.v5.0.COMPLETE.md` for full specification.

---

## Production Deployment

See deployment guide in full documentation (v5.0.COMPLETE.md).

Brief steps:
1. Push to main branch
2. GitHub Actions runs tests + builds Docker
3. Deploy to Railway/Render (or K8s)
4. Run database migrations
5. Verify health endpoints

---

## Troubleshooting

**Docker won't start:**
```bash
docker-compose down -v  # Remove old volumes
docker-compose up -d
```

**Postgres connection refused:**
```bash
# Make sure postgres service is healthy
docker-compose ps
# Should see postgres container running
```

**Tests failing:**
```bash
# Ensure services are running
docker-compose up -d

# Check environment variables
cat .env

# Run with verbose output
pytest -vv
```

---

## Contributing

1. Create feature branch from `develop`
2. Make changes
3. Run tests: `pytest`
4. Commit + push
5. Create Pull Request

---

## Resources

- **Full Architecture**: See `Handoff.v5.0.COMPLETE.md`
- **v5.0 Specification**: Includes 25 sections covering all aspects
- **v4.0 Reference**: Legacy docs, check for historical context
- **API Docs**: http://localhost:8000/docs (when running)

---

## License

MIT

---

## Status

🟢 **Sprint 1 Complete** - Skeleton ready for development

Next: Sprint 2 (Database, Ingestion, RAG)

---

**Built with ❤️ using FastAPI, PostgreSQL, Redis, and AI**
