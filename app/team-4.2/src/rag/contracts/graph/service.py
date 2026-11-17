"""Dịch vụ đồ thị hợp đồng: tách → dựng → kiểm → công bố, có khóa ghi theo hợp đồng."""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime

from rag.contracts.doc import ContractDoc, PageText
from rag.contracts.graph.build import build_graph
from rag.contracts.graph.neo4j_store import ContractGraphStore, GraphUnavailable
from rag.contracts.graph.oplog import OperationLog

log = logging.getLogger(__name__)

BACKOFF_S = 30.0
BACKING_OFF = "Neo4j tạm không khả dụng — sẽ thử lại sau"


class GraphBusy(RuntimeError):
    """Hợp đồng đang được thay đổi bởi người khác."""

    def __init__(self, message: str = "Đang có thay đổi khác trên hợp đồng này — hãy tải lại"):
        super().__init__(message)


class ContractGraphService:
    def __init__(self, store: ContractGraphStore | None, clock=time.monotonic):
        self.store = store
        self._clock = clock
        self._down_until = 0.0     # Neo4j vừa sập: không thử công bố lại trước thời điểm này
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    @contextmanager
    def writing(self, contract_id: str):
        """Khóa ghi riêng từng hợp đồng; đang bị giữ thì báo GraphBusy."""
        with self._guard:
            lock = self._locks.setdefault(contract_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise GraphBusy()
        try:
            yield
        finally:
            lock.release()

    def rebuild(self, contract_id: str, pages: list[PageText], oplog: OperationLog, *,
                file_checksum: str, now: datetime) -> tuple[ContractDoc, dict]:
        """Dựng lại đồ thị; luôn trả ContractDoc, đồ thị lỗi/tắt chỉ báo trong trạng thái."""
        build, doc = build_graph(contract_id, pages, oplog,
                                 file_checksum=file_checksum, built_at=now)
        problems = list(build.problems)
        status = {"enabled": self.store is not None, "build_id": build.build_id,
                  "published": False, "problems": problems, "error": None,
                  "record": build.record()}
        if self.store is None or problems:
            return doc, status
        if self._clock() < self._down_until:
            status["error"] = BACKING_OFF
            return doc, status
        try:
            self.store.publish(build)
            status["published"] = True
        except GraphUnavailable as exc:
            self._down_until = self._clock() + BACKOFF_S
            status["error"] = str(exc)
        except Exception as exc:  # đồ thị không được làm hỏng API
            log.exception("Ghi đồ thị hợp đồng %s thất bại", contract_id)
            status["error"] = f"Lỗi khi ghi đồ thị: {type(exc).__name__}"
        return doc, status
