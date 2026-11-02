"""Text normalization and recursive sentence-aware chunking with overlap."""

from hashlib import sha256
import re
import unicodedata

from .models import TextUnit


def normalize_text(text: str) -> str:
    """Normalize text into Unicode NFC form, strip null characters and clean whitespace."""
    text = unicodedata.normalize("NFC", text).replace("\x00", "")
    return "\n".join(
        re.sub(r"[^\S\n]+", " ", line).strip()
        for line in text.splitlines()
    ).strip()


def split_into_sentences(text: str) -> list[str]:
    """Split text along natural sentence or structural boundaries.
    
    Splits by:
    - Paragraph breaks (\n\n+)
    - Sentence enders (., !, ?) followed by whitespace or line break
    - Semicolon list terminators (;) at line ends
    - Structural numbered/bullet points
    """
    pattern = r"(?<=[.!?])\s+|\n{2,}|(?<=;)\n+"
    sentences = [p.strip() for p in re.split(pattern, text) if p.strip()]
    return sentences


def make_chunks(
    document_id: str,
    units: list[TextUnit],
    size: int = 1200,
    overlap: int = 200,
) -> list[dict]:
    """Split TextUnits into sentence-aware chunks with semantic overlap.
    
    1. Preserves sentence integrity: Never cuts a sentence in half if it fits in `size`.
    2. Boundary aware: Respects section boundaries and supports multi-page spans.
    3. Fallback: If text contains no natural sentence breaks or a single sentence
       exceeds `size`, smoothly falls back to character sliding window.
    """
    if not 0 <= overlap < size:
        raise ValueError("Overlap must be non-negative and strictly smaller than chunk size.")

    chunks = []
    step = size - overlap

    for unit in units:
        unit_text = unit.text.strip()
        if not unit_text:
            continue

        sentences = split_into_sentences(unit_text)

        # Fallback for continuous text without sentence/whitespace boundaries
        if len(sentences) <= 1 and len(unit_text) > size:
            for start in range(0, len(unit_text), step):
                end = min(start + size, len(unit_text))
                chunk_text = unit_text[start:end].strip()
                if chunk_text:
                    identity = f"{document_id}:{len(chunks)}:{unit.page}:{unit.section}:{chunk_text}"
                    chunk_id = "chunk_" + sha256(identity.encode("utf-8")).hexdigest()[:32]
                    chunks.append({
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                        "text": chunk_text,
                        "page": unit.page,
                        "pages": list(unit.pages) if unit.pages else ([unit.page] if unit.page else []),
                        "section": unit.section,
                    })
                if end == len(unit_text):
                    break
            continue

        # Sentence-aware accumulation
        cur_sents: list[str] = []
        cur_len = 0

        for sent in sentences:
            sent_len = len(sent)

            # If an unusually long sentence exceeds chunk size, chunk it individually
            if sent_len > size:
                if cur_sents:
                    chunk_text = "\n".join(cur_sents).strip()
                    if chunk_text:
                        identity = f"{document_id}:{len(chunks)}:{unit.page}:{unit.section}:{chunk_text}"
                        chunk_id = "chunk_" + sha256(identity.encode("utf-8")).hexdigest()[:32]
                        chunks.append({
                            "chunk_id": chunk_id,
                            "document_id": document_id,
                            "text": chunk_text,
                            "page": unit.page,
                            "pages": list(unit.pages) if unit.pages else ([unit.page] if unit.page else []),
                            "section": unit.section,
                        })
                    cur_sents = []
                    cur_len = 0

                for start in range(0, sent_len, step):
                    end = min(start + size, sent_len)
                    chunk_text = sent[start:end].strip()
                    if chunk_text:
                        identity = f"{document_id}:{len(chunks)}:{unit.page}:{unit.section}:{chunk_text}"
                        chunk_id = "chunk_" + sha256(identity.encode("utf-8")).hexdigest()[:32]
                        chunks.append({
                            "chunk_id": chunk_id,
                            "document_id": document_id,
                            "text": chunk_text,
                            "page": unit.page,
                            "pages": list(unit.pages) if unit.pages else ([unit.page] if unit.page else []),
                            "section": unit.section,
                        })
                    if end == sent_len:
                        break
                continue

            delimiter_len = 1 if cur_sents else 0
            if cur_len + sent_len + delimiter_len > size and cur_sents:
                chunk_text = "\n".join(cur_sents).strip()
                if chunk_text:
                    identity = f"{document_id}:{len(chunks)}:{unit.page}:{unit.section}:{chunk_text}"
                    chunk_id = "chunk_" + sha256(identity.encode("utf-8")).hexdigest()[:32]
                    chunks.append({
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                        "text": chunk_text,
                        "page": unit.page,
                        "pages": list(unit.pages) if unit.pages else ([unit.page] if unit.page else []),
                        "section": unit.section,
                    })

                # Carry over last sentences for smooth overlap
                overlap_sents: list[str] = []
                overlap_len = 0
                for s in reversed(cur_sents):
                    if overlap_len + len(s) + (1 if overlap_sents else 0) <= overlap:
                        overlap_sents.insert(0, s)
                        overlap_len += len(s) + 1
                    else:
                        break
                cur_sents = overlap_sents
                cur_len = sum(len(s) for s in cur_sents) + max(0, len(cur_sents) - 1)

            cur_sents.append(sent)
            cur_len += sent_len + (1 if len(cur_sents) > 1 else 0)

        if cur_sents:
            chunk_text = "\n".join(cur_sents).strip()
            if chunk_text:
                identity = f"{document_id}:{len(chunks)}:{unit.page}:{unit.section}:{chunk_text}"
                chunk_id = "chunk_" + sha256(identity.encode("utf-8")).hexdigest()[:32]
                chunks.append({
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "text": chunk_text,
                    "page": unit.page,
                    "pages": list(unit.pages) if unit.pages else ([unit.page] if unit.page else []),
                    "section": unit.section,
                })

    return chunks
