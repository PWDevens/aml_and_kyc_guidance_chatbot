"""Entry point. Windows: `python -m src.app.asgi` (Flask dev server).
ponytail: Hypercorn/ASGI wrapping deferred to Phase 5 packaging."""
from .api import app

if __name__ == "__main__":
    import os
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "8000")), threaded=True)
