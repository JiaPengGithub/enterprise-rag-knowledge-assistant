import time
from uuid import uuid4

from app.core.config import get_settings
from app.services.retrieval import hybrid_search
from app.services.users import get_user
from app.services.vector_store import AI_RUNTIME_STATUS, overlap_score, tokenize
from app.storage.database import dumps, get_connection, loads, rows_to_dicts


INSUFFICIENT_EVIDENCE_MESSAGE = "I do not have enough information in the available documents to answer this reliably."


def answer_question(question: str, user_id: str) -> dict:
    started = time.perf_counter()
    user = get_user(user_id)
    if not user:
        raise ValueError("Unknown demo user.")
    retrieved = hybrid_search(question, user)
    evidence_score = _evidence_score(question, retrieved)
    if not retrieved or evidence_score < get_settings().evidence_threshold:
        answer = INSUFFICIENT_EVIDENCE_MESSAGE
        status = "insufficient_evidence"
        citations: list[dict] = []
    else:
        citations = [_citation(chunk) for chunk in retrieved[:3]]
        answer = _generate_answer(question, retrieved[:3], citations)
        status = "answered"
    latency_ms = int((time.perf_counter() - started) * 1000)
    payload = {
        "answer": answer,
        "status": status,
        "citations": citations,
        "retrieved_chunks": [_public_chunk(chunk) for chunk in retrieved],
        "latency_ms": latency_ms,
    }
    _log_query(user_id, question, payload)
    return payload


def list_logs(user_id: str, limit: int = 50) -> list[dict]:
    user = get_user(user_id)
    if not user:
        raise ValueError("Unknown demo user.")
    params: tuple = (limit,)
    where_clause = ""
    if "admin" not in set(user["roles"]):
        where_clause = "WHERE user_id = ?"
        params = (user_id, limit)
    with get_connection() as connection:
        rows = rows_to_dicts(
            connection.execute(
                f"SELECT * FROM query_logs {where_clause} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        )
    for row in rows:
        row["retrieved_chunks"] = loads(row["retrieved_chunks"], [])
        row["citations"] = loads(row["citations"], [])
    return rows


def _generate_answer(question: str, chunks: list[dict], citations: list[dict]) -> str:
    model_answer = _try_model_answer(question, chunks)
    if model_answer:
        return model_answer
    lead = _best_sentence(question, chunks[0]["content"])
    source_refs = ", ".join(f"{item['document_title']} p. {item['page'] or 'n/a'}" for item in citations)
    return f"{lead} Sources: {source_refs}."


def _try_model_answer(question: str, chunks: list[dict]) -> str | None:
    settings = get_settings()
    AI_RUNTIME_STATUS["chat_configured"] = bool(settings.openai_api_key)
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None)
        context = "\n\n".join(
            f"[{index}] {chunk['document_title']} page {chunk['page'] or 'n/a'}: {chunk['content']}"
            for index, chunk in enumerate(chunks, start=1)
        )
        response = client.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": "Answer only from the provided enterprise documents. If the documents are insufficient, say so in English.",
                },
                {"role": "user", "content": f"Question: {question}\n\nDocuments:\n{context}"},
            ],
            temperature=0.1,
        )
        AI_RUNTIME_STATUS.update({"chat_verified": True, "chat_mode": "openai", "chat_last_error": None})
        return response.choices[0].message.content
    except Exception as exc:
        AI_RUNTIME_STATUS.update({"chat_verified": False, "chat_mode": "local_fallback", "chat_last_error": str(exc)})
        return None


def _best_sentence(question: str, content: str) -> str:
    query_tokens = tokenize(question, expand=True)
    sentences = [sentence.strip() for sentence in content.replace("\n", " ").split(".") if sentence.strip()]
    if not sentences:
        return content[:400]
    sentences.sort(key=lambda sentence: overlap_score(query_tokens, sentence), reverse=True)
    return sentences[0] + "."


def _evidence_score(question: str, chunks: list[dict]) -> float:
    query_tokens = tokenize(question, expand=True)
    if not chunks:
        return 0.0
    return max(overlap_score(query_tokens, chunk["content"]) for chunk in chunks)


def _citation(chunk: dict) -> dict:
    return {
        "document_id": chunk["document_id"],
        "document_title": chunk["document_title"],
        "page": chunk["page"],
        "chunk_id": chunk["id"],
        "excerpt": chunk["content"][:500],
        "version": chunk["version"],
    }


def _public_chunk(chunk: dict) -> dict:
    return {
        "chunk_id": chunk["id"],
        "document_id": chunk["document_id"],
        "document_title": chunk["document_title"],
        "page": chunk["page"],
        "excerpt": chunk["content"][:500],
        "score": round(float(chunk["score"]), 4),
        "sources": chunk.get("sources", [chunk.get("source", "unknown")]),
        "version": chunk["version"],
    }


def _log_query(user_id: str, question: str, payload: dict) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO query_logs (id, user_id, question, answer, status, retrieved_chunks, citations, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid4().hex,
                user_id,
                question,
                payload["answer"],
                payload["status"],
                dumps(payload["retrieved_chunks"]),
                dumps(payload["citations"]),
                payload["latency_ms"],
            ),
        )
