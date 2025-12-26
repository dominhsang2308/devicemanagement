from sqlmodel import create_engine, SQLModel, Session
import os
from dotenv import load_dotenv

load_dotenv()

# DATABASE_URL ví dụ: sqlite:///./dev.db hoặc postgresql+psycopg2://user:pass@host/dbname
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

# SQLite cần check_same_thread False
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# create engine
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

def get_engine():
    return engine

def create_db_and_tables():
    """
    Tạo tất cả bảng SQLModel (dùng SQLModel.metadata.create_all).
    Gọi một lần ở startup hoặc chạy python -m app.database để khởi tạo DB.
    IMPORTANT: Không import models ở module này để tránh circular imports.
    """
    # Import models lazily to avoid circular imports when other modules import database
    try:
        # Nếu bạn giữ models trong app.inventory_models, import ở đây
        from app import inventory_models  # noqa: F401
    except Exception:
        # nếu không có module above, ignore (dev scenario)
        pass
    SQLModel.metadata.create_all(engine)

# FastAPI dependency: yield Session
def get_session():
    """
    Dependency để dùng trong FastAPI endpoints:
        def endpoint(session: Session = Depends(get_session)):
            ...
    """
    with Session(engine) as session:
        yield session

if __name__ == "__main__":
    # debug / init helper
    create_db_and_tables()
    print("Database and tables created at", DATABASE_URL)