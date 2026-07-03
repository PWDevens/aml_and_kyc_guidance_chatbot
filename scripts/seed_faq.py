"""Build data/faq.db from the committed data/faq_seed.yaml (AC-11).
Run:  python -m scripts.seed_faq

Idempotent: upsert_entry does INSERT OR REPLACE keyed on entry id, so
re-running with the same YAML yields the same final store contents. Reuses
embed_queries (D1) so FAQ question/paraphrase vectors and the request-time
query vector come from the identical model — required for cosine to be
meaningful (D2)."""
from __future__ import annotations

from pathlib import Path

import yaml

from src.rag.config import CONFIG
from src.rag.faq import store
from src.rag.faq.embed import embed_queries

SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "faq_seed.yaml"


def main() -> None:
    entries = yaml.safe_load(SEED_PATH.read_text(encoding="utf-8")) or []
    print(f"Seeding {len(entries)} FAQ entries from {SEED_PATH} into {CONFIG.faq_db_path} ...")

    for entry in entries:
        strings = [entry["canonical_question"], *entry.get("paraphrases", [])]
        embeddings = embed_queries(strings, CONFIG.embed_model)
        store.upsert_entry(CONFIG, entry, embeddings)
        print(f"  {entry['id']}: {len(strings)} vectors embedded")

    print(f"Done. {len(entries)} entries in {CONFIG.faq_db_path}")


if __name__ == "__main__":
    main()
