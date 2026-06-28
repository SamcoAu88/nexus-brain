# Nexus-Brain v5.0 - Complete Project Handoff & Roadmap
**Last Updated:** June 28, 2026  
**Project Status:** Sprint 2 Complete (33% of project)  
**Repository:** https://github.com/SamcoAu88/nexus-brain

---

## 📋 Executive Summary

**Nexus-Brain v5.0** is a personal AI assistant with Telegram interface, RAG memory system, and LangGraph agentic architecture. Currently at Sprint 2 completion with production-ready database schema, idempotent webhook handling, and comprehensive CRUD operations. 33% complete - on track for full launch in 3-4 months.

**Current Status:** 
- ✅ Database fully migrated (12 tables, Alembic)
- ✅ Telegram webhook with deduplication (idempotency)
- ✅ Memory CRUD API (collections, sources, chunks, conversations, messages)
- ✅ 33 unit tests passing (75% coverage)
- ⏳ Type checking (mypy) being resolved
- ⬜ Auth, PII, LangGraph agent pending

---

## 🏗️ Architecture Overview

### Tech Stack
- **Backend:** FastAPI + Python 3.11
- **Database:** PostgreSQL 15 + Alembic (migrations)
- **Queue:** Celery + Redis
- **ML/AI:** LangGraph (agents), LiteLLM (multi-model), Presidio (PII)
- **Search:** pgvector (embeddings) + BM25 (hybrid)
- **Infrastructure:** Docker Compose, Cloudflare Tunnel
- **Monitoring:** Langfuse, Sentry, OpenTelemetry, Prometheus
- **Testing:** pytest, coverage 75%

### Database Schema (12 Tables)
```
user_profiles          → User accounts + Telegram mapping
collections            → Memory projects/notebooks
sources                → Data sources (docs, links, voice, messages)
memory_chunks          → Text chunks for embedding + search
entities               → Named entities (persons, places, concepts)
entity_relations       → Knowledge graph (entity relationships)
chunk_entities         → Junction: chunks mention entities
conversations          → Chat sessions
messages               → Individual messages (user/assistant)
cost_tracking          → API costs per user per day
audit_logs             → Immutable audit trail
telegram_update_log    → Webhook idempotency tracking (24h TTL)
```

### LangGraph Agent (6 Nodes - Sprint 4)
1. **Input Router** → Classify message type (question/memory/etc)
2. **Memory Retriever** → Hybrid search (BM25 + vectors)
3. **Entity Extractor** → Presidio PII + Named entities
4. **Reasoner** → Multi-step reasoning with tools
5. **Response Generator** → Generate answer + PII masking
6. **Memory Writer** → Store in PostgreSQL

---

## ✅ Completed Work (Sprints 1-2)

### Sprint 1: Foundation
- ✅ FastAPI skeleton with structured logging
- ✅ Docker Compose (Postgres, Redis, Celery, PgAdmin, Redis Commander)
- ✅ Health check endpoints (/health, /ready, /live, /docs)
- ✅ Config management (Pydantic Settings)
- ✅ 5 health tests passing

**Commits:** Initial skeleton, Docker setup, health routes

### Sprint 2: Database & Webhook (COMPLETED TODAY)
- ✅ **Database Migration (Alembic)**
  - 11 tables created with relationships
  - Indexes for performance (user_id, collection_id, chunk_id, etc)
  - Foreign key constraints
  - UUIDs for all primary keys
  
- ✅ **Telegram Idempotency Pipeline**
  - Database-backed `telegram_update_log` table
  - 24-hour TTL for deduplication
  - IP whitelist validation (Telegram datacenters only)
  - Secret token verification
  - 6 comprehensive idempotency tests
  
- ✅ **Memory Router CRUD**
  - Collections: create, list, get, delete
  - Sources: create, list (with soft-delete filter)
  - Chunks: create, list (ordered by index)
  - Conversations: create, list, get (archived filter)
  - Messages: create, list (ordered by time)
  - Pydantic schemas for all models
  - User isolation via user_id filter
  
- ✅ **Test Coverage**
  - 33 total tests (5 health + 6 idempotency + 22 CRUD)
  - 75% code coverage
  - All tests passing locally and in CI

**Commits:**
1. Database migrations & schema creation
2. Telegram idempotency with DB tracking
3. Memory Router CRUD implementation
4. Comprehensive CRUD test suite
5. Import cleanup (ruff linter)
6. Code formatting (Black)

---

## 🚨 Issues Encountered & Solutions

