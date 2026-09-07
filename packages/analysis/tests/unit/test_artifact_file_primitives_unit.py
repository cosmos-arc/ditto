"""Cross-platform import and no-follow checks for artifact primitives."""

from __future__ import annotations

import ctypes
import os
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest
from ditto_analysis.research import _artifact_file_primitives as primitives


def test_modules_import_without_posix_only_open_flags() -> None:
    code = """import os
for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_ACCMODE"):
    if hasattr(os, flag):
        delattr(os, flag)
import ditto_analysis.research._artifact_file_primitives as primitives
import ditto_analysis.research._indexed_artifacts
assert primitives._HAS_ATOMIC_NOFOLLOW is False
assert primitives._windows_access(primitives.READ_FLAGS) != 0
assert (
    primitives._windows_fd_flags(primitives.READ_FLAGS)
    & primitives._WINDOWS_ACCESS_MODE
    == 0
)
"""
    result = subprocess.run(  # noqa: S603 - fixed interpreter and inline literal
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_missing_atomic_nofollow_fails_closed_for_existing_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"safe")
    link = tmp_path / "artifact.json"
    link.symlink_to(outside)
    monkeypatch.setattr(primitives, "_HAS_ATOMIC_NOFOLLOW", False)
    monkeypatch.setattr(primitives, "_IS_WINDOWS", False)

    with pytest.raises(OSError, match="atomic no-follow open unavailable"):
        primitives.open_file(link, os.O_RDONLY)

    assert outside.read_bytes() == b"safe"


def test_missing_atomic_nofollow_fails_closed_for_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "file.json"
    target.write_bytes(b"{}")
    monkeypatch.setattr(primitives, "_HAS_ATOMIC_NOFOLLOW", False)
    monkeypatch.setattr(primitives, "_IS_WINDOWS", False)

    with pytest.raises(OSError, match="atomic no-follow open unavailable"):
        primitives.open_directory(target)


def test_exclusive_create_mode_is_preserved_without_atomic_nofollow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "sidecar.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    monkeypatch.setattr(primitives, "_HAS_ATOMIC_NOFOLLOW", False)
    monkeypatch.setattr(primitives, "_IS_WINDOWS", False)

    descriptor = primitives.open_file(target, flags, 0o600)
    os.close(descriptor)

    if sys.platform != "win32":
        assert target.stat().st_mode & 0o777 == 0o600
    else:
        assert target.is_file()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native behavior")
def test_windows_no_follow_uses_real_reparse_point_entries(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    target.write_bytes(b"safe")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    parent_fd = primitives.open_directory(tmp_path, durable=True)
    try:
        descriptor = primitives.open_file(
            primitives.DirectoryEntryPath(parent_fd, target.name), primitives.READ_FLAGS
        )
        try:
            assert os.read(descriptor, 4) == b"safe"
        finally:
            os.close(descriptor)

        descriptor = primitives.open_file(
            primitives.DirectoryEntryPath(parent_fd, target.name),
            primitives.SYNC_FLAGS,
        )
        try:
            primitives.fsync_entry(descriptor)
        finally:
            os.close(descriptor)

        with pytest.raises(OSError, match="artifact path is a reparse point"):
            primitives.open_file(
                primitives.DirectoryEntryPath(parent_fd, link.name),
                primitives.READ_FLAGS,
            )

        child = tmp_path / "artifacts"
        child.mkdir()
        descriptor = primitives.open_directory(
            primitives.DirectoryEntryPath(parent_fd, child.name), durable=True
        )
        try:
            assert stat.S_ISDIR(os.fstat(descriptor).st_mode)
            primitives.fsync_entry(descriptor)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (os.O_WRONLY, primitives._WINDOWS_FILE_WRITE_ACCESS),
        (
            os.O_RDWR,
            primitives._WINDOWS_FILE_READ_ACCESS
            | primitives._WINDOWS_FILE_WRITE_ACCESS,
        ),
        (os.O_RDONLY, primitives._WINDOWS_FILE_READ_ACCESS),
    ],
)
def test_windows_access_uses_specific_file_rights(flags: int, expected: int) -> None:
    assert primitives._windows_access(flags) == expected


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (os.O_CREAT | os.O_EXCL, 1),
        (os.O_CREAT | os.O_TRUNC, 2),
        (os.O_CREAT, 4),
        (os.O_TRUNC, 5),
        (os.O_RDONLY, 3),
    ],
)
def test_windows_absolute_creation_modes(flags: int, expected: int) -> None:
    assert primitives._windows_absolute_creation(flags) == expected


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (os.O_CREAT | os.O_EXCL, 2),
        (os.O_CREAT | os.O_TRUNC, 5),
        (os.O_CREAT, 3),
        (os.O_TRUNC, 4),
        (os.O_RDONLY, 1),
    ],
)
def test_windows_relative_creation_modes(flags: int, expected: int) -> None:
    assert primitives._windows_relative_creation(flags) == expected


