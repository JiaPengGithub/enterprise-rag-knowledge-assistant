import sqlite3
from io import BytesIO

from fastapi.testclient import TestClient

from app.main import create_app


def test_init_db_adds_classification_to_existing_documents_table(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            department TEXT NOT NULL,
            roles TEXT NOT NULL,
            source_filename TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    from app.core.config import get_settings
    from app.storage.database import init_db

    get_settings.cache_clear()
    init_db()

    connection = sqlite3.connect(database_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()}
    connection.close()
    get_settings.cache_clear()

    assert "classification" in columns


def test_chat_api_returns_citations(isolated_app):
    client = TestClient(create_app())

    response = client.post(
        "/api/chat",
        json={"question": "How many days in advance should employees request planned vacation?", "user_id": "hr_user"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["citations"]
    assert body["citations"][0]["document_title"] == "Employee Handbook"


def test_upload_document_api(isolated_app):
    client = TestClient(create_app())
    file = BytesIO(b"Security badges must be returned on the final day of employment.")

    response = client.post(
        "/api/documents/upload",
        data={
            "title": "Badge Policy",
            "department": "Security",
            "roles": "employee",
            "classification": "public",
            "user_id": "admin",
        },
        files={"file": ("badge_policy.txt", file, "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Badge Policy"
    assert body["classification"] == "public"
    assert body["version"] == 1


def test_document_management_requires_admin_demo_user(isolated_app):
    client = TestClient(create_app())
    file = BytesIO(b"Only admins should be allowed to add this document.")

    upload_response = client.post(
        "/api/documents/upload",
        data={
            "title": "Restricted Upload",
            "department": "Security",
            "roles": "employee",
            "classification": "public",
            "user_id": "hr_user",
        },
        files={"file": ("restricted.txt", file, "text/plain")},
    )

    assert upload_response.status_code == 403

    document_id = client.get("/api/documents", params={"user_id": "admin"}).json()[0]["id"]
    patch_response = client.patch(f"/api/documents/{document_id}", json={"user_id": "it_user", "classification": "public"})
    delete_response = client.delete(f"/api/documents/{document_id}", params={"user_id": "pm_user"})

    assert patch_response.status_code == 403
    assert delete_response.status_code == 403


def test_update_document_classification_api(isolated_app):
    client = TestClient(create_app())
    documents = client.get("/api/documents", params={"user_id": "admin"}).json()
    document_id = documents[0]["id"]

    response = client.patch(f"/api/documents/{document_id}", json={"user_id": "admin", "classification": "public"})

    assert response.status_code == 200
    body = response.json()
    assert body["classification"] == "public"


def test_documents_are_filtered_by_demo_user_access(isolated_app):
    client = TestClient(create_app())

    hr_documents = client.get("/api/documents", params={"user_id": "hr_user"}).json()
    it_documents = client.get("/api/documents", params={"user_id": "it_user"}).json()
    admin_documents = client.get("/api/documents", params={"user_id": "admin"}).json()

    assert {item["title"] for item in hr_documents} == {"Employee Handbook"}
    assert {item["title"] for item in it_documents} == {"IT Operations Manual"}
    assert {item["title"] for item in admin_documents} == {
        "Employee Handbook",
        "IT Operations Manual",
        "Project Orion Brief",
    }


def test_startup_repairs_legacy_sample_document_access(isolated_app):
    from app.services.documents import seed_sample_documents
    from app.storage.database import dumps, get_connection

    with get_connection() as connection:
        connection.execute(
            "UPDATE documents SET classification = 'internal', roles = ? WHERE source_filename = ?",
            (dumps(["employee"]), "it_operations_manual.md"),
        )

    seed_sample_documents()
    client = TestClient(create_app())
    hr_documents = client.get("/api/documents", params={"user_id": "hr_user"}).json()

    assert {item["title"] for item in hr_documents} == {"Employee Handbook"}


def test_query_logs_are_filtered_by_demo_user(isolated_app):
    client = TestClient(create_app())
    client.post(
        "/api/chat",
        json={"question": "How many days in advance should employees request planned vacation?", "user_id": "hr_user"},
    )
    client.post(
        "/api/chat",
        json={"question": "When should a severity one incident be escalated?", "user_id": "it_user"},
    )

    hr_logs = client.get("/api/chat/logs", params={"user_id": "hr_user"}).json()
    admin_logs = client.get("/api/chat/logs", params={"user_id": "admin"}).json()

    assert len(hr_logs) == 1
    assert hr_logs[0]["user_id"] == "hr_user"
    assert len(admin_logs) == 2


def test_deleted_document_is_not_retrieved_by_generic_remaining_terms(isolated_app):
    client = TestClient(create_app())
    file = BytesIO(b"Persistence probe token alpha-seven is retained after restart.")
    upload = client.post(
        "/api/documents/upload",
        data={
            "title": "Persistence Probe",
            "department": "IT",
            "roles": "it",
            "classification": "confidential",
            "user_id": "admin",
        },
        files={"file": ("persist.txt", file, "text/plain")},
    ).json()

    before_delete = client.post(
        "/api/chat",
        json={"question": "What probe token is retained after restart?", "user_id": "it_user"},
    ).json()
    client.delete(f"/api/documents/{upload['id']}", params={"user_id": "admin"})
    after_delete = client.post(
        "/api/chat",
        json={"question": "What probe token is retained after restart?", "user_id": "it_user"},
    ).json()

    assert before_delete["status"] == "answered"
    assert before_delete["citations"][0]["document_title"] == "Persistence Probe"
    assert after_delete["status"] == "insufficient_evidence"
    assert after_delete["citations"] == []


def test_ai_status_marks_missing_credentials_as_unverified_fallback(isolated_app):
    client = TestClient(create_app())

    response = client.get("/api/ai/status")

    assert response.status_code == 200
    body = response.json()
    assert body["embedding_configured"] is False
    assert body["embedding_verified"] is False
    assert body["embedding_mode"] == "local_fallback"


def test_evaluation_api_returns_metrics(isolated_app):
    client = TestClient(create_app())

    response = client.post("/api/evaluations/run")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert "hit_rate" in body
