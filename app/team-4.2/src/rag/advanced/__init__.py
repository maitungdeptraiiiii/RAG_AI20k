"""Phương pháp nâng cao dạng plugin. Xem advanced/base.py.

Mỗi dòng import dưới đây đăng ký một (hoặc vài) phương pháp vào REGISTRY. Thêm phương pháp mới:
thêm file + một dòng import. Bật/tắt bằng biến môi trường ADVANCED.
"""

from rag.advanced import colbert, contextual, hyde, splade  # noqa: F401  (import để đăng ký)
from rag.advanced.base import (
    REGISTRY,
    Components,
    Enhancement,
    IndexEnhancer,
    build_enhancements,
    parse_names,
    register,
)

__all__ = [
    "REGISTRY",
    "Components",
    "Enhancement",
    "IndexEnhancer",
    "build_enhancements",
    "parse_names",
    "register",
]
