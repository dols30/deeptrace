"""Runs model-runner commands as one-shot subprocesses or through warm worker processes.

Every adapter calls run_command(). With DEEPTRACE_MODEL_WORKERS off (the default) it is exactly the
previous subprocess.run call. With it on, a command of the form `<python> <dir>/<runner>.py ...`,
where <dir> also contains worker.py, is sent to a long-lived worker started from the same
interpreter and script. The worker keeps the model loaded between requests. The API process still
never imports torch: workers are separate processes, and the runner JSON is unchanged.

Failure policy: a worker that cannot start, refuses a connection or dies mid-request is stopped and
the command runs once as an ordinary subprocess, so a broken worker never costs a result. A runner
error is reported as CalledProcessError and a timeout as TimeoutExpired, the same exceptions the
adapters already handle.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from deeptrace.config import settings

logger = logging.getLogger("deeptrace.runner")

WORKER_SCRIPT = "worker.py"
STARTUP_TIMEOUT_SECONDS = 60


class WorkerUnavailable(Exception):
    """The worker could not serve this request; the caller falls back to a subprocess."""


class _Worker:
    def __init__(self, interpreter: str, script: Path, socket_path: Path):
        self.interpreter, self.script, self.socket_path = interpreter, script, socket_path
        self.process: subprocess.Popen | None = None
        # One request at a time per worker: it serves serially and must not be started twice.
        self.lock = threading.Lock()

    def alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> None:
        self.socket_path.unlink(missing_ok=True)
        self.process = subprocess.Popen(
            [self.interpreter, str(self.script.parent / WORKER_SCRIPT), "--script", str(self.script),
             "--socket", str(self.socket_path), "--parent-pid", str(os.getpid())],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while not self.socket_path.exists():
            if self.process.poll() is not None:
                raise WorkerUnavailable(f"worker exited during startup with code {self.process.returncode}")
            if time.monotonic() > deadline:
                self.stop()
                raise WorkerUnavailable("worker did not become ready")
            time.sleep(0.02)
        logger.info("Started warm model worker for %s (pid %s)", self.script.name, self.process.pid)

    def stop(self) -> None:
        if self.alive():
            self.process.terminate()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process = None
        self.socket_path.unlink(missing_ok=True)

    def call(self, args: list[str], timeout: float) -> str:
        if not self.alive():
            self.start()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(timeout)
                client.connect(str(self.socket_path))
                client.sendall(json.dumps({"argv": args[2:]}).encode() + b"\n")
                data = b""
                while not data.endswith(b"\n"):
                    chunk = client.recv(1024 * 1024)
                    if not chunk:
                        break
                    data += chunk
        except socket.timeout as exc:
            # Same outcome as a subprocess timeout: the stuck worker is killed.
            self.stop()
            raise subprocess.TimeoutExpired(args, timeout) from exc
        except OSError as exc:
            self.stop()
            raise WorkerUnavailable(f"{type(exc).__name__}: {exc}") from exc
        if not data.endswith(b"\n"):
            self.stop()
            raise WorkerUnavailable("worker closed the connection without a response")
        response = json.loads(data)
        if not response.get("ok"):
            raise subprocess.CalledProcessError(1, args, output="", stderr=str(response.get("error", "")))
        return response["stdout"]


_workers: dict[tuple[str, str], _Worker] = {}
_workers_lock = threading.Lock()
_socket_dir: Path | None = None


def _worker_for(args: list[str]) -> _Worker | None:
    """The warm worker for `<python> <runner>.py ...`, or None when the command cannot use one."""
    global _socket_dir
    if len(args) < 2 or not args[1].endswith(".py"):
        return None
    script = Path(args[1]).resolve()
    if script.name == WORKER_SCRIPT or not (script.parent / WORKER_SCRIPT).is_file():
        return None
    key = (args[0], str(script))
    with _workers_lock:
        if key not in _workers:
            if _socket_dir is None:
                # Short private directory: Unix socket paths are limited to about 100 characters.
                _socket_dir = Path(tempfile.mkdtemp(prefix="dtw-"))
            _workers[key] = _Worker(args[0], script, _socket_dir / f"{len(_workers)}-{script.stem[:40]}.sock")
        return _workers[key]


def run_command(args: list[str], timeout: float) -> str:
    """Run a model-runner command and return its JSON stdout."""
    worker = _worker_for(args) if settings.model_workers else None
    if worker is not None:
        with worker.lock:
            try:
                return worker.call(args, timeout)
            except WorkerUnavailable as exc:
                logger.warning("Warm worker for %s unavailable (%s); running as a subprocess.",
                    worker.script.name, exc)
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True).stdout


def shutdown_workers() -> None:
    global _socket_dir
    with _workers_lock:
        for worker in _workers.values():
            worker.stop()
        _workers.clear()
        if _socket_dir is not None:
            shutil.rmtree(_socket_dir, ignore_errors=True)
            _socket_dir = None


atexit.register(shutdown_workers)
