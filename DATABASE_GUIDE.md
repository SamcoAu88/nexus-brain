# 💾 Database Tables Complete Guide

Your data is stored in **14 tables** in PostgreSQL. Here's what each one does:

---

## 📚 **Core Tables - Your Conversations**

### 1. **conversations** - Chat Sessions
**Purpose:** Groups messages into conversations per user

**Columns:**
- `conversation_id` - Unique ID
- `user_id` - Which user (your Telegram ID)
- `title` - Auto-generated like "Telegram 123456"
- `created_at` - When chat started
- `is_archived` - If conversation is closed

**Query Your Chats:**
```sql
SELECT conversation_id, title, created_at 
FROM conversations 
WHERE user_id = (SELECT user_id FROM user_profiles LIMIT 1)
ORDER BY created_at DESC;
```

---

### 2. **messages** - Chat History & Bot Responses
**Purpose:** Every message sent (user messages + bot responses)

**Columns:**
- `message_id` - Unique ID
- `conversation_id` - Which chat
- `role` - "user" or "assistant"
- `content` - Original text
- `content_masked` - PII removed version
- `created_at` - When sent
- `tokens_used` - API tokens consumed
- `model_used` - Which LLM responded

**Query Your Chat History:**
```sql
-- See all your messages in order
SELECT role, content, created_at 
FROM messages
WHERE conversation_id IN (
  SELECT conversation_id FROM conversations 
  WHERE user_id = (SELECT user_id FROM user_profiles LIMIT 1)
)
ORDER BY created_at ASC;

-- See only bot responses
SELECT content, created_at FROM messages
WHERE role = 'assistant' AND conversation_id IN (
  SELECT conversation_id FROM conversations 
  LIMIT 1
)
ORDER BY created_at ASC;

-- See how many tokens used
SELECT COUNT(*), SUM(tokens_used) as total_tokens 
FROM messages 
WHERE role = 'assistant';
```

**Example Output:**
```
role      | content                           | created_at
----------|-----------------------------------|------------------
user      | My name is Samet                  | 2026-06-30 5:18pm
assistant | Great to meet you, Samet!        | 2026-06-30 5:18pm
user      | I'm learning AI engineering      | 2026-06-30 5:19pm
assistant | That's awesome, keep learning!   | 2026-06-30 5:19pm
```

---

### 3. **user_profiles** - You!
**Purpose:** User account info

**Columns:**
- `user_id` - Your unique ID (UUID)
- `telegram_id` - Your Telegram ID
- `username` - Your login name (auto-generated)
- `password_hash` - Hashed password (not reversible)
- `created_at` - Account creation
- `is_active` - If account is active

**Query Your Profile:**
```sql
SELECT user_id, telegram_id, username, created_at 
FROM user_profiles;
```

---

## 🧠 **Memory Tables - What Bot Remembers**

### 4. **collections** - Memory Folders
**Purpose:** Organize memories into groups (like notes folders)

**Columns:**
- `collection_id` - Unique ID
- `user_id` - Your memories
- `name` - Folder name (e.g., "Work Notes", "Learning")
- `description` - What's in it
- `created_at` - When created

**Query:**
```sql
SELECT name, description, created_at 
FROM collections 
WHERE user_id = (SELECT user_id FROM user_profiles LIMIT 1);
```

---

### 5. **sources** - Data Origins
**Purpose:** Where memories came from (Telegram message, document, etc.)

**Columns:**
- `source_id` - Unique ID
- `collection_id` - Which folder
- `source_type` - "message", "document", "link", "voice"
- `title` - Source name
- `url` - Link (if applicable)
- `raw_content` - Original text
- `created_at` - When added

**Query:**
```sql
SELECT source_type, title, created_at 
FROM sources 
WHERE collection_id IN (
  SELECT collection_id FROM collections LIMIT 1
);
```

---

### 6. **memory_chunks** - Individual Memories
**Purpose:** Text pieces that can be searched

**Columns:**
- `chunk_id` - Unique ID
- `source_id` - Which source
- `content` - The actual memory text
- `chunk_index` - Position in source
- `embedding` - Vector (1536 numbers for AI search)
- `search_vector` - Full-text search index
- `importance` - How important (0.0-1.0)
- `created_at` - When stored
- `last_accessed` - When you accessed it

