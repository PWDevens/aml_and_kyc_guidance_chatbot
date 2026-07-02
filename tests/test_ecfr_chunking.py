"""One runnable check: section-aware chunking (`_split_section`) packs
paragraphs into <= budget chunks without ever splitting inside a paragraph,
and leaves short sections untouched.
Run:  python -m pytest tests/test_ecfr_chunking.py -q"""
from src.rag.indexing.loaders.ecfr import _split_section


def test_short_section_stays_one_chunk():
    text = "para one\npara two"
    assert _split_section(text, budget=1500) == [text]


def test_long_section_splits_on_paragraph_boundaries():
    paras = [f"paragraph {i} " + ("x" * 100) for i in range(10)]
    text = "\n".join(paras)
    chunks = _split_section(text, budget=300)
    assert len(chunks) > 1
    # every paragraph survives whole, in order, across the reassembled chunks
    assert "\n".join(chunks).replace("\n\n", "\n") == text or "\n".join(chunks) == text
    for chunk in chunks:
        assert len(chunk) <= 300 or "\n" not in chunk  # oversized only if a single para


def test_no_paragraph_split_mid_clause():
    paras = ["A" * 400, "B" * 400, "C" * 400]
    text = "\n".join(paras)
    chunks = _split_section(text, budget=500)
    rejoined_paras = "\n".join(chunks).split("\n")
    assert rejoined_paras == paras


if __name__ == "__main__":
    test_short_section_stays_one_chunk()
    test_long_section_splits_on_paragraph_boundaries()
    test_no_paragraph_split_mid_clause()
    print("chunking ok")
