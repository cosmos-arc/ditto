#!/usr/bin/env python3
"""Serve a loopback TCP endpoint that accepts HTTP but never responds."""

from __future__ import annotations

import argparse
import socketserver
import threading


class _BlackholeHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        # Read the request so the connection is demonstrably established, then
        # remain silent. Process-group cleanup terminates the waiting daemon
        # thread together with the server.
        self.request.recv(64 * 1024)
        threading.Event().wait()


class _LoopbackBlackhole(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, type=int)
    arguments = parser.parse_args()
    with _LoopbackBlackhole(("127.0.0.1", arguments.port), _BlackholeHandler) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