def test_windows_fd_flags_preserve_open_mode() -> None:
    flags = os.O_RDWR | getattr(os, "O_APPEND", 0) | getattr(os, "O_BINARY", 0)
    assert primitives._windows_fd_flags(flags) == (
        os.O_RDWR | getattr(os, "O_APPEND", 0) | getattr(os, "O_BINARY", 0)
    )


def _install_fake_msvcrt(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("msvcrt")
    module.get_osfhandle = lambda descriptor: descriptor
    module.open_osfhandle = lambda handle, _flags: int(handle)
    monkeypatch.setitem(sys.modules, "msvcrt", module)


_windows_coverage_simulation = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Linux coverage simulation; Windows exercises the real native APIs",
)


class _FakeWinApi:
    def __init__(self, handle: object = 123) -> None:
        self.CreateFileW = _FakeWinFunction(handle)
        self.CloseHandle = _FakeWinFunction(None)

    def __call__(self, *_args: object, **_kwargs: object) -> _FakeWinApi:
        return self


class _FakeWinFunction:
    def __init__(self, result: object) -> None:
        self.result = result
        self.argtypes: list[object] = []
        self.restype: object = None
        self.calls: list[tuple[object, ...]] = []

    def __call__(self, *args: object) -> object:
        self.calls.append(args)
        return self.result(*args) if callable(self.result) else self.result


@_windows_coverage_simulation
def test_windows_absolute_open_converts_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "artifact.json"
    target.write_bytes(b"safe")
    descriptor = os.open(target, os.O_RDONLY)
    fake = _FakeWinApi(handle=descriptor)
    monkeypatch.setattr(primitives.ctypes, "WinDLL", fake, raising=False)
    _install_fake_msvcrt(monkeypatch)

    opened = primitives._open_windows_absolute(target, primitives.READ_FLAGS)

    assert os.read(opened, 4) == b"safe"
    assert fake.CreateFileW.calls
    os.close(opened)
    assert fake.CloseHandle.calls == []


