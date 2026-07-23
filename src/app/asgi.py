"""Entry point. Windows: `python -m src.app.asgi` (Flask dev server).
Deliberately simple: Hypercorn/ASGI wrapping deferred to Phase 5 packaging."""
from .api import app

if __name__ == "__main__":
    import os
    # HOST defaults to loopback for safe local dev (`python -m src.app.asgi`),
    # but must be overridable: inside a container the app has to bind 0.0.0.0
    # or the published port (`-p 8000:8000`) can never reach it. The Dockerfile
    # sets HOST=0.0.0.0 for exactly this reason.
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        threaded=True,
    )
