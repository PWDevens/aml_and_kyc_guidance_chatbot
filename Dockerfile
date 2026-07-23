# -----------------------------------------------------------------------------
# BUILT AND RUN (verified 2026-07-23 on a Docker-enabled host).
# `docker build .` produces a ~9.4 GB image (in-container index build ~84s,
# 402 chunks); the running container serves /healthz, /corpus_status, and
# /chat_stream (FAQ fast-path + live Phi-4 generation, HTTP 200). The same
# `docker build` runs green in CI (.github/workflows/ci.yml docker-build job).
# The original machine had no Docker, so earlier revisions were authored but
# never executed — that caveat no longer applies. See docker/docker-compose.yml
# and README "Docker" for the matching run story.
# -----------------------------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# System deps: none beyond what the slim base + pip wheels need for this
# stack (chromadb/sentence-transformers/onnxruntime-genai all ship manylinux
# wheels for this base image; no compiler toolchain required).

# Install pinned deps first (better layer caching across code-only changes).
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

# Bound HuggingFace Hub network waits so a stalled model download (the embedder
# pulled by the index build below, or Phi-4 pulled on the container's first
# generate) fails fast instead of hanging indefinitely. Set before the build
# step so it applies there too; mirrors the defaults in src/rag/config.py and
# stays overridable at run time.
ENV HF_HUB_DOWNLOAD_TIMEOUT=30
ENV HF_HUB_ETAG_TIMEOUT=30

# Index strategy (see "Edge cases" in .build/iter-5/spec.md §6): the ChromaDB
# index and FAQ db are gitignored (data/chroma/, data/*.db) — never committed
# — so the image builds them itself at image-build time from the live eCFR +
# Federal Register APIs. This makes the image self-contained (matches the
# README's "one-command run" story) at the cost of a slower, network-dependent
# build. The alternative (mount a pre-built data/ as a volume) is documented
# in docker/docker-compose.yml's commented-out `volumes:` block for anyone who
# prefers not to rebuild the corpus inside the image.
RUN python -m scripts.build_index && python -m scripts.seed_faq

EXPOSE 8000

ENV PORT=8000
# Bind all interfaces inside the container so the published port (-p 8000:8000)
# is reachable from the host. src/app/asgi.py defaults HOST to 127.0.0.1 for
# safe local dev; the container must override it to 0.0.0.0.
ENV HOST=0.0.0.0

# Flask dev server, same as the locally-verified `python -m src.app.asgi`
# entrypoint (README Quickstart). Hypercorn/ASGI wrapping is documented
# (docs/ARCHITECTURE.md §9) as a later packaging option but was not built
# this iteration — the Flask dev server is adequate for a local/single-user
# CPU demo image and keeps this Dockerfile consistent with the one path that
# was actually run and verified (AC-5/AC-7), rather than introducing an
# unverified second server.
CMD ["python", "-m", "src.app.asgi"]