@_windows_coverage_simulation
def test_windows_absolute_open_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeWinApi(handle=None)
    monkeypatch.setattr(primitives.ctypes, "WinDLL", fake, raising=False)
    monkeypatch.setattr(primitives.ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(
        primitives.ctypes,
        "WinError",
        lambda code: OSError(code, "injected Win32 failure"),
        raising=False,
    )
    _install_fake_msvcrt(monkeypatch)

    with pytest.raises(OSError):
        primitives._open_windows_absolute(
            tmp_path / "missing.json", primitives.READ_FLAGS
        )


@_windows_coverage_simulation
def test_windows_relative_open_converts_nt_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "artifact.json"
    target.write_bytes(b"safe")
    parent_fd = os.open(tmp_path, primitives._DIRECTORY_FLAGS)
    descriptor = os.open(target, primitives.READ_FLAGS, dir_fd=parent_fd)

    def create_file(handle_reference: object, *_args: object) -> int:
        ctypes.cast(
            handle_reference, ctypes.POINTER(ctypes.c_void_p)
        ).contents.value = descriptor
        return 0

    nt_create = _FakeWinFunction(create_file)
    fake_ntdll = _FakeWinApi()
    fake_ntdll.NtCreateFile = nt_create
    fake_ntdll.RtlNtStatusToDosError = _FakeWinFunction(5)

    def load_dll(name: str, *_args: object, **_kwargs: object) -> _FakeWinApi:
        if name != "ntdll":
            raise AssertionError(name)
        return fake_ntdll

    monkeypatch.setattr(primitives.ctypes, "WinDLL", load_dll, raising=False)
    _install_fake_msvcrt(monkeypatch)

    opened = primitives._open_windows_relative(
        primitives.DirectoryEntryPath(parent_fd, target.name),
        primitives.READ_FLAGS,
    )

    assert os.read(opened, 4) == b"safe"
    os.close(opened)
    os.close(parent_fd)


def _install_fake_ntdll(
    monkeypatch: pytest.MonkeyPatch,
    information_status: int,
) -> _FakeWinFunction:
    set_information = _FakeWinFunction(information_status)
    fake_ntdll = _FakeWinApi()
    fake_ntdll.NtSetInformationFile = set_information
    fake_ntdll.RtlNtStatusToDosError = _FakeWinFunction(5)

    def load_dll(name: str, *_args: object, **_kwargs: object) -> _FakeWinApi:
        if name != "ntdll":
            raise AssertionError(name)
        return fake_ntdll

    monkeypatch.setattr(primitives.ctypes, "WinDLL", load_dll, raising=False)
    monkeypatch.setattr(
        primitives.ctypes,
        "WinError",
        lambda code: OSError(code, "injected NT failure"),
        raising=False,
    )
    _install_fake_msvcrt(monkeypatch)
    return set_information


@pytest.mark.parametrize("status", [0, 5])
@_windows_coverage_simulation
def test_windows_file_disposition_maps_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    target = tmp_path / "artifact.json"
    target.write_bytes(b"safe")
    descriptor = os.open(target, primitives.READ_FLAGS)
    set_information = _install_fake_ntdll(monkeypatch, status)

    try:
        if status == 0:
            primitives._windows_set_file_disposition(descriptor)
        else:
            with pytest.raises(OSError, match="injected NT failure"):
                primitives._windows_set_file_disposition(descriptor)
    finally:
        os.close(descriptor)

    assert set_information.calls


@pytest.mark.parametrize("status", [0, 5])
@_windows_coverage_simulation
def test_windows_hard_link_maps_status_and_closes_temporary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    temporary = tmp_path / ".result.tmp"
    temporary.write_bytes(b"safe")
    target = tmp_path / "result.json"
    parent_fd = os.open(tmp_path, primitives._DIRECTORY_FLAGS)
    descriptor = os.open(temporary, primitives.READ_FLAGS, dir_fd=parent_fd)
    set_information = _install_fake_ntdll(monkeypatch, status)
    monkeypatch.setattr(
        primitives,
        "_open_windows_relative",
        lambda *_args, **_kwargs: descriptor,
    )

    if status == 0:
        primitives._windows_create_hard_link(
            primitives.DirectoryEntryPath(parent_fd, temporary.name),
            primitives.DirectoryEntryPath(parent_fd, target.name),
        )
    else:
        with pytest.raises(OSError, match="injected NT failure"):
            primitives._windows_create_hard_link(
                primitives.DirectoryEntryPath(parent_fd, temporary.name),
                primitives.DirectoryEntryPath(parent_fd, target.name),
            )

    assert set_information.calls
    with pytest.raises(OSError):
        os.fstat(descriptor)
    os.close(parent_fd)


@_windows_coverage_simulation
def test_windows_directory_entry_primitives_use_safe_handles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = os.open(tmp_path, primitives._DIRECTORY_FLAGS)
    child = tmp_path / "artifacts"
    child.mkdir()
    child_fd = os.open(child, primitives._DIRECTORY_FLAGS)
    closed: list[int] = []
    fake_kernel32 = _FakeWinApi()
    fake_kernel32.CloseHandle = _FakeWinFunction(None)

    def load_dll(name: str, *_args: object, **_kwargs: object) -> _FakeWinApi:
        if name != "kernel32":
            raise AssertionError(name)
        return fake_kernel32

    monkeypatch.setattr(primitives, "_IS_WINDOWS", True)
    monkeypatch.setattr(primitives.ctypes, "WinDLL", load_dll, raising=False)
    monkeypatch.setattr(
        primitives,
        "_windows_nt_create",
        lambda *_args, **_kwargs: child_fd,
    )

    def duplicate_child(*_args: object, **_kwargs: object) -> int:
        return os.dup(child_fd)

    monkeypatch.setattr(primitives, "_open_windows_relative", duplicate_child)

    def record_disposition(descriptor: int) -> None:
        closed.append(descriptor)

    monkeypatch.setattr(primitives, "_windows_set_file_disposition", record_disposition)

    primitives.make_directory_entry(
        primitives.DirectoryEntryPath(parent_fd, child.name)
    )
    assert stat.S_ISDIR(
        primitives.stat_entry(
            primitives.DirectoryEntryPath(parent_fd, child.name)
        ).st_mode
    )
    primitives.unlink_entry(primitives.DirectoryEntryPath(parent_fd, child.name))

    assert len(closed) == 1
    assert fake_kernel32.CloseHandle.calls
    os.close(child_fd)
    os.close(parent_fd)


@_windows_coverage_simulation
def test_windows_link_entries_require_anchored_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(primitives, "_IS_WINDOWS", True)
    linked: list[tuple[object, object]] = []

    def record_link(temporary: object, target: object) -> None:
        linked.append((temporary, target))

    monkeypatch.setattr(primitives, "_windows_create_hard_link", record_link)
    parent_fd = 1
    temporary = primitives.DirectoryEntryPath(parent_fd, "temporary")
    target = primitives.DirectoryEntryPath(parent_fd, "target")

    primitives.link_entries(temporary, target)

    assert linked == [(temporary, target)]
    with pytest.raises(OSError, match="anchored Windows hard-link"):
        primitives.link_entries(temporary, Path("target.json"))


@_windows_coverage_simulation
def test_windows_nofollow_closes_descriptors_on_reparse_and_stat_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "artifact.json"
    target.write_bytes(b"safe")
    descriptor = os.open(target, primitives.READ_FLAGS)
    opened: list[int] = []

    def open_relative(*_args: object, **_kwargs: object) -> int:
        opened.append(descriptor)
        return descriptor

    def fail_fstat(_descriptor: int) -> os.stat_result:
        raise OSError("injected stat failure")

    monkeypatch.setattr(primitives, "_open_windows_relative", open_relative)
    monkeypatch.setattr(primitives.os, "fstat", fail_fstat)

    with pytest.raises(OSError, match="injected stat failure"):
        primitives._open_windows_nofollow(
            primitives.DirectoryEntryPath(1, target.name),
            primitives.READ_FLAGS,
        )

    with pytest.raises(OSError):
        os.fstat(descriptor)


@_windows_coverage_simulation
def test_windows_open_file_and_directory_use_masks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "artifacts"
    directory.mkdir()
    directory_fd = os.open(directory, primitives._DIRECTORY_FLAGS)
    requested: list[tuple[object, int | None]] = []

    def open_windows(
        path: object,
        _flags: int,
        *,
        access: int | None = None,
    ) -> int:
        requested.append((path, access))
        return directory_fd

    monkeypatch.setattr(primitives, "_HAS_ATOMIC_NOFOLLOW", False)
    monkeypatch.setattr(primitives, "_IS_WINDOWS", True)
    monkeypatch.setattr(primitives, "_open_windows_nofollow", open_windows)

    opened_file = primitives.open_file(
        primitives.DirectoryEntryPath(directory_fd, "artifact.json"),
        primitives._WRITE_FILE_FLAGS,
    )
    opened_directory = primitives.open_directory(
        primitives.DirectoryEntryPath(directory_fd, "child"), durable=True
    )

    assert opened_file == directory_fd
    assert opened_directory == directory_fd
    assert requested[-1][1] == primitives._WINDOWS_DURABLE_DIRECTORY_ACCESS
    os.close(directory_fd)


@_windows_coverage_simulation
def test_windows_open_directory_rejects_and_closes_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "artifact.json"
    target.write_bytes(b"safe")
    descriptor = os.open(target, primitives.READ_FLAGS)
    monkeypatch.setattr(primitives, "_IS_WINDOWS", True)
    monkeypatch.setattr(
        primitives,
        "_open_windows_nofollow",
        lambda *_args, **_kwargs: descriptor,
    )

    with pytest.raises(OSError, match="artifact path is not a directory"):
        primitives.open_directory(target)

    with pytest.raises(OSError):
        os.fstat(descriptor)
