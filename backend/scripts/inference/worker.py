"""Warm model worker: serves one runner's main() over a Unix socket so its model stays loaded.

Started and supervised by deeptrace.analyzers.runner when DEEPTRACE_MODEL_WORKERS is enabled; it
is not a public interface. It runs in the same interpreter and environment as the one-shot runner
command, and calls the same main(argv), so preprocessing, scores and the runner JSON are unchanged.
Requests are handled one at a time. Models are cached by common.cached().

Protocol, one request per connection:
  request:  {"argv": ["--frames", "...", ...]}\\n
  response: {"ok": true, "stdout": "<runner JSON>"}\\n   or   {"ok": false, "error": "<message>"}\\n
"""
import argparse
import importlib.util
import json
import os
import socket
import sys
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path

MAX_REQUEST_BYTES = 1024 * 1024


def load_main(script):
    script = Path(script).resolve()
    # Runners import their siblings (common, face_coverage, ...) by name.
    if str(script.parent) not in sys.path:
        sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location('deeptrace_runner_' + script.stem, script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def exit_with_parent(parent_pid):
    """Exit if the API process that started this worker goes away, so no orphan holds a GPU."""
    while True:
        if os.getppid() != parent_pid:
            os._exit(0)
        time.sleep(2)


def read_request(connection):
    data = b''
    while not data.endswith(b'\n'):
        chunk = connection.recv(65536)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_REQUEST_BYTES:
            raise ValueError('Request too large')
    request = json.loads(data)
    argv = request.get('argv') if isinstance(request, dict) else None
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
        raise ValueError('Request must contain argv as a list of strings')
    return argv


def handle(main, argv):
    try:
        # Third-party constructors can print progress. Keep stdout for the protocol, as common.run does.
        with redirect_stdout(sys.stderr):
            payload = main(argv)
        return {'ok': True, 'stdout': json.dumps(payload, allow_nan=False)}
    except SystemExit as exc:  # argparse reports bad arguments by exiting
        return {'ok': False, 'error': f'Runner rejected its arguments (exit {exc.code}).'}
    except Exception as exc:
        return {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}


def serve(main, socket_path, parent_pid):
    threading.Thread(target=exit_with_parent, args=(parent_pid,), daemon=True).start()
    socket_path = Path(socket_path)
    # Bind and listen on a temporary name, then rename: the final path appears only when ready.
    pending = socket_path.with_name(socket_path.name + '.starting')
    pending.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(pending))
    os.chmod(pending, 0o600)
    server.listen(16)
    os.replace(pending, socket_path)
    while True:
        connection, _ = server.accept()
        with connection:
            try:
                response = handle(main, read_request(connection))
            except (ValueError, json.JSONDecodeError) as exc:
                response = {'ok': False, 'error': f'Invalid worker request: {exc}'}
            try:
                connection.sendall(json.dumps(response).encode() + b'\n')
            except OSError:
                pass  # The client gave up (timeout); keep serving.


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script', type=Path, required=True)
    parser.add_argument('--socket', type=Path, required=True)
    parser.add_argument('--parent-pid', type=int, required=True)
    args = parser.parse_args()
    serve(load_main(args.script), args.socket, args.parent_pid)


if __name__ == '__main__':
    cli()
