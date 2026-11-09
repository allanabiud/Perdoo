__all__ = ["Failure", "RunResult"]

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Failure:
    stage: str
    path: Path
    error: str


@dataclass
class RunResult:
    stage: str
    processed: int = 0
    succeeded: int = 0
    planned: int = 0
    skipped: int = 0
    failures: list[Failure] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.failures)

    def add_failure(self, path: Path, error: Exception | str) -> None:
        self.failures.append(Failure(stage=self.stage, path=path, error=str(error)))

    def merge(self, other: "RunResult") -> None:
        self.processed += other.processed
        self.succeeded += other.succeeded
        self.planned += other.planned
        self.skipped += other.skipped
        self.failures.extend(other.failures)
