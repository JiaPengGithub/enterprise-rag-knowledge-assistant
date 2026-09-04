from uuid import uuid4

from app.services.retrieval import hybrid_search
from app.services.users import get_user
from app.storage.database import get_connection, rows_to_dicts


EVALUATION_CASES = [
    {
        "name": "HR vacation policy",
        "question": "How many days in advance should employees request planned vacation?",
        "user_id": "hr_user",
        "expected_title": "Employee Handbook",
        "expected_page": 1,
    },
    {
        "name": "IT incident escalation",
        "question": "When should a severity one incident be escalated?",
        "user_id": "it_user",
        "expected_title": "IT Operations Manual",
        "expected_page": 1,
    },
    {
        "name": "Project milestone review",
        "question": "What is the next milestone for Project Orion?",
        "user_id": "pm_user",
        "expected_title": "Project Orion Brief",
        "expected_page": 1,
    },
]


def run_evaluation() -> dict:
    results = []
    with get_connection() as connection:
        for case in EVALUATION_CASES:
            user = get_user(case["user_id"])
            if not user:
                continue
            retrieved = hybrid_search(case["question"], user)
            expected = _find_document_by_title(connection, case["expected_title"])
            expected_id = expected["id"] if expected else ""
            ranks = [index for index, chunk in enumerate(retrieved, start=1) if chunk["document_id"] == expected_id]
            hit = bool(ranks)
            reciprocal_rank = 1 / ranks[0] if ranks else 0.0
            citation_covered = hit and any(chunk.get("page") == case["expected_page"] for chunk in retrieved[:3])
            record = {
                "id": uuid4().hex,
                "name": case["name"],
                "question": case["question"],
                "user_id": case["user_id"],
                "expected_document_id": expected_id,
                "expected_page": case["expected_page"],
                "hit": int(hit),
                "reciprocal_rank": reciprocal_rank,
                "citation_covered": int(citation_covered),
            }
            connection.execute(
                """
                INSERT INTO evaluations
                (id, name, question, user_id, expected_document_id, expected_page, hit, reciprocal_rank, citation_covered)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["name"],
                    record["question"],
                    record["user_id"],
                    record["expected_document_id"],
                    record["expected_page"],
                    record["hit"],
                    record["reciprocal_rank"],
                    record["citation_covered"],
                ),
            )
            results.append(record)
    return {
        "total": len(results),
        "hit_rate": _average(item["hit"] for item in results),
        "mrr": _average(item["reciprocal_rank"] for item in results),
        "citation_coverage": _average(item["citation_covered"] for item in results),
        "results": results,
    }


def list_evaluations(limit: int = 50) -> list[dict]:
    with get_connection() as connection:
        return rows_to_dicts(connection.execute("SELECT * FROM evaluations ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall())


def _find_document_by_title(connection, title: str) -> dict | None:
    row = connection.execute("SELECT * FROM documents WHERE title = ? AND active = 1", (title,)).fetchone()
    return dict(row) if row else None


def _average(values) -> float:
    values = list(values)
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)
