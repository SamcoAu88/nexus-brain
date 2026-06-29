"""
Nexus-Brain Hybrid Search Module (Sprint 5)
Combines pgvector (cosine similarity) + PostgreSQL full-text search (BM25 equivalent)
with Reciprocal Rank Fusion (RRF) for result merging.
"""

DEFAULT_RRF_K = 60  # RRF constant (higher = more weight to top ranks)
DEFAULT_VECTOR_WEIGHT = 0.6  # Vector score weight in hybrid results
DEFAULT_BM25_WEIGHT = 0.4  # BM25 score weight in hybrid results
DEFAULT_TOP_K = 20  # Results to fetch per search method
DEFAULT_FINAL_K = 10  # Final merged results
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536
