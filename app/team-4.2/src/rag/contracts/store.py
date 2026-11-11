"""Kho hợp đồng: bộ nhớ cho bản "Chỉ trong phiên", thư mục `<root>/<id>/` cho bản "Lưu lại".

Bản trong phiên không bao giờ ghi đĩa; mất khi server khởi động lại (mức demo).
"""

from __future__ import annotations

import json
import re
import shutil
import threading
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from rag.contracts.models import Contract, ContractUnit

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ContractStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._mem: dict[str, Contract] = {}
        self._originals: dict[str, tuple[bytes, str]] = {}
        self._lock = threading.Lock()

    def _folder(self, cid: str) -> Path:
        if not _ID.fullmatch(cid or ""):
            raise KeyError(cid)
        return self.root / cid

    def add(self, contract: Contract, *, original: bytes, suffix: str) -> Contract:
        self._folder(contract.contract_id)
        with self._lock:
            self._mem[contract.contract_id] = contract
            self._originals[contract.contract_id] = (original, suffix)
        if contract.persist:
            self._write(contract)
        return contract

    def get(self, cid: str) -> Contract:
        folder = self._folder(cid)
        with self._lock:
            if cid in self._mem:
                return self._mem[cid]
        path = folder / "contract.json"
        if not path.is_file():
            raise KeyError(cid)
        contract = _load(json.loads(path.read_text(encoding="utf-8")))
        with self._lock:
            self._mem[cid] = contract
        return contract

    def original(self, cid: str) -> tuple[bytes, str] | None:
        folder = self._folder(cid)
        if cid in self._originals:
            return self._originals[cid]
        for p in folder.glob("original.*") if folder.is_dir() else []:
            return p.read_bytes(), p.suffix
        return None

    def save(self, cid: str) -> Contract:
        contract = self.get(cid)
        contract.persist = True
        self._write(contract)
        return contract

    def update(self, contract: Contract) -> None:
        """Ghi lại bản đã lưu sau khi đổi bên / ngày ký / thêm báo cáo."""
        if contract.persist:
            self._write(contract)

    def delete(self, cid: str) -> None:
        folder = self._folder(cid)
        with self._lock:
            self._mem.pop(cid, None)
            self._originals.pop(cid, None)
        shutil.rmtree(folder, ignore_errors=True)

    def _write(self, contract: Contract) -> None:
        folder = self._folder(contract.contract_id)
        folder.mkdir(parents=True, exist_ok=True)
        orig = self._originals.get(contract.contract_id)
        if orig is not None:
            (folder / f"original{orig[1]}").write_bytes(orig[0])
        tmp = folder / "contract.json.tmp"
        tmp.write_text(json.dumps(_dump(contract), ensure_ascii=False), encoding="utf-8")
        tmp.replace(folder / "contract.json")


def _dump(c: Contract) -> dict:
    return {
        "contract_id": c.contract_id, "filename": c.filename, "persist": c.persist,
        "created_at": c.created_at.isoformat(), "text": c.text, "units": [asdict(u) for u in c.units],
        "total_units": c.total_units, "pages": c.pages, "facts": c.facts, "party": c.party,
        "sign_date": c.sign_date.isoformat() if c.sign_date else None, "sign_date_source": c.sign_date_source,
        "reports": c.reports,
    }


def _load(d: dict) -> Contract:
    return Contract(
        d["contract_id"], d["filename"], d.get("persist", True), datetime.fromisoformat(d["created_at"]),
        d["text"], [ContractUnit(**u) for u in d["units"]], d.get("total_units", len(d["units"])),
        d.get("pages") or [], d.get("facts") or {}, d.get("party"),
        date.fromisoformat(d["sign_date"]) if d.get("sign_date") else None, d.get("sign_date_source"),
        d.get("reports") or {},
    )
