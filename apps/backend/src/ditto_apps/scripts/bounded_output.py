"""用标准库为长驻 worker 的合并 stdout/stderr 设置有限日志。"""

import argparse
import logging
import os
import signal
import subprocess
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import FrameType

_MIN_LOG_BYTES = 8192


def run(command: list[str], path: Path, *, max_bytes: int, backups: int) -> int:
    """透传退出码和终止信号；只轮转本命令的日志，不触碰业务文件。"""
    if not command or max_bytes < _MIN_LOG_BYTES or backups < 1:
        raise ValueError("command, max_bytes >= 8192 and backups >= 1 required")
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
    )
    process = subprocess.Popen(  # noqa: S603 - explicit CLI argv, no shell
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    def forward(signum: int, frame: FrameType | None) -> None:
        del frame
        if process.poll() is None:
            os.killpg(process.pid, signum)

    previous = {
        sig: signal.signal(sig, forward) for sig in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        if process.stdout is None:
            raise RuntimeError("worker output pipe was not created")
        while chunk := os.read(process.stdout.fileno(), 4096):
            handler.handle(
                logging.LogRecord(
                    "worker",
                    logging.INFO,
                    "",
                    0,
                    chunk.decode("utf-8", errors="replace"),
                    (),
                    None,
                )
            )
        return process.wait()
    finally:
        for sig, original in previous.items():
            signal.signal(sig, original)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        if process.stdout is not None:
            process.stdout.close()
        handler.close()


def main() -> int:
    """运行原 worker 命令，默认保留 5×20MiB 历史及一个活动文件。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=20 * 1024 * 1024)
    parser.add_argument("--backups", type=int, default=5)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return run(command, args.log, max_bytes=args.max_bytes, backups=args.backups)


if __name__ == "__main__":
    raise SystemExit(main())
