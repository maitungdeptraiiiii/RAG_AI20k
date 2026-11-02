"""Data models and exception types for parsing and chunking."""

from dataclasses import dataclass, field

try:
    from src.backend.core.errors import AppError as BaseError
except ImportError:
    class BaseError(Exception):
        def __init__(self, code: str, message: str, status: int = 422):
            super().__init__(code)
            self.code = code
            self.message = message
            self.status = status


class ParseError(BaseError):
    """Raised when parsing a PDF or web document fails."""
    pass


@dataclass(frozen=True)
class TextUnit:
    """A logical unit of text before chunking.
    
    Supports single page or cross-page spans (pages).
    """
    text: str
    page: int | None = None
    section: str | None = None
    pages: tuple[int, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not self.pages and self.page is not None:
            object.__setattr__(self, "pages", (self.page,))
        elif self.pages and self.page is None:
            object.__setattr__(self, "page", self.pages[0])
