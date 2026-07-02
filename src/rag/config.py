"""RagConfig — env-driven knobs. Only what Phase 0 actually reads.
More vars (RERANK, ORCHESTRATION, FAQ_CACHE...) land in the phase that uses them.
ponytail: one dataclass from env, no config framework."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _b(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class RagConfig:
    rag_mode: str = os.getenv("RAG_MODE", "naive")
    embed_model: str = os.getenv("EMBED_MODEL_NAME", "BAAI/bge-small-en-v1.5")
    chroma_path: str = os.getenv("CHROMA_PATH", str(ROOT / "data" / "chroma"))
    collection: str = os.getenv("CHROMA_COLLECTION", "aml_kyc")
    retrieval_top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
    max_new_tokens: int = int(os.getenv("MAX_NEW_TOKENS", "400"))
    # eCFR scope (ARCHITECTURE §8)
    ecfr_title: str = os.getenv("ECFR_TITLE", "31")
    ecfr_chapter: str = os.getenv("ECFR_CHAPTER", "X")
    # Phase-0 keeps the corpus small & fast: a few core BSA parts unless overridden.
    ecfr_parts: str = os.getenv("ECFR_PARTS", "1010,1020")
    generate: bool = _b("GENERATE", "true")

    @property
    def parts(self) -> list[str]:
        return [p.strip() for p in self.ecfr_parts.split(",") if p.strip()]


CONFIG = RagConfig()
