from io import BytesIO

from fastapi.testclient import TestClient

from app.main import create_app


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
        data={"title": "Badge Policy", "department": "Security", "roles": "employee"},
        files={"file": ("badge_policy.txt", file, "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Badge Policy"
    assert body["version"] == 1


def test_evaluation_api_returns_metrics(isolated_app):
    client = TestClient(create_app())

    response = client.post("/api/evaluations/run")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert "hit_rate" in body