### Issue 1: Alembic `.env` Loading Failure
**Problem:** Alembic migration couldn't read `.env` file, falling back to hardcoded `user:user` credentials.

**Root Cause:** `load_dotenv()` running from wrong directory; migration files had hardcoded default in `alembic.ini`.

**Solution:**
- Moved imports to top of `env.py`
- Used `Path(__file__).resolve()` for absolute path resolution
- Loaded `.env` explicitly before creating engine
- Used `create_engine(database_url)` directly instead of `engine_from_config()`

**Lesson:** Environment loading in migrations must use absolute paths; relative paths fail when invoked from different directories.

---

### Issue 2: SQLAlchemy Reserved Keywords
**Problem:** Column named `metadata` triggered SQLAlchemy error - "reserved when using Declarative API."

**Root Cause:** `metadata` is a reserved attribute in SQLAlchemy ORM.

**Solution:** Renamed all `metadata` columns to `meta_data` in Source, Entity, and EntityRelation models.

**Lesson:** Check SQLAlchemy reserved keywords before naming columns.

---

### Issue 3: Duplicate Table Definition in Models
**Problem:** `TelegramUpdateLog` class was nested inside `AuditLog` class, causing redefinition error during migration.

**Root Cause:** Copy-paste mistake - nested class indentation.

**Solution:** Moved `TelegramUpdateLog` to root level (module-level class).

**Lesson:** Always verify class indentation matches intended nesting level.

---

### Issue 4: Ruff Linter (11 Fixable + 9 Manual)
**Problem:** CI failed with 20 ruff violations (unused imports, boolean comparisons to False).

**Root Cause:** 
- Unused imports from initial code generation
- SQLAlchemy filter syntax requires `~Column == False` not `Column == False`

**Solution:**
- `ruff check --fix` auto-fixed 11 issues
- Manual fixes for E712 errors: replaced `Column == False` with `~Column` in SQLAlchemy filters
- Removed unused variable assignments

**Lesson:** Linters catch real issues but require understanding of context (e.g., SQLAlchemy filters != boolean logic).

---

### Issue 5: Black Formatting
**Problem:** Black reformatted 12 files; CI failed.

**Root Cause:** Code generated didn't match Black style; line-ending differences (LF vs CRLF) on Windows.

**Solution:** Ran `black src/ tests/` locally and committed formatted code.

**Lesson:** Run formatters locally before pushing; configure pre-commit hooks to automate this.

---

### Issue 6: MyPy Type Checking (IN PROGRESS)
**Problem:** 27 mypy errors across 4 files.

**Root Cause:**
- Settings() load missing `.env` parameter
- Generator functions need `Generator[YieldType, SendType, ReturnType]` return type
- `user_id: UUID = None` should be `user_id: Optional[UUID] = None`
- Embedding column missing type hint

**Solution (Applied):**
- Changed `settings = Settings()` to `settings = Settings(_env_file=".env")`
- Changed `get_db() -> Session` to `get_db() -> Generator[Session, None, None]`
- Added embedding type: `embedding: list[float] | None`
- Find/Replace all `user_id: UUID = None` with `user_id: Optional[UUID] = None`
- Ran `black src/ tests/` again

**Status:** Awaiting CI confirmation. Should pass now.

---

## 📊 Current Test Status

```
Tests Passing:    33/33 ✅
Coverage:         75%
Lint (Ruff):      ✅ PASSING
Format (Black):   ✅ PASSING  
Types (MyPy):     ⏳ PENDING (fixes applied)

By Category:
- Health checks:     5/5 ✅
- Idempotency:       6/6 ✅
- CRUD Collections:  6/6 ✅
- CRUD Sources:      3/3 ✅
- CRUD Chunks:       4/4 ✅
- CRUD Conversations: 3/3 ✅
- CRUD Messages:     3/3 ✅
- Relationships:     3/3 ✅
```

**Coverage by Module:**
```
src/models/memory.py         100% ✅
src/schemas/memory.py        100% ✅
src/core/config.py            94% ⚠️ (settings load)
src/core/logging_config.py   100% ✅
src/api/health_router.py      82% ⚠️ (untested error paths)
src/api/telegram_router.py    66% ⚠️ (auth TODO)
src/api/memory_router.py      26% ⚠️ (no endpoint integration tests yet)
```

---

## ⚠️ Current Known Issues

### 1. Memory Router Endpoints Not Integration-Tested
**Status:** Low Priority  
**Details:** CRUD functions exist but endpoints require auth dependency injection that's not yet implemented. Database operations work (unit tests pass), but HTTP layer integration tests are pending Auth implementation.

