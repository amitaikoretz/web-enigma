from app.api.factory import create_app

app = create_app()

__all__ = ["create_app", "app"]
