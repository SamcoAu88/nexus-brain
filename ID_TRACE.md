# ID Synchronization Trace

## Flow

```
1. telegram_router.py:203
   sends: user_id=str(user.user_id)  [UUID as STRING]
   
2. agent_tasks.py:61
   converts: user_id=UUID(user_id)  [STRING → UUID]
   
3. graph.py:169
   passes: user_id=user_id  [UUID object]
   
4. state.py:59
   stores: user_id=user_id  [UUID object]
   
5. nodes.py:193
   reads: user_id = state["user_id"]  [UUID object]
   
6. tools.py:245
   calls: search_memory(user_id=user_id, ...)  [UUID object]
   
7. hybrid_search.py:65
   calls: vector_search(user_id=user_id, ...)  [UUID object]
   
8. vector_search.py:79
   SQL param: "user_id": user_id  [UUID object → PostgreSQL UUID]
   WHERE c.user_id = :user_id
```

## Potential Issues

1. UUID to STRING to UUID conversion might fail
2. SQLAlchemy might not convert UUID correctly to PostgreSQL UUID type
3. UUID object might be str() instead of UUID() in some places
4. Collections might not have correct user_id filled

## Test Query

```sql
SELECT 
  c.collection_id, 
  c.user_id,
  COUNT(s.source_id) as source_count,
  COUNT(mc.chunk_id) as memory_count
FROM collections c
LEFT JOIN sources s ON c.collection_id = s.collection_id
LEFT JOIN memory_chunks mc ON s.source_id = mc.source_id
WHERE c.user_id = 'your-uuid-here'
GROUP BY c.collection_id, c.user_id;
```