**Query Your Memories:**
```sql
-- See all your stored memories
SELECT content, importance, created_at 
FROM memory_chunks
WHERE source_id IN (
  SELECT source_id FROM sources 
  WHERE collection_id IN (
    SELECT collection_id FROM collections LIMIT 1
  )
)
ORDER BY created_at DESC;

-- Find specific memory
SELECT content FROM memory_chunks 
WHERE content ILIKE '%AI engineering%' 
LIMIT 5;
```

---

## 🏷️ **Entity Tables - Named Things**

### 7. **entities** - People, Places, Concepts
**Purpose:** Extracted names and concepts from your messages

**Columns:**
- `entity_id` - Unique ID
- `user_id` - Your entities
- `name` - "Samet", "Australia Post", "AI"
- `entity_type` - "person", "organization", "concept", "place"
- `description` - Extra info
- `created_at` - When extracted

**Query:**
```sql
-- See all entities found in your messages
SELECT name, entity_type, description 
FROM entities
WHERE user_id = (SELECT user_id FROM user_profiles LIMIT 1)
ORDER BY entity_type;

-- Example: Find all people mentioned
SELECT name FROM entities
WHERE entity_type = 'person';
```

---

### 8. **entity_relations** - How Things Connect
**Purpose:** Relationship graph (e.g., "Samet works at Australia Post")

**Columns:**
- `relation_id` - Unique ID
- `entity_a_id` - First entity (e.g., Samet)
- `entity_b_id` - Second entity (e.g., Australia Post)
- `relation_type` - "works_at", "located_in", "knows", etc.
- `weight` - Strength of relation (0.0-1.0)
- `created_at` - When discovered

**Query:**
```sql
-- See all relationships
SELECT e1.name as entity1, r.relation_type, e2.name as entity2
FROM entity_relations r
JOIN entities e1 ON r.entity_a_id = e1.entity_id
JOIN entities e2 ON r.entity_b_id = e2.entity_id
LIMIT 20;
```

---

### 9. **chunk_entities** - Memory Links to Entities
**Purpose:** Which memories mention which people/places

**Columns:**
- `chunk_entity_id` - Junction ID
- `chunk_id` - Which memory
- `entity_id` - Which entity
- `mention_count` - How many times mentioned
- `created_at` - When linked

**Query:**
```sql
-- See which memories mention "Samet"
SELECT mc.content, ce.mention_count
FROM chunk_entities ce
JOIN memory_chunks mc ON ce.chunk_id = mc.chunk_id
JOIN entities e ON ce.entity_id = e.entity_id
WHERE e.name = 'Samet';
```

---

## 🔍 **Search & Detection Tables**

### 10. **pii_redaction_logs** - Private Information Detected
**Purpose:** Log all PII found and masked

**Columns:**
- `log_id` - Unique ID
- `user_id` - Your data
- `message_id` - Which message had PII
- `pii_types` - ["EMAIL", "PHONE", "PERSON"]
- `pii_count` - How many pieces detected
- `sample_entities` - Examples (masked)
- `created_at` - When detected

**Query:**
```sql
-- See all PII detections in your chats
SELECT pii_types, pii_count, created_at 
FROM pii_redaction_logs
WHERE user_id = (SELECT user_id FROM user_profiles LIMIT 1)
ORDER BY created_at DESC;

-- Count by type
SELECT pii_types, COUNT(*) 
FROM pii_redaction_logs, UNNEST(pii_types) as pii_type
GROUP BY pii_type;
```

---

## 💰 **Usage Tracking**

### 11. **cost_tracking** - API Spending
**Purpose:** Track how much you've spent on LLM API calls

**Columns:**
- `cost_id` - Unique ID
- `user_id` - Your account
- `date` - YYYY-MM-DD
- `total_cost` - USD spent
- `requests_count` - How many API calls
- `tokens_used` - Total LLM tokens
- `updated_at` - Last update

