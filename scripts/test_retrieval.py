"""
End-to-end retrieval verification against the live database.
Run: docker exec -e PYTHONPATH=/app nexus-celery python /app/scripts/test_retrieval.py
"""

import logging
import sys
from uuid import UUID

logging.basicConfig(level=logging.WARNING)

TELEGRAM_USER = UUID("79a70709-0b8f-447f-8157-1761ed5e6ae6")

from src.agents.tools import get_recent_memories, search_memory
from src.search.vector_search import vector_search
from src.search.bm25_search import bm25_search

failures = 0

print("=" * 60)
print("TEST 1: get_recent_memories (the 'about me' path)")
results = get_recent_memories(user_id=TELEGRAM_USER, limit=15)
print(f"  -> {len(results)} chunks")
for r in results[:3]:
    print(f"  -> {r['content'][:70]!r}")
if not results:
    failures += 1
    print("  FAIL: expected chunks, got none")

print("=" * 60)
print("TEST 2: vector_search (Python cosine, no pgvector)")
results = vector_search(query="what is the user's job and age", user_id=TELEGRAM_USER, top_k=3)
print(f"  -> {len(results)} results")
for r in results:
    print(f"  -> score={r['score']:.3f}  {r['content'][:60]!r}")
if not results:
    failures += 1
    print("  FAIL: expected results, got none")

print("=" * 60)
print("TEST 3: bm25_search (OR tsquery + ILIKE fallback)")
results = bm25_search(query="name job work postie", user_id=TELEGRAM_USER, top_k=3)
print(f"  -> {len(results)} results")
for r in results:
    print(f"  -> {r['content'][:60]!r}")
if not results:
    failures += 1
    print("  FAIL: expected results, got none")

print("=" * 60)
print("TEST 4: search_memory (full hybrid pipeline)")
results = search_memory(query="user's name age job", user_id=TELEGRAM_USER, limit=5)
print(f"  -> {len(results)} results")
for r in results[:3]:
    print(f"  -> {r['content'][:60]!r}")
if not results:
    failures += 1
    print("  FAIL: expected results, got none")

print("=" * 60)
if failures:
    print(f"RESULT: {failures} TEST(S) FAILED")
    sys.exit(1)
print("RESULT: ALL 4 TESTS PASSED")