**Fix Timeline:** Sprint 3 (Auth)

### 2. User ID Hardcoded to None
**Status:** Blocking Feature Development  
**Details:** All memory router endpoints have `user_id: Optional[UUID] = None` - they work for testing but won't enforce user isolation in production.

**Fix Timeline:** Sprint 3 (JWT Auth)

### 3. Telegram Webhook Processing Not Wired
**Status:** Medium Priority  
**Details:** Webhook receives updates correctly and stores idempotency log, but message processing (extraction, chunking, storage) is stubbed with TODO comments.

**Fix Timeline:** Sprint 4 (Celery + LangGraph)

### 4. PII Masking Not Implemented
**Status:** Medium Priority  
**Details:** Message model has `content_masked` column but no Presidio integration yet.

**Fix Timeline:** Sprint 3 (PII Protection)

---

## 🛣️ Detailed Roadmap for Remaining Work

### Sprint 3: Authentication & Security (2-3 weeks)
**Goal:** Protect endpoints, mask sensitive data, prepare for multi-user production.

#### 3.1 JWT Authentication
- [ ] Create `src/auth/tokens.py` - JWT encoding/decoding
- [ ] Create `src/auth/dependencies.py` - `get_current_user()` dependency
- [ ] Create auth router with `/login`, `/token`, `/refresh`
- [ ] Extract `user_id` from JWT in all memory router endpoints
- [ ] Add auth tests (10+ tests)
- [ ] Update memory router to use auth dependency

**Files to Create:**
```
src/auth/__init__.py
src/auth/tokens.py        # JWT encode/decode with RS256
src/auth/dependencies.py  # FastAPI dependencies
src/auth/router.py        # Login/token endpoints
tests/unit/test_auth.py   # Auth integration tests
```

**Tech:** PyJWT, python-jose, passlib

#### 3.2 PII Protection with Presidio
- [ ] Install presidio-analyzer, presidio-anonymizer
- [ ] Create `src/security/pii.py` - PII detection/masking
- [ ] Integrate into message creation (mask before storing `content_masked`)
- [ ] Create audit log for PII redactions
- [ ] Add Presidio tests (5+ tests)

**Key Logic:**
```python
# Detect PII in message.content
# Mask it → store in message.content_masked
# Log detection in audit_logs table
```

#### 3.3 Fernet Encryption for Sensitive Fields
- [ ] Create `src/security/encryption.py` - Fernet key management
- [ ] Encrypt sensitive fields (api_keys, webhook_urls)
- [ ] Add decrypt on read, encrypt on write
- [ ] Update `src/core/config.py` to use encrypted secrets

**Estimate:** 150 lines of code

#### 3.4 Update Config to Use ConfigDict (Pydantic v2)
- [ ] Migrate all Settings classes from `class Config` to `ConfigDict`
- [ ] Resolve mypy deprecation warnings

**Sprint 3 Deliverables:**
- ✅ JWT auth working on all endpoints
- ✅ PII detection + masking in messages
- ✅ Encrypted secrets in config
- ✅ 25+ new tests for auth/security
- ✅ User isolation enforced in DB queries

**Testing:** 33 + 25 = 58 tests total

---

### Sprint 4: LangGraph Agent & Celery Ingestion (2-3 weeks)
**Goal:** Wire agent reasoning, async message processing, RAG pipeline.

#### 4.1 LangGraph Agent (6 Nodes)
- [ ] Create `src/agents/graph.py` - define 6-node graph
- [ ] Node 1: Input Router (classify message type)
- [ ] Node 2: Memory Retriever (BM25 + vector search)
- [ ] Node 3: Entity Extractor (Presidio + named entities)
- [ ] Node 4: Reasoner (multi-step with tools)
- [ ] Node 5: Response Generator (with context)
- [ ] Node 6: Memory Writer (store to PostgreSQL)
- [ ] Add LangSmith tracing for debugging
- [ ] Add agent tests (10+ tests)

**Files to Create:**
```
src/agents/__init__.py
src/agents/graph.py           # Main graph definition
src/agents/nodes.py           # Individual node functions
src/agents/tools.py           # Tool definitions (search, calc, etc)
tests/unit/test_agent.py      # Agent integration tests
```

**Key Dependencies:** langgraph, langchain, langgraph-checkpoint

