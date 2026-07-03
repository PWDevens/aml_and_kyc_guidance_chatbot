# -----------------------------------------------------------------------------
# AUTHORED, NOT BUILT/RUN IN THIS ENVIRONMENT.
# Docker is not installed on the machine this file was authored on (verified:
# `docker --version` -> command not found, both Bash and PowerShell). This
# Dockerfile has been reviewed for internal correctness and consistency with
# the locally-verified run (README "Quickstart", .build/iter-5/test-results.md
# AC-5) but has never been `docker build`/`docker run`-executed. Verify on a
# Docker-enabled host before relying on it. See docker/docker-compose.yml and
# README "Docker" section for the matching run story.
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

# Flask dev server, same as the locally-verified `python -m src.app.asgi`
# entrypoint (README Quickstart). Hypercorn/ASGI wrapping is documented
# (docs/ARCHITECTURE.md §9) as a later packaging option but was not built
# this iteration — the Flask dev server is adequate for a local/single-user
# CPU demo image and keeps this Dockerfile consistent with the one path that
# was actually run and verified (AC-5/AC-7), rather than introducing an
# unverified second server.
CMD ["python", "-m", "src.app.asgi"]
