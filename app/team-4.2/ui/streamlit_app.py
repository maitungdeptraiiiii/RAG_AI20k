"""UI chat Streamlit (chạy tại gốc repo):

    streamlit run app/team-4.2/ui/streamlit_app.py

Sidebar: upload PDF/TXT/MD hoặc nhập URL để ingest. Khung chính: hỏi đáp, mỗi câu trả lời kèm
citation và bảng kết quả từng arm (BM25 / Dense / kết quả cuối) để chứng minh hybrid search chạy.
Qdrant local chỉ cho một tiến trình mở index: đừng chạy script eval khi app đang mở.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from rag.config import Settings
from rag.pipeline import AskTrace, RAGPipeline

st.set_page_config(page_title="RAG Team 4.2", page_icon="📚", layout="wide")


@st.cache_resource
def get_pipeline() -> tuple[RAGPipeline, Settings]:
    settings = Settings.load()
    return RAGPipeline.from_settings(settings), settings


pipeline, settings = get_pipeline()
chunks = pipeline.retriever.chunks


def hits_table(hits) -> list[dict]:
    rows = []
    for h in hits:
        c = chunks[h.chunk_id]
        rows.append({
            "#": h.rank,
            "điểm": round(h.score, 4),
            "nguồn": c.source,
            "trang": c.page_start,
            "đoạn": " ".join(c.text.split())[:120],
        })
    return rows


def show_trace(trace: AskTrace) -> None:
    st.markdown(trace.answer.text)
    if trace.answer.citations:
        st.markdown("**Nguồn:**")
        for c in trace.answer.citations:
            page = f", trang {c.page}" if c.page is not None else ""
            st.markdown(f"- **[{c.n}]** {c.source}{page} — _{c.quote}_")
    res = trace.retrieval
    with st.expander(
        f"Chi tiết retrieval · context {len(trace.context.blocks)} đoạn ({trace.context.mode})"
        + (" · đã rerank" if res.reranked else "")
    ):
        if res.errors:
            st.warning(f"Arm bị lỗi: {res.errors}")
        cols = st.columns(len(res.arms) + 1)
        for col, (arm, hits) in zip(cols, res.arms.items()):
            col.markdown(f"**{arm.upper()}**")
            col.dataframe(hits_table(hits[:5]), hide_index=True)
        cols[-1].markdown("**Kết quả cuối**")
        cols[-1].dataframe(hits_table(res.hits), hide_index=True)


# --- sidebar: ingest -------------------------------------------------------------------

with st.sidebar:
    st.header("Tài liệu")
    uploads = st.file_uploader("Upload PDF / TXT / MD", type=["pdf", "txt", "md"], accept_multiple_files=True)
    url = st.text_input("Hoặc nhập URL")
    if st.button("Ingest", type="primary", disabled=not (uploads or url)):
        raw_dir = settings.data_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        targets: list[tuple[str | Path, str | None]] = []
        for f in uploads or []:
            path = raw_dir / Path(f.name).name
            path.write_bytes(f.getvalue())
            targets.append((path, f.name))
        if url:
            targets.append((url.strip(), None))
        for target, name in targets:
            with st.spinner(f"Đang ingest {name or target} ..."):
                try:
                    r = pipeline.ingest(target, source=name)
                except Exception as e:  # noqa: BLE001 — hiện lỗi cho người dùng, không làm sập app
                    st.error(f"{name or target}: {e}")
                    continue
            if r.skipped:
                st.info(f"{r.source}: đã có, bỏ qua")
            else:
                st.success(f"{r.source}: {r.n_pages} trang, {r.n_chunks} chunk")
            if r.empty_pages:
                st.warning(f"{r.source}: trang không có text (PDF scan?): {r.empty_pages}")

    st.divider()
    docs = pipeline.store.docs()
    st.caption(f"{len(docs)} tài liệu · {len(pipeline.store)} chunk")
    for d in docs:
        st.caption(f"• {d.source} ({d.n_chunks} chunk)")
    st.caption(f"Rerank: {settings.rerank_backend} · LLM: {settings.llm_model}")

# --- chat ----------------------------------------------------------------------------------

st.title("Hỏi đáp tài liệu")
if "history" not in st.session_state:
    st.session_state.history = []

for question, trace in st.session_state.history:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        show_trace(trace)

if question := st.chat_input("Đặt câu hỏi về tài liệu đã ingest"):
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Đang tìm và trả lời ..."):
            trace = pipeline.ask_debug(question)
        show_trace(trace)
    st.session_state.history.append((question, trace))
