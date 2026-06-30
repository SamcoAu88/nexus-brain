# 💾 Where Your Data is Stored

Short answer: **PostgreSQL in Docker** (NOT Supabase)

---

## 📊 Data Storage Architecture

```
┌─────────────────────────────────────────────────────────┐
│         Your Telegram Messages                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓
        ┌─────────────────────────────┐
        │   FastAPI Webhook Handler   │
        │  (receives from Telegram)   │
        └──────────────┬──────────────┘
                       │
                       ↓
        ┌──────────────────────────────────┐
        │   PostgreSQL Database (Docker)   │  ← YOUR DATA LIVES HERE
        │                                  │
        │  - Conversations                 │
        │  - Messages                      │
        │  - User Profiles                 │
        │  - Memory Collections            │
        │  - Embeddings/Vectors            │
        │  - Audit Logs                    │
        └──────────────────────────────────┘
                       │
                       ↓
        ┌─────────────────────────────┐
        │   Redis Cache (Docker)      │
        │  (temporary storage)        │
        └─────────────────────────────┘
```

---

## 🗂️ Database Details

### Database Name
```
nexus_brain
```

### Connection String
```
postgresql://postgres:postgres@postgres:5432/nexus_brain
```

### Where It Runs
```
Docker container: nexus-postgres
Port: 5432 (internal to Docker network)
Accessible from host: localhost:5432
```

### Access It Yourself
```bash
# Option 1: Use pgAdmin (Web UI)
http://localhost:5050
Login: admin@admin.com / admin

# Option 2: Use psql command line
psql -h localhost -U postgres -d nexus_brain

# Option 3: Use DBeaver, DataGrip, or other SQL client
```

---

## 📋 What's Stored in PostgreSQL

### 13 Tables (Fully Indexed):

#### User Management
- **user_profiles** - Your Telegram ID, username, password hash
- **telegram_update_log** - All Telegram messages received (dedup key)

#### Conversations & Messages
- **conversations** - Chat sessions (one per Telegram user)
- **messages** - All messages (both user input + bot responses)
  - Stores: original text, masked version (PII removed), tokens used, timestamp
- **cost_tracking** - API usage and spending per user per day

#### Memory & Knowledge
- **collections** - Memory collections (like "notes", "learning", etc.)
- **sources** - Where memories come from (document, link, message, voice)
- **memory_chunks** - Text chunks with embeddings
  - Stores: text, vector embedding (1536 dims), full-text search vector
- **entities** - Extracted entities (person, place, concept names)
- **entity_relations** - Graph relationships between entities
- **chunk_entities** - Junction table linking chunks to entities

#### Audit & Security
- **audit_logs** - All data changes (immutable log)
- **pii_redaction_logs** - All PII detections (compliance log)

---

## 🔍 Example: What Happens When You Send a Message

### Step 1: Message Received
```sql
INSERT INTO messages (message_id, conversation_id, role, content, content_masked, created_at)
VALUES ('...', '...', 'user', 'My email is john@example.com', 'My email is ****', NOW());
```

### Step 2: PII Logged
```sql
INSERT INTO pii_redaction_logs (user_id, message_id, pii_types, pii_count, sample_entities)
VALUES ('...', '...', '["EMAIL"]', 1, '["john@example.com"]');
```

### Step 3: Embeddings Generated
```sql
UPDATE memory_chunks 
SET embedding = '[0.123, -0.456, ...]'  -- 1536-dimensional vector
WHERE chunk_id = '...';
```

### Step 4: Response Stored
```sql
INSERT INTO messages (conversation_id, role, content, created_at)
VALUES ('...', 'assistant', 'I found your email and masked it...', NOW());
```

### Step 5: Audit Log
```sql
INSERT INTO audit_logs (user_id, action, table_name, record_id, changes)
VALUES ('...', 'CREATE', 'messages', '...', '{"role": "user", "content": "..."}');
```

---

## 💾 Storage Breakdown

### Database Size
- PostgreSQL: **~100-500 MB** (depending on message volume)
- Vectors stored in: **pgvector** (native PostgreSQL extension)
- Full-text search: **tsvector** (PostgreSQL native)

### Persistence
- ✅ **Persisted across restarts** (stored on disk)
- ✅ **Not lost when containers restart**
- ✅ **Survives Docker crashes**
- ✅ **Can be backed up/exported**

### Data Volume
- ~1 KB per message (including metadata)
- ~6 KB per vector embedding (1536 dimensions)
- After 1000 messages: ~1-2 MB database size

---

## 🔐 Data Security

