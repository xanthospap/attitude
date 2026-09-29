from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProductResult:
    """Outcome of preparing one logical product family.

    Missing remote files are warnings, not exceptions.  Exceptions are
    reserved for invalid user configuration and local programming errors.
    """

    product: str
    available: list[Path] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_available(self, path: str | Path) -> None:
        self.available.append(Path(path))

    def add_missing(self, item: str, message: str | None = None) -> None:
        self.missing.append(item)
        if message:
            self.warnings.append(message)

    def merge(self, other: "ProductResult") -> "ProductResult":
        self.available.extend(other.available)
        self.missing.extend(other.missing)
        self.warnings.extend(other.warnings)
        return self

    def as_dict(self) -> dict[str, object]:
        return {
            "product": self.product,
            "available": [str(path) for path in self.available],
            "missing": self.missing,
            "warnings": self.warnings,
            "complete": not self.missing,
        }
