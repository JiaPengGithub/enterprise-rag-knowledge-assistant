from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.schemas import ChatRequest, DocumentUpdate
from app.services.answering import list_logs
from app.services.documents import create_document_from_upload, delete_document, list_documents, update_document
from app.services.evaluation import list_evaluations, run_evaluation
from app.services.users import get_user, list_users
from app.services.vector_store import ai_runtime_status
from app.services.workflow import run_query_workflow

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ai/status")
def ai_status() -> dict:
    return ai_runtime_status()


@router.get("/users/demo")
def demo_users() -> list[dict]:
    return list_users()


@router.get("/documents")
def documents(user_id: str = Query("hr_user")) -> list[dict]:
    user = _require_demo_user(user_id)
    return list_documents(user)


@router.post("/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    department: str = Form("General"),
    roles: str = Form("employee"),
    classification: str = Form("internal"),
    user_id: str = Form(...),
) -> dict:
    _require_admin(user_id)
    role_list = [role.strip() for role in roles.split(",") if role.strip()]
    try:
        return create_document_from_upload(file, title, department, role_list, classification)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/documents/{document_id}")
def patch_document(document_id: str, payload: DocumentUpdate) -> dict:
    _require_admin(payload.user_id)
    updated = update_document(document_id, payload.title, payload.department, payload.roles, payload.classification)
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found.")
    return updated


@router.delete("/documents/{document_id}")
def remove_document(document_id: str, user_id: str = Query(...)) -> dict:
    _require_admin(user_id)
    if not delete_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"status": "deleted"}


@router.post("/chat")
def chat(payload: ChatRequest) -> dict:
    try:
        return run_query_workflow(payload.question, payload.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/chat/logs")
def chat_logs(user_id: str = Query("hr_user")) -> list[dict]:
    try:
        return list_logs(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/evaluations")
def evaluations() -> list[dict]:
    return list_evaluations()


@router.post("/evaluations/run")
def run_evaluations() -> dict:
    return run_evaluation()


def _require_demo_user(user_id: str) -> dict:
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Unknown demo user.")
    return user


def _require_admin(user_id: str) -> dict:
    user = _require_demo_user(user_id)
    if "admin" not in set(user["roles"]):
        raise HTTPException(status_code=403, detail="Admin demo user required for document management.")
    return user
