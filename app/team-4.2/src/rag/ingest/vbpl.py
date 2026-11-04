"""Crawler văn bản pháp luật từ vbpl.vn (API JSON công khai của Bộ Tư pháp) — reader, không chunk.

Tham khảo `Law-RAG/law_rag/crawl/crawl_vbpl_laws.py`. Khác bản gốc:
- Chỉ tải và lưu text + metadata; chunk/index vẫn do `scripts/team-4.2/ingest.py` làm như mọi nguồn khác.
- Text sinh ra giống hệt cách đã tạo snapshot 6 Bộ luật trong `data/team-4.2/raw/` (đã đối chiếu
  Bộ luật Lao động 45/2019/QH14), nên chunker hiện tại đọc được ngay.
- Tìm theo số hiệu (`search_by_number`), không chỉ duyệt danh sách theo loại văn bản.
- Manifest ghi checksum từng văn bản: crawl lại thì biết văn bản mới / không đổi / đã đổi nội dung.

Mỗi văn bản lưu thành 2 file trong thư mục đích:
    <stem>.txt         nội dung văn bản (phần "NỘI DUNG VĂN BẢN"), không chèn metadata
    <stem>.meta.json   số hiệu, loại, cơ quan, ngày ban hành/hiệu lực, tình trạng hiệu lực, nguồn, checksum
và cập nhật `manifest.json` (vbpl_id -> bản ghi).

Metadata hành chính không đưa vào text để embed (xem plan baseline: làm kết quả tệ hơn); để dành làm filter.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

API_BASE = "https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc"
SOURCE_URL = "https://vbpl.vn/van-ban/chi-tiet/{id}"
USER_AGENT = "Mozilla/5.0 (compatible; rag-team-4.2-crawler)"

# Id danh mục của vbpl (fallback khi không gọi được combobox).
DOC_TYPE_IDS = {
    "Bộ luật": "404b68a7-8e71-4ee5-a6c0-07e59f35f824",
    "Luật": "11025e19-2dd6-4165-85ad-ab6241186a1a",
    "Nghị định": "0d08b84c-7de7-4800-8760-2a68265e7890",
    "Thông tư": "178c63a9-73ff-4fd4-9d91-18d690520090",
    "Quyết định": "0a5362e8-cdca-436e-96cd-979598df3b16",
}
EFFECTIVE_STATUS_IDS = {
    "Còn hiệu lực": "1419f6be-4a15-44a7-97ac-ea042770a514",
    "Hết hiệu lực một phần": "9c20e89d-e048-4f3a-b6c2-df87fe0b1ada",
    "Ngưng hiệu lực một phần": "d1189072-7aed-44d8-bcaf-d89409adcded",
}


class VbplError(RuntimeError):
    pass


# --- HTTP ------------------------------------------------------------------------------


def create_session():
    import requests

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://vbpl.vn",
            "Referer": "https://vbpl.vn/van-ban/trung-uong",
        }
    )
    return session


def _unwrap(response) -> Any:
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success", True):
        raise VbplError(str(payload)[:300])
    return payload["data"]


@dataclass
class VbplClient:
    """Gọi API vbpl. `session` thay được bằng session giả khi test."""

    session: Any = None
    timeout: float = 60
    delay: float = 0.5  # nghỉ giữa các request, tránh dồn tải lên máy chủ nhà nước
    attempts: int = 3
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = create_session()

    def _call(self, fn: Callable[[], Any]) -> Any:
        for attempt in range(self.attempts):
            try:
                result = fn()
                self.sleep(self.delay)
                return result
            except Exception as e:  # noqa: BLE001 — thử lại mọi lỗi mạng/HTTP
                if attempt + 1 >= self.attempts:
                    raise
                wait = max(0.2, self.delay) * 2**attempt
                log.warning("vbpl lỗi (%s), thử lại sau %.1fs", e, wait)
                self.sleep(wait)
        raise AssertionError("unreachable")

    def list_page(
        self,
        page_number: int,
        page_size: int = 50,
        *,
        keyword: str | None = None,
        doc_type_ids: list[str] | None = None,
        status_ids: list[str] | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"pageNumber": page_number, "pageSize": page_size}
        if keyword:
            payload["keyword"] = keyword
        if doc_type_ids:
            payload["docType"] = doc_type_ids
        if status_ids:
            payload["effStatus"] = status_ids
        return self._call(
            lambda: _unwrap(self.session.post(f"{API_BASE}/all", json=payload, timeout=self.timeout))
        )

    def detail(self, doc_id: str) -> dict:
        return self._call(lambda: _unwrap(self.session.get(f"{API_BASE}/{doc_id}", timeout=self.timeout)))

    def iter_list(
        self,
        *,
        doc_type_ids: list[str] | None = None,
        status_ids: list[str] | None = None,
        keyword: str | None = None,
        page_size: int = 50,
    ) -> Iterator[dict]:
        page_number = 1
        seen = 0
        while True:
            page = self.list_page(
                page_number, page_size, keyword=keyword, doc_type_ids=doc_type_ids, status_ids=status_ids
            )
            items = page.get("items") or []
            yield from items
            seen += len(items)
            if not items or seen >= int(page.get("total") or 0):
                return
            page_number += 1

    def search_by_number(self, doc_number: str) -> list[dict]:
        """Các mục có số hiệu đúng bằng `doc_number` (API tìm `keyword` gần đúng, nên lọc lại)."""
        want = _norm_number(doc_number)
        page = self.list_page(1, 20, keyword=doc_number)
        return [i for i in page.get("items") or [] if _norm_number(i.get("docNum") or "") == want]


def _norm_number(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", value)).upper()


# --- parse -----------------------------------------------------------------------------


def html_to_text(html: str) -> str:
    """HTML nội dung văn bản -> text, mỗi phần tử một dòng (giống snapshot đã commit)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = (re.sub(r"\s+", " ", line).strip() for line in soup.get_text("\n").splitlines())
    return unicodedata.normalize("NFC", "\n".join(line for line in lines if line))


