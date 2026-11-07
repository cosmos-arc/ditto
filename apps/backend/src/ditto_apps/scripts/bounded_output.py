"""用标准库为长驻 worker 的合并 stdout/stderr 设置有限日志。"""

import argparse
import logging
import os
import signal
import subprocess
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Timer
from types import FrameType

_MIN_LOG_BYTES = 8192


def run(command: list[str], path: Path, *, max_bytes: int, backups: int) -> int:
    """透传退出码和终止信号；只轮转本命令的日志，不触碰业务文件。"""
    if not command or max_bytes < _MIN_LOG_BYTES or backups < 1:
        raise ValueError("command, max_bytes >= 8192 and backups >= 1 required")
    path.parent.mkdir(parents=True, exist_ok=True)
    _bound_existing_logs(path, max_bytes, backups)
    handler = RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
    )
    process = subprocess.Popen(  # noqa: S603 - explicit CLI argv, no shell
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    stop_timer: Timer | None = None

    def forward(signum: int, frame: FrameType | None) -> None:
        nonlocal stop_timer
        del frame
        if stop_timer is None:
            # A timer runs even while read blocks and the worker ignores TERM.
            stop_timer = Timer(10, _signal_group, (process.pid, signal.SIGKILL))
            stop_timer.daemon = True
            stop_timer.start()
        _signal_group(process.pid, signum)

    previous = {
        sig: signal.signal(sig, forward) for sig in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        if process.stdout is None:
            raise RuntimeError("worker output pipe was not created")
        while chunk := os.read(process.stdout.fileno(), min(4096, max_bytes // 4)):
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
        if stop_timer is not None:
            stop_timer.cancel()
        for sig, original in previous.items():
            signal.signal(sig, original)
        _stop_process(process)
        if process.stdout is not None:
            process.stdout.close()
        handler.close()


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        _signal_group(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _signal_group(process.pid, signal.SIGKILL)
            process.wait()


def _signal_group(pid: int, signum: int) -> None:
    try:
        os.killpg(pid, signum)
    except ProcessLookupError:
        pass  # The entire worker group already exited.


def _bound_existing_logs(path: Path, max_bytes: int, backups: int) -> None:
    """接管已有大日志时保留尾部；只触碰此日志与数字轮转代。"""
    existing = [path]
    for candidate in path.parent.glob(path.name + ".*"):
        suffix = candidate.name.removeprefix(path.name + ".")
        if not suffix.isdecimal():
            continue
        if int(suffix) > backups:
            candidate.unlink()
        else:
            existing.append(candidate)
    for candidate in existing:
        if candidate.exists() and candidate.stat().st_size > max_bytes:
            with candidate.open("r+b") as stream:
                stream.seek(-max_bytes, os.SEEK_END)
                tail = stream.read(max_bytes)
                stream.seek(0)
                stream.write(tail)
                stream.truncate()


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
