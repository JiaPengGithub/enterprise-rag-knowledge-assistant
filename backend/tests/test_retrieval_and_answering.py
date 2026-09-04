import sys
from types import SimpleNamespace

from app.services.answering import INSUFFICIENT_EVIDENCE_MESSAGE, answer_question
from app.services.documents import ingest_document
from app.services.vector_store import embed_texts, openai_collection_name
from app.services.retrieval import allowed_document_ids, can_access_document, hybrid_search
from app.services.users import get_user


def test_permission_filter_excludes_hr_document_for_it_user(isolated_app):
    user = get_user("it_user")
    results = hybrid_search("planned vacation requests", user)

    assert all(result["document_title"] != "Employee Handbook" for result in results)


def test_permission_filter_allows_hr_document_for_hr_user(isolated_app):
    user = get_user("hr_user")
    results = hybrid_search("planned vacation requests ten business days", user)

    assert any(result["document_title"] == "Employee Handbook" for result in results)


def test_admin_can_access_all_seed_documents(isolated_app):
    user = get_user("admin")
    ids = allowed_document_ids(user)

    assert len(ids) == 3


def test_public_document_is_visible_to_all_demo_users(isolated_app, tmp_path):
    document = _ingest_text_document(tmp_path, "cafeteria", "Cafeteria Menu", "Facilities", [], "public")

    for user_id in ["hr_user", "it_user", "pm_user", "admin"]:
        assert document["id"] in allowed_document_ids(get_user(user_id))


def test_internal_document_is_visible_to_employee_users(isolated_app, tmp_path):
    document = _ingest_text_document(tmp_path, "office_map", "Office Map", "Facilities", [], "internal")

    assert document["id"] in allowed_document_ids(get_user("hr_user"))
    assert document["id"] in allowed_document_ids(get_user("admin"))


def test_confidential_document_allows_same_department(isolated_app):
    user = get_user("hr_user")
    document = {"department": "Human Resources", "roles": [], "classification": "confidential"}

    assert can_access_document(user, document)


def test_confidential_document_allows_matching_role(isolated_app):
    user = get_user("pm_user")
    document = {"department": "Finance", "roles": ["project"], "classification": "confidential"}

    assert can_access_document(user, document)


def test_confidential_document_blocks_cross_department_without_matching_role(isolated_app, tmp_path):
    _ingest_text_document(
        tmp_path,
        "payroll",
        "Payroll Forecast",
        "Finance",
        ["finance"],
        "confidential",
        "Payroll forecast includes a confidential retention budget for finance leadership.",
    )

    response = answer_question("zephyr payroll forecast retention budget", "it_user")

    assert all(chunk["document_title"] != "Payroll Forecast" for chunk in response["retrieved_chunks"])
    assert all(citation["document_title"] != "Payroll Forecast" for citation in response["citations"])


def test_insufficient_evidence_uses_english_fallback(isolated_app):
    response = answer_question("What is the cafeteria menu for next Friday?", "hr_user")

    assert response["status"] == "insufficient_evidence"
    assert response["answer"] == INSUFFICIENT_EVIDENCE_MESSAGE
    assert response["citations"] == []


def test_embedding_uses_openai_when_api_key_is_configured(isolated_app, monkeypatch):
    from app.core.config import get_settings

    calls = {}

    class FakeEmbeddings:
        def create(self, model, input):
            calls["model"] = model
            calls["input"] = input
            return SimpleNamespace(
                data=[
                    SimpleNamespace(embedding=[0.1, 0.2, 0.3]),
                    SimpleNamespace(embedding=[0.4, 0.5, 0.6]),
                ]
            )

    class FakeOpenAI:
        def __init__(self, api_key, base_url):
            calls["api_key"] = api_key
            calls["base_url"] = base_url
            self.embeddings = FakeEmbeddings()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    get_settings.cache_clear()
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    embeddings, collection_name = embed_texts(["first", "second"])

    assert embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert collection_name == openai_collection_name(get_settings().embedding_model)
    assert calls == {
        "api_key": "test-key",
        "base_url": "https://example.test/v1",
        "model": "text-embedding-3-small",
        "input": ["first", "second"],
    }


def _ingest_text_document(
    tmp_path,
    filename: str,
    title: str,
    department: str,
    roles: list[str],
    classification: str,
    content: str = "This shared document is available for permission model testing.",
) -> dict:
    path = tmp_path / f"{filename}.txt"
    path.write_text(content, encoding="utf-8")
    return ingest_document(path, title, department, roles, classification=classification)
