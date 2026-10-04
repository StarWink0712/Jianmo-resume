"""Importable on every platform; no native APIs or platform selection here."""

from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict


class PlatformUnavailable(ValueError):
    pass


class LockBusy(ValueError):
    pass


class Lease(Protocol):
    def close(self) -> None: ...


@dataclass(frozen=True)
class Capabilities:
    file_isolation: bool
    network_isolation: bool
    process_tree: str
    memory: str
    cpu: str
    output_file: str

    def require_compilation(self):
        if not (self.file_isolation and self.network_isolation and self.process_tree != 'none'
                and self.memory != 'none' and self.cpu != 'none' and self.output_file != 'none'):
            raise PlatformUnavailable('Native compiler isolation is not implemented and verified on this platform; refusing unsandboxed execution.')


class ExecutionResult(TypedDict):
    returncode: int | None
    timed_out: bool
    memory_exceeded: bool
    peak_group_rss_bytes: int
    memory_limit_bytes: int | None
    seconds: float
    reason: Literal['success', 'exit_error', 'start_failed', 'wall_timeout', 'memory_limit', 'cpu_limit', 'file_limit']
    process_tree_cleanup: Literal['not_started', 'signalled', 'already_exited', 'failed']
