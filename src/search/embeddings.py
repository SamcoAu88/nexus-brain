"""
Embedding Generation
Generates vector embeddings for text chunks using OpenAI or Ollama.
"""

import logging
from typing import List, Optional

from src.core.config import settings
from src.search import DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)

# ─── OpenAI Embeddings ─────────────────────────────────


def generate_openai_embedding(
    text: str,
    model: str = DEFAULT_EMBEDDING_MODEL,
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
) -> Optional[List[float]]:
    """
    Generate an embedding vector using OpenAI's API.

    Args:
        text: Text to embed
        model: OpenAI embedding model name
        dimensions: Output dimensions (text-embedding-3-small supports 512/1536)

    Returns:
        List of floats, or None on failure
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set, skipping OpenAI embedding")
        return None

    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        response = client.embeddings.create(
            model=model,
            input=text,
            dimensions=dimensions,
        )
        embedding = response.data[0].embedding
        logger.debug(f"OpenAI embedding: {len(embedding)} dimensions")
        return embedding
    except Exception as e:
        logger.error(f"OpenAI embedding failed: {e}")
        return None


def generate_ollama_embedding(
    text: str,
    model: Optional[str] = None,
) -> Optional[List[float]]:
    """
    Generate embedding using local Ollama instance (fallback).

    Args:
        text: Text to embed
        model: Ollama model name (defaults to config setting)

    Returns:
        List of floats, or None on failure
    """
    import requests

    model = model or settings.OLLAMA_EMBEDDING_MODEL
    url = f"{settings.OLLAMA_API_URL}/api/embeddings"

    try:
        response = requests.post(
            url,
            json={"model": model, "prompt": text},
            timeout=30,
        )
        response.raise_for_status()
        embedding = response.json().get("embedding")
        logger.debug(f"Ollama embedding: {len(embedding)} dims ({model})")
        return embedding
    except Exception as e:
        logger.error(f"Ollama embedding failed: {e}")
        return None


# ─── Unified Embedding ─────────────────────────────────


def generate_embedding(
    text: str,
    prefer_ollama: bool = False,
) -> Optional[List[float]]:
    """
    Generate embedding with automatic fallback.
    OpenAI -> Ollama -> None

    Args:
        text: Text to embed
        prefer_ollama: Try Ollama first (for local-only dev)

    Returns:
        Embedding vector or None
    """
    if not text or not text.strip():
        logger.warning("Empty text, skipping embedding")
        return None

    if prefer_ollama:
        result = generate_ollama_embedding(text)
        if result:
            return result
        return generate_openai_embedding(text)

    result = generate_openai_embedding(text)
    if result:
        return result
    return generate_ollama_embedding(text)


# ─── Batch Embedding ───────────────────────────────────


def generate_embeddings_batch(
    texts: List[str],
    batch_size: int = 20,
) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts in batches.

    Args:
        texts: List of texts to embed
        batch_size: OpenAI API batch size

    Returns:
        List of embedding vectors (None for failed items)
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set, skipping batch embedding")
        return [None] * len(texts)

    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    results: List[Optional[List[float]]] = []

    try:
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch = [t for t in batch if t and t.strip()]

            if not batch:
                continue

            response = client.embeddings.create(
                model=DEFAULT_EMBEDDING_MODEL,
                input=batch,
                dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
            )

            emb_map = {e.index: e.embedding for e in response.data}
            results.extend(emb_map.get(j, None) for j in range(len(batch)))

        return results
    except Exception as e:
        logger.error(f"Batch embedding failed: {e}")
        return [None] * len(texts)