def _name(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("name")
    return value if isinstance(value, str) else None


def _names(value: Any) -> list[str]:
    return [n for n in (_name(v) for v in value or []) if n] if isinstance(value, list) else []


def _date(value: Any) -> str | None:
    """'2019-11-20T00:00:00' -> '2019-11-20'."""
    return value[:10] if isinstance(value, str) and value else None


def metadata_from_detail(detail: dict) -> dict:
    return {
        "vbpl_id": str(detail.get("id")),
        "title": detail.get("title"),
        "doc_number": detail.get("docNum"),
        "doc_type": _name(detail.get("docType")),
        "agency": detail.get("agencyName") or _name(detail.get("organization")),
        "issue_date": _date(detail.get("issueDate")),
        "effective_from": _date(detail.get("effFrom")),
        "effective_to": _date(detail.get("effTo")),
        "effective_status": _name(detail.get("effStatus")),
        "fields": _names(detail.get("documentFields")),
        "majors": _names(detail.get("documentMajors")),
        "is_consolidated": bool(detail.get("isConsolidatedDocument")),
        "source_url": SOURCE_URL.format(id=detail.get("id")),
    }


def pick_detail(client: VbplClient, items: list[dict]) -> dict | None:
    """Một số hiệu có thể có nhiều bản ghi (hệ thống cũ/mới); lấy bản đầu tiên có nội dung."""
    for item in items:
        detail = client.detail(str(item["id"]))
        if (detail.get("documentContent") or {}).get("content"):
            return detail
        log.info("bỏ qua %s (%s): không có nội dung", item.get("id"), item.get("docNum"))
    return None


# --- lưu -------------------------------------------------------------------------------

_VI_ASCII = str.maketrans({"đ": "d", "Đ": "d"})


def slugify(value: str, max_len: int = 80) -> str:
    ascii_value = unicodedata.normalize("NFKD", value.translate(_VI_ASCII))
    ascii_value = "".join(c for c in ascii_value if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")[:max_len].rstrip("_")


def default_stem(meta: dict) -> str:
    title = meta.get("title") or ""
    number = meta.get("doc_number") or ""
    # Bỏ "số 45/2019/QH14" khỏi tiêu đề rồi gắn số hiệu ở cuối cho ngắn và không trùng.
    title = re.sub(r"\s*(số\s*)?" + re.escape(number), "", title, flags=re.I) if number else title
    return slugify(f"{title} {number}") or f"vbpl_{meta.get('vbpl_id')}"


@dataclass(frozen=True)
class SavedDoc:
    vbpl_id: str
    doc_number: str | None
    text_file: Path
    status: str  # new | unchanged | updated | empty
    n_chars: int


def load_manifest(out_dir: Path) -> dict[str, dict]:
    path = out_dir / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_manifest(out_dir: Path, manifest: dict[str, dict]) -> None:
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def save_document(
    detail: dict,
    out_dir: Path,
    manifest: dict[str, dict],
    *,
    stem: str | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> SavedDoc:
    """Ghi <stem>.txt + <stem>.meta.json và cập nhật `manifest` (chưa ghi manifest ra đĩa)."""
    meta = metadata_from_detail(detail)
    text = html_to_text((detail.get("documentContent") or {}).get("content") or "")
    vbpl_id = meta["vbpl_id"]
    if not text:
        return SavedDoc(vbpl_id, meta["doc_number"], Path(), "empty", 0)

    previous = manifest.get(vbpl_id)
    stem = stem or (Path(previous["text_file"]).stem if previous else default_stem(meta))
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if previous is None:
        status = "new"
    elif previous.get("sha256") == checksum and (out_dir / previous["text_file"]).exists():
        status = "unchanged"
    else:
        status = "updated"

    text_file = out_dir / f"{stem}.txt"
    record = {
        **meta,
        "text_file": text_file.name,
        "meta_file": f"{stem}.meta.json",
        "sha256": checksum,
        "n_chars": len(text),
        "crawled_at": now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if status == "unchanged":
        record["crawled_at"] = previous.get("crawled_at", record["crawled_at"])
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        text_file.write_text(text + "\n", encoding="utf-8")
        if previous and status == "updated":
            record["previous_sha256"] = previous.get("sha256")
        (out_dir / record["meta_file"]).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    manifest[vbpl_id] = record
    return SavedDoc(vbpl_id, meta["doc_number"], text_file, status, len(text))
