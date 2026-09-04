import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.services.chunking import chunk_pages
from app.services.parsing import parse_document
from app.services.vector_store import ChromaIndex
from app.storage.database import dumps, get_connection, loads, row_to_dict, rows_to_dicts


def list_documents() -> list[dict]:
    with get_connection() as connection:
        rows = rows_to_dicts(
            connection.execute(
                """
                SELECT d.*, COUNT(c.id) AS chunk_count
                FROM documents d
                LEFT JOIN chunks c ON c.document_id = d.id
                WHERE d.active = 1
                GROUP BY d.id
                ORDER BY d.updated_at DESC
                """
            ).fetchall()
        )
    for row in rows:
        row["roles"] = loads(row["roles"], [])
    return rows


def create_document_from_upload(file: UploadFile, title: str, department: str, roles: list[str]) -> dict:
    settings = get_settings()
    document_id = uuid4().hex
    safe_name = Path(file.filename or "document.txt").name
    storage_path = settings.upload_dir / f"{document_id}_{safe_name}"
    with storage_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    return ingest_document(storage_path, title, department, roles, document_id=document_id, source_filename=safe_name)


def ingest_document(
    storage_path: Path,
    title: str,
    department: str,
    roles: list[str],
    document_id: str | None = None,
    source_filename: str | None = None,
    version: int = 1,
) -> dict:
    document_id = document_id or uuid4().hex
    source_filename = source_filename or storage_path.name
    pages = parse_document(storage_path)
    chunks = chunk_pages(document_id, version, pages)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO documents (id, title, department, roles, source_filename, storage_path, version, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                department = excluded.department,
                roles = excluded.roles,
                source_filename = excluded.source_filename,
                storage_path = excluded.storage_path,
                version = excluded.version,
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (document_id, title, department, dumps(roles), source_filename, str(storage_path), version),
        )
        connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        chunk_rows = []
        for chunk in chunks:
            connection.execute(
                """
                INSERT INTO chunks (id, document_id, document_title, page, content, version, token_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (chunk.id, document_id, title, chunk.page, chunk.content, version, chunk.token_count),
            )
            chunk_rows.append(
                {
                    "id": chunk.id,
                    "document_id": document_id,
                    "document_title": title,
                    "page": chunk.page,
                    "content": chunk.content,
                    "version": version,
                }
            )
    index = ChromaIndex()
    index.delete_document(document_id)
    index.upsert(chunk_rows)
    return get_document(document_id) or {}


def update_document(document_id: str, title: str | None, department: str | None, roles: list[str] | None) -> dict | None:
    existing = get_document(document_id)
    if not existing:
        return None
    next_title = title or existing["title"]
    next_department = department or existing["department"]
    next_roles = roles or existing["roles"]
    return ingest_document(
        Path(existing["storage_path"]),
        next_title,
        next_department,
        next_roles,
        document_id=document_id,
        source_filename=existing["source_filename"],
        version=existing["version"] + 1,
    )


def delete_document(document_id: str) -> bool:
    with get_connection() as connection:
        result = connection.execute("UPDATE documents SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (document_id,))
        connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
    ChromaIndex().delete_document(document_id)
    return result.rowcount > 0


def get_document(document_id: str) -> dict | None:
    with get_connection() as connection:
        row = row_to_dict(connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone())
    if row:
        row["roles"] = loads(row["roles"], [])
    return row


def seed_sample_documents() -> None:
    settings = get_settings()
    existing = list_documents()
    if existing:
        return
    samples = [
        ("employee_handbook.md", "Employee Handbook", "Human Resources", ["hr"]),
        ("it_operations_manual.md", "IT Operations Manual", "IT", ["it"]),
        ("project_orion_brief.md", "Project Orion Brief", "Product", ["project"]),
    ]
    for filename, title, department, roles in samples:
        path = settings.sample_docs_dir / filename
        if path.exists():
            ingest_document(path, title, department, roles)
