import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.factory import create_app
from app.config.models import DataCacheConfig
from app.db.base import Base
from app.db.session import get_db_session


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def build_backtest_client(tmp_path: Path) -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override_db_session():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app(
        cache_config=DataCacheConfig(directory=str(tmp_path / "cache")),
        output_dir=tmp_path / "api-results",
        log_file=tmp_path / "api.log",
        session_factory=test_session_factory,
    )
    app.dependency_overrides[get_db_session] = override_db_session
    return TestClient(app)
