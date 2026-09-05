import math
import os
import re
import logging
from hashlib import md5
from typing import Iterable

from app.core.config import get_settings


VECTOR_DIMENSIONS = 256
LOCAL_COLLECTION_NAME = "knowledge_chunks"
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "after",
    "be",
    "before",
    "by",
    "can",
    "company",
    "business",
    "day",
    "days",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "must",
    "need",
    "of",
    "on",
    "or",
    "request",
    "requests",
    "should",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "will",
    "with",
    "employee",
    "employees",
    "staff",
}
SYNONYMS = {
    "ask": ["request", "submit"],
    "critical": ["severity", "one"],
    "deadline": ["milestone", "scheduled"],
    "delivery": ["milestone"],
    "early": ["advance", "before"],
    "employee": ["staff"],
    "employees": ["staff"],
    "escalation": ["escalated", "incident"],
    "outage": ["incident"],
    "pto": ["vacation", "leave"],
    "scheduled": ["planned"],
    "staff": ["employees"],
    "timeoff": ["vacation", "leave"],
}

logger = logging.getLogger(__name__)
AI_RUNTIME_STATUS = {
    "embedding_configured": False,
    "embedding_verified": False,
    "embedding_mode": "local_fallback",
    "embedding_last_error": None,
    "chat_configured": False,
    "chat_verified": False,
    "chat_mode": "local_fallback",
    "chat_last_error": None,
}


class ChromaIndex:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = None
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
            self.client = chromadb.PersistentClient(
                path=str(self.settings.chroma_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        except Exception:
            self.client = None

    def upsert(self, chunks: list[dict]) -> None:
        if not self.client or not chunks:
            return
        embeddings, collection_name = embed_texts([chunk["content"] for chunk in chunks], self.settings)
        collection = self.client.get_or_create_collection(name=collection_name)
        collection.upsert(
            ids=[chunk["id"] for chunk in chunks],
            embeddings=embeddings,
            documents=[chunk["content"] for chunk in chunks],
            metadatas=[
                {
                    "document_id": chunk["document_id"],
                    "document_title": chunk["document_title"],
                    "page": chunk["page"] or 0,
                    "version": chunk["version"],
                }
                for chunk in chunks
            ],
        )

    def delete_document(self, document_id: str) -> None:
        if not self.client:
            return
        for collection_name in {LOCAL_COLLECTION_NAME, openai_collection_name(self.settings.embedding_model)}:
            try:
                collection = self.client.get_or_create_collection(name=collection_name)
                collection.delete(where={"document_id": document_id})
            except Exception:
                continue

    def query(self, text: str, allowed_document_ids: list[str], limit: int) -> list[dict]:
        if not self.client or not allowed_document_ids:
            return []
        query_embedding, collection_name = embed_texts([text], self.settings)
        collection = self.client.get_or_create_collection(name=collection_name)
        count = collection.count()
        if count == 0:
            return []
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=min(count, max(limit * 2, limit)),
            where={"document_id": {"$in": allowed_document_ids}},
        )
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        matches = []
        for chunk_id, distance, content, metadata in zip(ids, distances, documents, metadatas):
            score = max(0.0, 1.0 - float(distance))
            if score <= 0:
                continue
            matches.append(
                {
                    "id": chunk_id,
                    "content": content,
                    "score": score,
                    "source": "semantic",
                    **metadata,
                }
            )
        return matches[:limit]


def embed_texts(texts: list[str], settings=None) -> tuple[list[list[float]], str]:
    settings = settings or get_settings()
    AI_RUNTIME_STATUS["embedding_configured"] = bool(settings.openai_api_key)
    if settings.openai_api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None)
            response = client.embeddings.create(model=settings.embedding_model, input=texts)
            embeddings = [item.embedding for item in response.data]
            AI_RUNTIME_STATUS.update(
                {
                    "embedding_verified": True,
                    "embedding_mode": "openai",
                    "embedding_last_error": None,
                }
            )
            return embeddings, openai_collection_name(settings.embedding_model)
        except Exception as exc:
            AI_RUNTIME_STATUS.update(
                {
                    "embedding_verified": False,
                    "embedding_mode": "local_fallback",
                    "embedding_last_error": str(exc),
                }
            )
            logger.warning("OpenAI embedding failed; falling back to local hash embeddings: %s", exc)
    return [hash_embedding(text) for text in texts], LOCAL_COLLECTION_NAME


def ai_runtime_status() -> dict:
    settings = get_settings()
    status = dict(AI_RUNTIME_STATUS)
    status["embedding_configured"] = bool(settings.openai_api_key)
    status["chat_configured"] = bool(settings.openai_api_key)
    status["embedding_model"] = settings.embedding_model
    status["chat_model"] = settings.chat_model
    status["active_embedding_collection"] = (
        openai_collection_name(settings.embedding_model) if status["embedding_mode"] == "openai" else LOCAL_COLLECTION_NAME
    )
    return status


def openai_collection_name(model: str) -> str:
    digest = md5(model.encode("utf-8")).hexdigest()[:12]
    return f"knowledge_openai_{digest}"


def hash_embedding(text: str) -> list[float]:
    vector = [0.0] * VECTOR_DIMENSIONS
    for token in tokenize(text, expand=True):
        index = int(md5(token.encode("utf-8")).hexdigest(), 16) % VECTOR_DIMENSIONS
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def tokenize(text: str, expand: bool = False) -> list[str]:
    tokens = [token for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if token not in STOPWORDS]
    if not expand:
        return tokens
    expanded = list(tokens)
    for token in tokens:
        expanded.extend(SYNONYMS.get(token, []))
    return expanded


def overlap_score(query_tokens: Iterable[str], text: str) -> float:
    query = set(query_tokens)
    if not query:
        return 0.0
    content = set(tokenize(text))
    return len(query & content) / len(query)
