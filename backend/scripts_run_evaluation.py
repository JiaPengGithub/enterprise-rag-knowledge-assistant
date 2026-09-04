from app.storage.database import ensure_data_dirs, init_db
from app.services.documents import seed_sample_documents
from app.services.evaluation import run_evaluation
from app.services.users import seed_users


if __name__ == "__main__":
    ensure_data_dirs()
    init_db()
    seed_users()
    seed_sample_documents()
    print(run_evaluation())