#### 4.2 Celery Async Tasks
- [ ] Wire Celery worker in Docker
- [ ] Create `src/tasks/process_message.py` - async ingestion task
- [ ] Task pipeline: extract → chunk → embed → store
- [ ] Add task retries, dead-letter queue
- [ ] Add Celery monitoring (Flower)

**Files to Create:**
```
src/tasks/__init__.py
src/tasks/process_message.py  # Main async task
src/tasks/embedding.py        # Embedding generation
tests/integration/test_celery.py
```

#### 4.3 Telegram Webhook → Celery Integration
- [ ] Update telegram_router to send to Celery queue
- [ ] Remove TODO stubs
- [ ] Task receives update_id + message data
- [ ] Task calls agent graph
- [ ] Agent writes response to memory
- [ ] Send response back to Telegram via bot API

**Logic Flow:**
```
User sends message to Telegram
  ↓
Webhook receives (idempotency check passes)
  ↓
Store in telegram_update_log
  ↓
Enqueue Celery task: process_message(update_id, message_data)
  ↓
Return 200 OK to Telegram immediately
  ↓
[Async] Celery worker processes:
  - Call LangGraph agent
  - Agent retrieves memory
  - Agent reasons
  - Generate response
  - Store in conversations/messages
  - Send response to Telegram
```

#### 4.4 Embedding Generation
- [ ] Choose embedding model (OpenAI, Cohere, or local)
- [ ] Create `src/embeddings/service.py`
- [ ] Batch embedding during ingestion
- [ ] Store vectors in memory_chunks.embedding
- [ ] Index for fast retrieval

**Estimate:** 200 lines

**Sprint 4 Deliverables:**
- ✅ Full LangGraph agent reasoning
- ✅ Async Celery task queue
- ✅ End-to-end Telegram → agent → memory flow
- ✅ Embedding generation + storage
- ✅ Agent traces in LangSmith
- ✅ 35+ new tests

**Testing:** 58 + 35 = 93 tests total

---

### Sprint 5: Hybrid Search & Vector Operations (1-2 weeks)
**Goal:** Fast, relevant memory retrieval combining semantic + keyword search.

#### 5.1 Vector Search Setup
- [ ] Create `src/search/vector.py` - pgvector queries
- [ ] Create indexes on memory_chunks.embedding (GiST/IVFFlat)
- [ ] Implement cosine similarity search
- [ ] Add reranking with CrossEncoder

**Query Example:**
```sql
SELECT chunk_id, content, importance,
  1 - (embedding <=> query_vector) as similarity
FROM memory_chunks
WHERE source_id = $1
ORDER BY similarity DESC
LIMIT 10;
```

#### 5.2 BM25 Full-Text Search
- [ ] Create GIN index on memory_chunks.content
- [ ] Implement PostgreSQL full-text search
- [ ] Rank by TF-IDF

**Query Example:**
```sql
SELECT chunk_id, content, 
  ts_rank(to_tsvector('english', content), query) as rank
FROM memory_chunks
WHERE to_tsvector('english', content) @@ plainto_tsquery('english', $1)
ORDER BY rank DESC
LIMIT 10;
```

#### 5.3 Hybrid Search (Weighted Combination)
- [ ] Create `src/search/hybrid.py`
- [ ] Combine: 60% vector + 35% BM25 + 5% recency
- [ ] Normalize scores to 0-1 range
- [ ] Return top-k deduplicated results

**Formula:**
```
score = (0.6 * cosine_similarity) + (0.35 * bm25_rank) + (0.05 * recency_bonus)
```

#### 5.4 Relevance Ranking
- [ ] Chunk importance factor (already in model)
- [ ] Access recency boost
- [ ] Entity match bonus (if named entities align)

#### 5.5 Search Tests
- [ ] 10+ integration tests
- [ ] Edge cases: empty queries, special characters, unicode
- [ ] Relevance validation

**Files to Create:**
```
src/search/__init__.py
src/search/vector.py          # Vector similarity
src/search/bm25.py            # Full-text search
src/search/hybrid.py          # Combined search
src/search/reranker.py        # CrossEncoder reranking
tests/integration/test_search.py
```

**Sprint 5 Deliverables:**
- ✅ Vector search with pgvector
- ✅ BM25 full-text search
- ✅ Hybrid search combining both
- ✅ Reranking with CrossEncoder
- ✅ 15+ search tests

**Testing:** 93 + 15 = 108 tests total

---

### Sprint 6: Production Hardening & Deployment (1-2 weeks)
**Goal:** Security, monitoring, scalability, launch readiness.

