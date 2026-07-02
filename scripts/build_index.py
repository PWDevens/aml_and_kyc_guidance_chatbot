"""Build the ChromaDB index from eCFR 31 CFR Chapter X + FinCEN FedReg docs.
Run:  python -m scripts.build_index
ponytail: full rebuild each run; incremental upsert is Phase-2 ETL's job."""
from __future__ import annotations

from collections import Counter

from src.rag.config import CONFIG
from src.rag.indexing.builder import build
from src.rag.indexing.loaders import ecfr, fedreg


def main() -> None:
    print(f"Loading eCFR title {CONFIG.ecfr_title} chapter {CONFIG.ecfr_chapter} "
          f"parts {CONFIG.parts} ...")
    ecfr_records = ecfr.load_parts(CONFIG.ecfr_title, CONFIG.ecfr_chapter, CONFIG.parts,
                                    chunk_char_budget=CONFIG.chunk_char_budget)
    print(f"  {len(ecfr_records)} eCFR chunks loaded.")

    print(f"Loading FinCEN FedReg documents (agency={CONFIG.fedreg_agency}, "
          f"since={CONFIG.fedreg_since}, max_docs={CONFIG.fedreg_max_docs}) ...")
    fedreg_records = fedreg.load_documents(CONFIG.fedreg_agency, CONFIG.fedreg_since,
                                            CONFIG.fedreg_max_docs)
    print(f"  {len(fedreg_records)} FedReg documents loaded.")

    records = ecfr_records + fedreg_records
    counts = Counter(r["source"] for r in records)
    print(f"  per-source counts: {dict(counts)}")

    print("Embedding + indexing ...")
    n = build(CONFIG, records)
    print(f"Done. {n} chunks/documents in collection '{CONFIG.collection}' at {CONFIG.chroma_path}")


if __name__ == "__main__":
    main()
