import math
from collections import Counter, defaultdict

from app.core.config import get_settings
from app.services.vector_store import ChromaIndex, overlap_score, tokenize
from app.storage.database import get_connection, loads, rows_to_dicts


def allowed_document_ids(user: dict) -> list[str]:
    with get_connection() as connection:
        rows = rows_to_dicts(
            connection.execute("SELECT id, department, roles, classification FROM documents WHERE active = 1").fetchall()
        )
    allowed = []
    for row in rows:
        row["roles"] = loads(row["roles"], [])
        if can_access_document(user, row):
            allowed.append(row["id"])
    return allowed


def can_access_document(user: dict, document: dict) -> bool:
    user_roles = set(user["roles"])
    document_roles = set(document["roles"])
    classification = document.get("classification", "internal")

    if "admin" in user_roles:
        return True
    if classification == "public":
        return True
    if classification == "internal":
        return "employee" in user_roles
    if classification == "confidential":
        return user["department"] == document["department"] or bool(user_roles & document_roles)
    return False


def hybrid_search(question: str, user: dict, limit: int | None = None) -> list[dict]:
    settings = get_settings()
    limit = limit or settings.retrieval_k
    allowed_ids = allowed_document_ids(user)
    if not allowed_ids:
        return []
    keyword_results = _keyword_search(question, allowed_ids, limit)
    semantic_results = ChromaIndex().query(question, allowed_ids, limit)
    if not semantic_results:
        semantic_results = _semantic_fallback(question, allowed_ids, limit)
    merged: dict[str, dict] = {}
    for result in keyword_results + semantic_results:
        chunk_id = result["id"]
        if chunk_id not in merged:
            merged[chunk_id] = {**result, "score": 0.0, "sources": set()}
        merged[chunk_id]["score"] += result["score"]
        merged[chunk_id]["sources"].add(result["source"])
    ranked = []
    for result in merged.values():
        result["sources"] = sorted(result["sources"])
        ranked.append(result)
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]


def _keyword_search(question: str, allowed_ids: list[str], limit: int) -> list[dict]:
    query_tokens = tokenize(question, expand=True)
    if not query_tokens:
        return []
    rows = _load_chunks(allowed_ids)
    document_frequency = defaultdict(int)
    chunk_tokens: dict[str, list[str]] = {}
    for row in rows:
        tokens = tokenize(row["content"])
        chunk_tokens[row["id"]] = tokens
        for token in set(tokens):
            document_frequency[token] += 1
    scores = []
    total_chunks = max(len(rows), 1)
    avg_length = sum(len(tokens) for tokens in chunk_tokens.values()) / total_chunks
    for row in rows:
        tokens = chunk_tokens[row["id"]]
        counts = Counter(tokens)
        length = len(tokens) or 1
        score = 0.0
        for token in query_tokens:
            if counts[token] == 0:
                continue
            idf = math.log(1 + (total_chunks - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5))
            numerator = counts[token] * 2.2
            denominator = counts[token] + 1.2 * (0.25 + 0.75 * length / max(avg_length, 1))
            score += idf * numerator / denominator
        if score > 0:
            scores.append({**row, "score": score, "source": "keyword"})
    scores.sort(key=lambda item: item["score"], reverse=True)
    return scores[:limit]


def _semantic_fallback(question: str, allowed_ids: list[str], limit: int) -> list[dict]:
    query_tokens = tokenize(question, expand=True)
    scores = []
    for row in _load_chunks(allowed_ids):
        score = overlap_score(query_tokens, row["content"])
        if score > 0:
            scores.append({**row, "score": score, "source": "semantic"})
    scores.sort(key=lambda item: item["score"], reverse=True)
    return scores[:limit]


def _load_chunks(allowed_ids: list[str]) -> list[dict]:
    placeholders = ",".join("?" for _ in allowed_ids)
    with get_connection() as connection:
        return rows_to_dicts(
            connection.execute(
                f"""
                SELECT c.id, c.document_id, c.document_title, c.page, c.content, c.version
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.document_id IN ({placeholders}) AND d.active = 1
                """,
                allowed_ids,
            ).fetchall()
        )