#### 6.1 Row-Level Security (RLS)
- [ ] Enable RLS on all tables
- [ ] Create policies for user_id isolation
- [ ] Test RLS enforcement
- [ ] Add SQL tests

**Example Policy:**
```sql
CREATE POLICY user_isolation ON memory_chunks
  USING (source_id IN (
    SELECT source_id FROM sources 
    WHERE collection_id IN (
      SELECT collection_id FROM collections 
      WHERE user_id = current_user_id()
    )
  ));
```

#### 6.2 Monitoring & Observability
- [ ] Enable Langfuse tracing (already in requirements)
- [ ] Add Sentry error tracking (already in requirements)
- [ ] Add Prometheus metrics (request count, latency, errors)
- [ ] Dashboard in Grafana (optional)

**Key Metrics:**
```
- HTTP requests per endpoint
- Webhook processing latency
- Agent reasoning time
- Database query time
- Queue depth (Celery)
- Cache hit ratio
```

#### 6.3 Cloudflare Tunnel Setup
- [ ] Install cloudflared locally
- [ ] Create tunnel configuration
- [ ] Route webhook through tunnel
- [ ] Enable Cloudflare WAF rules

**Tunnel Config Example:**
```yaml
tunnel: nexus-brain-prod
ingress:
  - hostname: api.example.com
    service: http://localhost:8000
  - service: http_status:404
```

#### 6.4 Rate Limiting & DDoS Protection
- [ ] Add rate limiting middleware (Slowapi)
- [ ] Implement per-user quotas
- [ ] Add IP blacklist/whitelist
- [ ] Cloudflare rate limiting rules

#### 6.5 Database Backup & Recovery
- [ ] Automated backups (pg_dump daily)
- [ ] Backup storage (S3 or similar)
- [ ] Recovery testing procedure
- [ ] Point-in-time recovery setup

#### 6.6 Load Testing
- [ ] Locust tests for concurrent users
- [ ] Stress test database (connection pool)
- [ ] Test agent under load
- [ ] Identify bottlenecks

**Test Scenarios:**
```
- 100 concurrent webhook requests
- 1000 memory retrieval queries per second
- Agent reasoning with max context window
```

#### 6.7 Documentation
- [ ] API documentation (auto-generated from FastAPI)
- [ ] Deployment runbook
- [ ] Troubleshooting guide
- [ ] Architecture decision records (ADRs)

**Files:**
```
docs/DEPLOYMENT.md
docs/RUNBOOK.md
docs/TROUBLESHOOTING.md
docs/ARCHITECTURE.md
```

#### 6.8 CI/CD Pipeline Completion
- [ ] GitHub Actions: lint → test → build → deploy
- [ ] Docker image building + registry push
- [ ] Staging environment testing
- [ ] Blue-green deployment strategy

**Sprint 6 Deliverables:**
- ✅ RLS policies enforcing user isolation
- ✅ Full observability (Langfuse, Sentry, Prometheus)
- ✅ Cloudflare Tunnel in production
- ✅ Rate limiting + DDoS protection
- ✅ Automated backups
- ✅ Load testing with passing thresholds
- ✅ Complete documentation
- ✅ CI/CD automated to production

**Testing:** 108 + 20 (ops tests) = 128 tests total

---

## 📈 Project Timeline & Milestones

```
Sprint 1 (Done)      ✅ Foundation              [1 week]    June 24-28
Sprint 2 (Done)      ✅ Database + Webhook     [1 week]    June 28
Sprint 3 (Next)      ⏳ Auth + Security        [2-3 weeks] July 1-15
Sprint 4 (Then)      ⏳ Agent + Ingestion      [2-3 weeks] July 15-29
Sprint 5 (Then)      ⏳ Hybrid Search          [1-2 weeks] July 29-Aug 5
Sprint 6 (Final)     ⏳ Production + Launch    [1-2 weeks] Aug 5-15

Total Timeline:       ~8-10 weeks from start
Remaining:           ~6-7 weeks
Launch Target:       Mid-August 2026
```

---

## 🔧 Environment Setup (For Continuity)

### Quick Start
```bash
# Clone
git clone https://github.com/SamcoAu88/nexus-brain.git
cd nexus-brain

# Activate venv
.\venv\Scripts\Activate.ps1  # Windows PowerShell

# Install deps
pip install -r requirements.txt

# Start Docker
docker-compose up -d

# Run migrations
alembic upgrade head

# Run tests
pytest tests/unit/ -v

# Start dev server
uvicorn src.main:app --reload
```

