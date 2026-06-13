from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SheetReader(Protocol):
    def read_rows(self, path: str | Path, sheet_name: str) -> list[tuple[Any, ...]]: ...


@runtime_checkable
class FileStore(Protocol):
    def save(self, upload_id: int, data: bytes) -> None: ...

    def load(self, upload_id: int) -> bytes: ...