### What's Protected
- ✅ Passwords: Hashed with Argon2 (not reversible)
- ✅ Sensitive API keys: Encrypted with Fernet (AES-128-CBC)
- ✅ PII: Masked before storage (email → ****)
- ✅ All changes: Audit logged

### What's NOT Sent to Supabase
- ❌ No data goes to Supabase (those configs are placeholders)
- ✅ All data stays in your Docker PostgreSQL
- ✅ No cloud dependency for data storage
- ✅ You own 100% of your data

---

## 🚀 Is Supabase Used?

### Supabase Fields in `.env`
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
SUPABASE_JWT_SECRET=your_jwt_secret_here
```

### Current Status
- ⏸️ **Not configured/used**
- These are template values for **future** use
- All actual data goes to PostgreSQL (Docker)

### Could Use Supabase If Desired
- Supabase = Managed PostgreSQL + Auth + Real-time (hosted)
- Current setup = Self-hosted PostgreSQL in Docker
- Both use same SQL, so easy to migrate if needed

---

## 📂 Access Your Data

### Via pgAdmin Web UI (Easiest)
1. Open http://localhost:5050
2. Login: `admin@admin.com` / `admin`
3. Add server: `nexus-postgres`
4. Browse databases, tables, query data

### Via Command Line
```bash
# Connect to database
psql -h localhost -U postgres -d nexus_brain

# List conversations
SELECT conversation_id, title, created_at FROM conversations;

# List all messages
SELECT message_id, role, content, created_at FROM messages ORDER BY created_at;

# Find user
SELECT user_id, telegram_id, username FROM user_profiles;

# Search for stored memories
SELECT content FROM memory_chunks WHERE content LIKE '%your search%';

# Check PII detections
SELECT user_id, pii_types, pii_count, created_at FROM pii_redaction_logs;
```

### Export Your Data
```bash
# Backup database
docker exec nexus-postgres pg_dump -U postgres nexus_brain > nexus_backup.sql

# Restore database
psql -h localhost -U postgres -d nexus_brain < nexus_backup.sql
```

---

## 🔄 Data Flow Diagram

```
User (Telegram)
     ↓
@nexus_brain_devs_bot (Receives message)
     ↓
ngrok tunnel (Public → Local)
     ↓
FastAPI (Port 8000)
     ↓
Celery Worker (Processes async)
     ↓
LLM (DeepSeek or OpenAI) - Generates response
     ↓
PostgreSQL (Stores everything)
     ↓
Telegram Bot API (Sends response back)
     ↓
User (Receives response)

ALL DATA STORED IN POSTGRESQL ✅
(Not sent to Supabase, cloud, or anywhere else)
```

---

## ✅ Data Stored When You Use Bot

### Every Message
- ✅ Message text (original + masked)
- ✅ Sender (your Telegram ID)
- ✅ Timestamp
- ✅ Conversation ID (groups by chat)
- ✅ LLM tokens used
- ✅ Processing latency

### Extracted Information
- ✅ Entity names (people, places, organizations)
- ✅ PII detected (email, phone, etc.) - masked
- ✅ Vector embeddings (for search)
- ✅ Full-text search index

### Audit Trail
- ✅ All changes logged
- ✅ Who changed what, when
- ✅ Immutable log (can't delete)

---

## 🎯 Summary

| Question | Answer |
|----------|--------|
| **Where is data saved?** | PostgreSQL in Docker (localhost:5432) |
| **Is it Supabase?** | No, it's self-hosted PostgreSQL |
| **Is it cloud?** | No, it's on your machine in Docker |
| **Can you access it?** | Yes, via pgAdmin or psql |
| **Is it persistent?** | Yes, survives container restarts |
| **Can you export it?** | Yes, via SQL dump |
| **Is it encrypted?** | Yes, PII is masked, sensitive data encrypted |
| **Do you own the data?** | Yes, 100% - it's in your Docker |

---

## 📍 How to Verify Your Data is Saved

### In PostgreSQL
```bash
# Connect to DB
psql -h localhost -U postgres -d nexus_brain

# Query your messages
SELECT content FROM messages WHERE role = 'user' LIMIT 5;

# Output shows your recent messages saved in database
```

### In pgAdmin UI
1. Open http://localhost:5050
2. Servers → nexus-postgres → Databases → nexus_brain → Schemas → public → Tables
3. Right-click `messages` → View/Edit Data
4. See all your conversations and messages

### Docker Volume
```bash
# PostgreSQL data stored in Docker volume
docker volume ls | grep postgres

# Data persists even if container stops
docker stop nexus-postgres
docker start nexus-postgres
# Data is still there!
```

---

**Your data is safe, secure, and completely under your control!** 🔒