### Key Directories
```
C:\Projects\nexus\
├── src/
│   ├── api/              # FastAPI routers
│   ├── models/           # SQLAlchemy ORM
│   ├── schemas/          # Pydantic validation
│   ├── core/             # Config, logging, database
│   ├── agents/           # LangGraph (Sprint 4)
│   ├── security/         # Auth, PII, encryption (Sprint 3)
│   └── search/           # Hybrid search (Sprint 5)
├── tests/
│   └── unit/             # 33 tests (75% coverage)
├── deployment/
│   └── alembic/          # Database migrations
├── .github/
│   └── workflows/        # CI/CD (ruff, black, mypy, pytest)
├── docker-compose.yml
└── requirements.txt
```

### Database Connection (Local)
```
postgresql://postgres:postgres@localhost:5432/nexus_brain

PgAdmin: http://localhost:5050
Username: admin@admin.com
Password: admin
```

### Redis Connection (Local)
```
redis://localhost:6379/0

Redis Commander: http://localhost:8081
```

---

## 📚 References & Resources

### Key Documentation
- **FastAPI Docs:** https://fastapi.tiangolo.com
- **SQLAlchemy ORM:** https://docs.sqlalchemy.org
- **Alembic Migrations:** https://alembic.sqlalchemy.org
- **LangGraph:** https://langchain-ai.github.io/langgraph
- **Presidio PII:** https://microsoft.github.io/presidio
- **PostgreSQL:** https://www.postgresql.org/docs

### Python Packages (Critical)
```
fastapi==0.138.1
sqlalchemy==2.0+
psycopg2-binary==2.9+
alembic==1.13+
langgraph==0.0.20+
celery==5.6+
pytest==9.1+
black==24+
ruff==0.2+
mypy==1.8+
```

### GitHub Actions Workflow
Located at: `.github/workflows/ci-cd.yml`

Currently runs:
1. Ruff lint check
2. Black format check
3. MyPy type checking
4. Pytest unit tests (33 tests)

---

## 🎯 Key Success Metrics

**By Sprint 6 Completion:**
- ✅ 128+ unit tests (95%+ passing)
- ✅ 80%+ code coverage
- ✅ All endpoints authenticated
- ✅ <100ms memory retrieval latency
- ✅ <500ms agent reasoning time
- ✅ <50 failed requests per million (99.99% uptime target)
- ✅ 0 security vulnerabilities (OWASP Top 10)
- ✅ Full audit logging

---

## 💡 Lessons Learned

1. **Alembic migrations need absolute path resolution** - relative paths fail across directories
2. **SQLAlchemy boolean filters use `~` not `== False`** - reserved operator behavior
3. **Type checking should be enforced early** - catching mypy errors in Sprint 2 prevented Sprint 4+ issues
4. **Idempotency is critical for webhooks** - Telegram will retry, must deduplicate upstream
5. **Run linters and formatters locally** - CI should validate, not teach
6. **Environment loading order matters** - imports must happen before config loading
7. **Generate tests alongside code** - CRUD tests caught edge cases immediately
8. **Use absolute paths in migrations** - Alembic runs from different contexts

---

## 🚀 Next Immediate Steps (Sprint 3)

1. Wait for MyPy CI to pass (should be green soon)
2. Start Sprint 3:
   - [ ] Create `src/auth/` module with JWT
   - [ ] Create `src/security/` module with PII + Fernet
   - [ ] Write 25+ auth + security tests
   - [ ] Update all memory router endpoints to require auth
3. Test locally thoroughly before pushing
4. Commit incrementally (one feature per commit)

---

## 📞 Support & Debugging

### Common Issues & Fixes

**Database won't connect:**
```powershell
# Check Docker
docker-compose ps

# Check logs
docker-compose logs nexus-postgres

# Reset database
docker-compose down -v
docker-compose up -d
alembic upgrade head
```

**Migrations failing:**
```powershell
# Check migration status
alembic current

# Downgrade if needed
alembic downgrade -1

# Reapply
alembic upgrade head
```

**Tests failing:**
```powershell
# Run with verbose output
pytest tests/unit/test_memory_crud.py -vv -s

# Run specific test
pytest tests/unit/test_memory_crud.py::TestCollectionCRUD::test_create_collection_db -vv
```

---

**Document Created:** June 28, 2026  
**Document Version:** 1.0  
**Status:** Project at Sprint 2 Completion

*This document is a complete backup and roadmap for Nexus-Brain v5.0. Keep it safe and reference it during subsequent sprints.*
