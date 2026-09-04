from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas import ChatRequest, DocumentUpdate
from app.services.answering import list_logs
from app.services.documents import create_document_from_upload, delete_document, list_documents, update_document
from app.services.evaluation import list_evaluations, run_evaluation
from app.services.users import list_users
from app.services.workflow import run_query_workflow

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/users/demo")
def demo_users() -> list[dict]:
    return list_users()


@router.get("/documents")
def documents() -> list[dict]:
    return list_documents()


@router.post("/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    department: str = Form("General"),
    roles: str = Form("employee"),
) -> dict:
    role_list = [role.strip() for role in roles.split(",") if role.strip()]
    try:
        return create_document_from_upload(file, title, department, role_list)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/documents/{document_id}")
def patch_document(document_id: str, payload: DocumentUpdate) -> dict:
    updated = update_document(document_id, payload.title, payload.department, payload.roles)
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found.")
    return updated


@router.delete("/documents/{document_id}")
def remove_document(document_id: str) -> dict:
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
def chat_logs() -> list[dict]:
    return list_logs()


@router.get("/evaluations")
def evaluations() -> list[dict]:
    return list_evaluations()


@router.post("/evaluations/run")
def run_evaluations() -> dict:
    return run_evaluation()
