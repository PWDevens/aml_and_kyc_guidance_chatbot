"""Build the ChromaDB index from eCFR 31 CFR Chapter X.
Run:  python -m scripts.build_index
ponytail: full rebuild each run; incremental upsert is Phase-2 ETL's job."""
from __future__ import annotations

from src.rag.config import CONFIG
from src.rag.indexing.builder import build
from src.rag.indexing.loaders import ecfr


def main() -> None:
    print(f"Loading eCFR title {CONFIG.ecfr_title} chapter {CONFIG.ecfr_chapter} "
          f"parts {CONFIG.parts} ...")
    records = ecfr.load_parts(CONFIG.ecfr_title, CONFIG.ecfr_chapter, CONFIG.parts)
    print(f"  {len(records)} sections loaded. Embedding + indexing ...")
    n = build(CONFIG, records)
    print(f"Done. {n} sections in collection '{CONFIG.collection}' at {CONFIG.chroma_path}")


if __name__ == "__main__":
    main()