**Query:**
```sql
-- See daily spending
SELECT date, total_cost, requests_count, tokens_used 
FROM cost_tracking
WHERE user_id = (SELECT user_id FROM user_profiles LIMIT 1)
ORDER BY date DESC;

-- Total spent
SELECT SUM(total_cost) as total_spent 
FROM cost_tracking;
```

---

## 📋 **Audit & Management**

### 12. **audit_logs** - All Changes
**Purpose:** Immutable record of everything that changed

**Columns:**
- `log_id` - Unique ID
- `user_id` - Who made change
- `action` - "CREATE", "UPDATE", "DELETE"
- `table_name` - Which table changed
- `record_id` - Which record
- `changes` - What changed (JSON)
- `created_at` - When changed

**Query:**
```sql
-- See all changes in your account
SELECT action, table_name, created_at 
FROM audit_logs
WHERE user_id = (SELECT user_id FROM user_profiles LIMIT 1)
ORDER BY created_at DESC
LIMIT 20;
```

---

### 13. **telegram_update_log** - Message Deduplication
**Purpose:** Track processed Telegram messages (prevent duplicates)

**Columns:**
- `id` - ID
- `update_id` - Telegram update ID
- `user_id` - Your ID
- `processed_at` - When processed
- `expires_at` - Cleanup time (24h)

**Query:**
```sql
-- See recent message processing
SELECT update_id, processed_at 
FROM telegram_update_log
WHERE user_id = (SELECT user_id FROM user_profiles LIMIT 1)
ORDER BY processed_at DESC
LIMIT 10;
```

---

### 14. **alembic_version** - Migration Version
**Purpose:** Database schema version tracking

**Query:**
```sql
SELECT version_num FROM alembic_version;
-- Shows which migrations were applied
```

---

## 🎯 **Quick Queries to Try**

### See Everything About You
```sql
-- Your profile
SELECT * FROM user_profiles;

-- Your conversations
SELECT * FROM conversations;

-- Your messages (last 10)
SELECT role, content, created_at FROM messages 
ORDER BY created_at DESC LIMIT 10;

-- Your memories
SELECT content FROM memory_chunks LIMIT 10;

-- PII detected in your messages
SELECT pii_types, pii_count FROM pii_redaction_logs LIMIT 5;
```

### Export All Your Data
```sql
-- Backup everything
pg_dump -h localhost -U postgres nexus_brain > my_data.sql
```

### Search for Specific Info
```sql
-- Find all mentions of "AI"
SELECT content FROM memory_chunks 
WHERE content ILIKE '%AI%'
ORDER BY created_at DESC;

-- Find conversations about work
SELECT m.content, c.created_at FROM messages m
JOIN conversations c ON m.conversation_id = c.conversation_id
WHERE m.content ILIKE '%work%' OR m.content ILIKE '%job%'
ORDER BY m.created_at DESC;
```

---

## 📊 Database Statistics

```sql
-- Count everything
SELECT 
  (SELECT COUNT(*) FROM messages) as total_messages,
  (SELECT COUNT(*) FROM memory_chunks) as total_memories,
  (SELECT COUNT(*) FROM entities) as total_entities,
  (SELECT COUNT(*) FROM conversations) as total_conversations,
  (SELECT SUM(tokens_used) FROM messages) as total_tokens_used;
```

---

## ✅ Summary

**Your 14 Tables:**
1. **alembic_version** - Schema version
2. **audit_logs** - Change history
3. **chunk_entities** - Memory-entity links
4. **collections** - Memory folders
5. **conversations** - Chat sessions
6. **cost_tracking** - API spending
7. **entities** - People/places/concepts
8. **entity_relations** - How entities connect
9. **memory_chunks** - Individual memories + embeddings
10. **messages** - Chat history (YOUR MAIN TABLE!)
11. **pii_redaction_logs** - PII detections
12. **sources** - Memory origins
13. **telegram_update_log** - Message processing log
14. **user_profiles** - Your account

**Most Important Tables:**
- **messages** - Your chat history
- **memory_chunks** - What bot remembers
- **user_profiles** - Your account
- **conversations** - Your chat groups
- **pii_redaction_logs** - Your private data detected
