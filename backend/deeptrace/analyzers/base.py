import shlex

from abc import ABC, abstractmethod
from pathlib import Path

from deeptrace.schemas import ComponentResult, MediaMetadata


class MediaAnalyzer(ABC):
    """Adapter boundary for pretrained or hosted inference implementations."""

    @abstractmethod
    def analyze(self, path: Path, metadata: MediaMetadata) -> ComponentResult:
        raise NotImplementedError



def command_args(template: str, **paths) -> list[str]:
    """Split before substituting paths, preserving spaces without invoking a shell."""
    return [part.format(**{key: str(value) for key, value in paths.items()})
            for part in shlex.split(template)]
