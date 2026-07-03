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
    # Phase-1: FinCEN Federal Register static loader (ARCHITECTURE §10)
    fedreg_agency: str = os.getenv("FEDREG_AGENCY", "financial-crimes-enforcement-network")
    fedreg_since: str = os.getenv("FEDREG_SINCE", "2020-01-01")
    fedreg_max_docs: int = int(os.getenv("FEDREG_MAX_DOCS", "50"))
    # Phase-1: section-aware chunking budget (chars), safely under CONTEXT_CHAR_BUDGET
    chunk_char_budget: int = int(os.getenv("CHUNK_CHAR_BUDGET", "1500"))
    # Phase-1: exact-match answer cache (Tier-2; semantic FAQ tier is Phase 3)
    answer_cache: bool = _b("ANSWER_CACHE", "true")
    cache_path: str = os.getenv("ANSWER_CACHE_PATH", str(ROOT / "data" / "cache.db"))
    # Phase-2: ETL watermarks + provenance ledger (docs/ETL_AND_TRIGGERS.md §4)
    etl_state_path: str = os.getenv("ETL_STATE_PATH", str(ROOT / "data" / "etl_state.db"))
    etl_schedule: str = os.getenv("ETL_SCHEDULE", "daily")
    etl_fedreg_since: str = os.getenv("ETL_FEDREG_SINCE", "2020-01-01")
    etl_ecfr_since: str = os.getenv("ETL_ECFR_SINCE", "2020-01-01")
    # Phase-3: local-first orchestration layer + semantic FAQ cache
    # (docs/AGENT_ORCHESTRATION.md, docs/FAQ_CACHE.md). ORCHESTRATION ships
    # false this iteration (D6) — flip only after the on-vs-off eval (AC-9)
    # shows a win; FAQ_CACHE ships true (D7) since Tier-1 only ever serves
    # human-curated, pre-verified answers.
    orchestration: bool = _b("ORCHESTRATION", "false")
    faq_cache: bool = _b("FAQ_CACHE", "true")
    faq_db_path: str = os.getenv("FAQ_DB_PATH", str(ROOT / "data" / "faq.db"))
    # D3: measured against real paraphrase/off-topic bands on bge-small — see
    # changes.md. 0.83 sits above the measured off-topic ceiling (~0.70) with
    # margin and admits genuine paraphrases (docs' proposed 0.92 was too high
    # and would miss almost every real paraphrase).
    faq_sim_threshold: float = float(os.getenv("FAQ_SIM_THRESHOLD", "0.83"))
    faq_topic_crosscheck: bool = _b("FAQ_TOPIC_CROSSCHECK", "true")
    faq_stale_policy: str = os.getenv("FAQ_STALE_POLICY", "suppress")
    verify_answers: bool = _b("VERIFY_ANSWERS", "true")
    orchestration_max_llm_calls: int = int(os.getenv("ORCHESTRATION_MAX_LLM_CALLS", "2"))

    @property
    def parts(self) -> list[str]:
        return [p.strip() for p in self.ecfr_parts.split(",") if p.strip()]


CONFIG = RagConfig()
