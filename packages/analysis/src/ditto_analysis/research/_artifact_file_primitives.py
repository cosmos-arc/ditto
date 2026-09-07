"""Closed-file and no-clobber primitives for indexed artifacts."""

from __future__ import annotations

import ctypes
import os
import stat
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from ditto_analysis.research.artifact_measurement import (
    ArtifactMeasurement as _ArtifactMeasurement,
)
from ditto_analysis.research.artifact_measurement import (
    measure_json_bytes as _measure_json_bytes,
)
from ditto_analysis.research.artifact_measurement import (
    measure_parquet_bytes as _measure_parquet_bytes,
)

_IS_WINDOWS = sys.platform == "win32"
_HAS_ATOMIC_NOFOLLOW = hasattr(os, "O_NOFOLLOW")
_WINDOWS_DIRECTORY_REQUEST = 1 << 30
_WINDOWS_DIRECTORY_FLAGS = _WINDOWS_DIRECTORY_REQUEST if _IS_WINDOWS else 0
READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_BINARY", 0)
    | _WINDOWS_DIRECTORY_FLAGS
)
_WRITE_FILE_FLAGS = (
    os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
)
SYNC_FLAGS = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


@dataclass(frozen=True)
class DirectoryEntryPath:
    """Path-like test surface backed by a stable open directory descriptor."""

    parent_fd: int
    name: str

    @property
    def parent(self) -> int:
        """Expose stable parent identity for publication-order assertions."""
        return self.parent_fd

    @property
    def suffix(self) -> str:
        """Return the leaf suffix without resolving through a process filesystem."""
        return Path(self.name).suffix

    def exists(self) -> bool:
        """Check the anchored directory entry without following symlinks."""
        try:
            stat_entry(self)
        except FileNotFoundError:
            return False
        return True


type ArtifactFilePath = Path | DirectoryEntryPath


class _WindowsIoStatusBlock(ctypes.Structure):
    _fields_ = [
        ("status", ctypes.c_long),
        ("pointer", ctypes.c_void_p),
    ]


def _raw_open(path: ArtifactFilePath, flags: int, mode: int = 0o777) -> int:
    if isinstance(path, DirectoryEntryPath):
        return os.open(path.name, flags, mode, dir_fd=path.parent_fd)
    return os.open(path, flags, mode)


def _windows_access(flags: int) -> int:
    access = 0x00100000  # SYNCHRONIZE
    access_mode = flags & os.O_ACCMODE
    if access_mode == os.O_WRONLY:
        access |= 0x40000000  # GENERIC_WRITE
    elif access_mode == os.O_RDWR:
        access |= 0xC0000000  # GENERIC_READ | GENERIC_WRITE
    else:
        access |= 0x80000000  # GENERIC_READ
    if flags & os.O_APPEND:
        access |= 0x0004  # FILE_APPEND_DATA
    return access


def _windows_absolute_creation(flags: int) -> int:
    if flags & os.O_CREAT and flags & os.O_EXCL:
        return 1  # CREATE_NEW
    if flags & os.O_CREAT and flags & os.O_TRUNC:
        return 2  # CREATE_ALWAYS
    if flags & os.O_CREAT:
        return 4  # OPEN_ALWAYS
    if flags & os.O_TRUNC:
        return 5  # TRUNCATE_EXISTING
    return 3  # OPEN_EXISTING


def _windows_relative_creation(flags: int) -> int:
    if flags & os.O_CREAT and flags & os.O_EXCL:
        return 2  # FILE_CREATE
    if flags & os.O_CREAT and flags & os.O_TRUNC:
        return 5  # FILE_OVERWRITE_IF
    if flags & os.O_CREAT:
        return 3  # FILE_OPEN_IF
    if flags & os.O_TRUNC:
        return 4  # FILE_OVERWRITE
    return 1  # FILE_OPEN


def _open_windows_absolute(
    path: Path,
    flags: int,
    *,
    access: int | None = None,
) -> int:
    """Open an absolute entry through Win32 without following a reparse point."""
    import msvcrt  # noqa: PLC0415 - unavailable on non-Windows platforms

    access = _windows_access(flags) if access is None else access
    creation = _windows_absolute_creation(flags)

    winapi = ctypes.WinDLL("kernel32", use_last_error=True)
    winapi.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    winapi.CreateFileW.restype = ctypes.c_void_p
    handle = winapi.CreateFileW(
        ctypes.c_wchar_p(str(path)),
        access,
        7,  # FILE_SHARE_READ | WRITE | DELETE
        None,
        creation,
        0x02200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        None,
    )
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return msvcrt.open_osfhandle(handle, _windows_fd_flags(flags))
    except OSError:
        winapi.CloseHandle(handle)
        raise


def _windows_fd_flags(flags: int) -> int:
    return flags & (
        os.O_ACCMODE
        | getattr(os, "O_APPEND", 0)
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_TEXT", 0)
    )


def _windows_nt_create(
    path: DirectoryEntryPath,
    access: int,
    disposition: int,
    create_options: int,
) -> int:
    """Create/open one directory-anchored NT handle without following reparse points."""
    import msvcrt  # noqa: PLC0415 - unavailable on non-Windows platforms

    class UnicodeString(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_uint16),
            ("maximum_length", ctypes.c_uint16),
            ("buffer", ctypes.c_wchar_p),
        ]

    class ObjectAttributes(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("root_directory", ctypes.c_void_p),
            ("object_name", ctypes.POINTER(UnicodeString)),
            ("attributes", ctypes.c_ulong),
            ("security_descriptor", ctypes.c_void_p),
            ("security_quality_of_service", ctypes.c_void_p),
        ]

    name = ctypes.create_unicode_buffer(path.name)
    object_name = UnicodeString(
        length=ctypes.sizeof(name) - 2,
        maximum_length=ctypes.sizeof(name),
        buffer=name,
    )
    parent_handle = msvcrt.get_osfhandle(path.parent_fd)
    attributes = ObjectAttributes(
        length=ctypes.sizeof(ObjectAttributes),
        root_directory=parent_handle,
        object_name=ctypes.pointer(object_name),
        attributes=0x40,  # OBJ_CASE_INSENSITIVE
    )
    status_block = _WindowsIoStatusBlock()
    handle = ctypes.c_void_p()
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtCreateFile.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_uint32,
        ctypes.POINTER(ObjectAttributes),
        ctypes.POINTER(_WindowsIoStatusBlock),
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    ntdll.NtCreateFile.restype = ctypes.c_long
    ntdll.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
    ntdll.RtlNtStatusToDosError.restype = ctypes.c_uint32
    status = ntdll.NtCreateFile(
        ctypes.byref(handle),
        access,
        ctypes.byref(attributes),
        ctypes.byref(status_block),
        None,
        0x80,  # FILE_ATTRIBUTE_NORMAL
        7,  # FILE_SHARE_READ | WRITE | DELETE
        disposition,
        create_options,
        None,
        0,
    )
    handle_value = handle.value
    if status != 0 or handle_value is None:
        win_error = ntdll.RtlNtStatusToDosError(ctypes.c_ulong(status & 0xFFFFFFFF))
        raise ctypes.WinError(win_error)
    return handle_value


def _open_windows_relative(
    path: DirectoryEntryPath,
    flags: int,
    *,
    access: int | None = None,
) -> int:
    """Return a CRT descriptor for a directory-anchored NT no-follow open."""
    import msvcrt  # noqa: PLC0415 - unavailable on non-Windows platforms

    create_options = 0x00200020  # OPEN_REPARSE_POINT | SYNCHRONOUS_IO_NONALERT
    if flags & (_WINDOWS_DIRECTORY_REQUEST | getattr(os, "O_DIRECTORY", 0)):
        create_options |= 0x1  # FILE_DIRECTORY_FILE
    handle = _windows_nt_create(
        path,
        access if access is not None else _windows_access(flags),
        _windows_relative_creation(flags),
        create_options,
    )
    try:
        return msvcrt.open_osfhandle(handle, _windows_fd_flags(flags))
    except OSError:
        ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(handle))
        raise


def _windows_set_file_disposition(descriptor: int) -> None:
    """Delete the object held by a descriptor without traversing a reparse point."""
    import msvcrt  # noqa: PLC0415 - unavailable on non-Windows platforms

    disposition = ctypes.c_uint32(3)  # DELETE | POSIX_SEMANTICS
    status_block = _WindowsIoStatusBlock()
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtSetInformationFile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
    ]
    ntdll.NtSetInformationFile.restype = ctypes.c_long
    ntdll.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
    ntdll.RtlNtStatusToDosError.restype = ctypes.c_uint32
    status = ntdll.NtSetInformationFile(
        msvcrt.get_osfhandle(descriptor),
        ctypes.byref(status_block),
        ctypes.byref(disposition),
        ctypes.sizeof(disposition),
        64,  # FileDispositionInformationEx
    )
    if status != 0:
        win_error = ntdll.RtlNtStatusToDosError(ctypes.c_ulong(status & 0xFFFFFFFF))
        raise ctypes.WinError(win_error)


def _windows_create_hard_link(
    temporary: DirectoryEntryPath,
    target: DirectoryEntryPath,
) -> None:
    """Link a staged file into a stable target directory without replacement."""
    import msvcrt  # noqa: PLC0415 - unavailable on non-Windows platforms

    descriptor = _open_windows_relative(
        temporary,
        os.O_RDONLY,
        access=0x00100100,  # SYNCHRONIZE | DELETE | FILE_WRITE_ATTRIBUTES
    )
    name_bytes = target.name.encode("utf-16-le")
    # FILE_LINK_INFORMATION on the supported Windows x64 ABI.
    information = (
        struct.pack(
            "<B7xQI",
            0,  # ReplaceIfExists
            msvcrt.get_osfhandle(target.parent_fd),
            len(name_bytes),
        )
        + name_bytes
    )
    buffer = (ctypes.c_ubyte * len(information)).from_buffer_copy(information)
    status_block = _WindowsIoStatusBlock()
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtSetInformationFile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
    ]
    ntdll.NtSetInformationFile.restype = ctypes.c_long
    ntdll.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
    ntdll.RtlNtStatusToDosError.restype = ctypes.c_uint32
    try:
        status = ntdll.NtSetInformationFile(
            msvcrt.get_osfhandle(descriptor),
            ctypes.byref(status_block),
            buffer,
            len(information),
            72,  # FileLinkInformation
        )
        if status != 0:
            win_error = ntdll.RtlNtStatusToDosError(ctypes.c_ulong(status & 0xFFFFFFFF))
            raise ctypes.WinError(win_error)
    finally:
        os.close(descriptor)


def make_directory_entry(path: DirectoryEntryPath) -> None:
    """Create one directory entry in its stable parent."""
    if _IS_WINDOWS:
        handle = _windows_nt_create(
            path,
            0x80010002,  # SYNCHRONIZE | GENERIC_READ | FILE_WRITE_DATA
            2,  # FILE_CREATE
            0x00200021,  # OPEN_REPARSE_POINT | SYNCHRONOUS_IO | DIRECTORY
        )
        ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(handle))
        return
    os.mkdir(path.name, dir_fd=path.parent_fd)


def stat_entry(path: ArtifactFilePath) -> os.stat_result:
    """Stat the final entry itself, never its reparse target."""
    if _IS_WINDOWS and isinstance(path, DirectoryEntryPath):
        descriptor = _open_windows_relative(path, READ_FLAGS)
        try:
            return os.fstat(descriptor)
        finally:
            os.close(descriptor)
    if isinstance(path, DirectoryEntryPath):
        return os.stat(path.name, dir_fd=path.parent_fd, follow_symlinks=False)
    return path.lstat()


def unlink_entry(path: DirectoryEntryPath) -> None:
    """Unlink one directory entry without traversing a reparse point."""
    if _IS_WINDOWS:
        descriptor = _open_windows_relative(
            path,
            os.O_RDONLY,
            access=0x00110000,  # SYNCHRONIZE | DELETE
        )
        try:
            _windows_set_file_disposition(descriptor)
        finally:
            os.close(descriptor)
        return
    os.unlink(path.name, dir_fd=path.parent_fd)


def fsync_entry(descriptor: int) -> None:
    """Flush one open descriptor."""
    os.fsync(descriptor)


def link_entries(
    temporary: ArtifactFilePath,
    target: ArtifactFilePath,
) -> None:
    """Create a no-replacement hard link between two entries."""
    if _IS_WINDOWS:
        if isinstance(temporary, DirectoryEntryPath) and isinstance(
            target, DirectoryEntryPath
        ):
            _windows_create_hard_link(temporary, target)
            return
        raise OSError("anchored Windows hard-link entries are required")
    if isinstance(temporary, DirectoryEntryPath):
        if isinstance(target, DirectoryEntryPath):
            os.link(
                temporary.name,
                target.name,
                src_dir_fd=temporary.parent_fd,
                dst_dir_fd=target.parent_fd,
                follow_symlinks=False,
            )
        else:
            os.link(
                temporary.name,
                target,
                src_dir_fd=temporary.parent_fd,
                follow_symlinks=False,
            )
    elif isinstance(target, DirectoryEntryPath):
        os.link(
            temporary,
            target.name,
            dst_dir_fd=target.parent_fd,
            follow_symlinks=False,
        )
    else:
        os.link(temporary, target, follow_symlinks=False)


def _open_windows_nofollow(
    path: ArtifactFilePath,
    flags: int,
    *,
    access: int | None = None,
) -> int:
    if isinstance(path, DirectoryEntryPath):
        descriptor = _open_windows_relative(path, flags, access=access)
    else:
        descriptor = _open_windows_absolute(path, flags, access=access)
    try:
        opened = os.fstat(descriptor)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if stat.S_ISLNK(opened.st_mode) or opened.st_file_attributes & reparse:
            raise OSError("artifact path is a reparse point")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def open_file(path: ArtifactFilePath, flags: int, mode: int = 0o777) -> int:
    """
    Open an entry without following a final symlink.

    Existing entries require atomic ``O_NOFOLLOW`` or the native Windows
    no-reparse-point primitive. Other platforms fail closed; exclusive creation
    remains safe there because it cannot replace an existing entry.
    """
    if _HAS_ATOMIC_NOFOLLOW:
        return _raw_open(path, flags, mode)
    if _IS_WINDOWS:
        return _open_windows_nofollow(path, flags)
    if flags & os.O_CREAT and flags & os.O_EXCL:
        return _raw_open(path, flags, mode)
    raise OSError("atomic no-follow open unavailable")


def open_directory(path: ArtifactFilePath, *, durable: bool = False) -> int:
    """
    Open a directory without following a final symlink.

    ``durable`` requests the write access Windows requires for directory
    flushing; readers use the ordinary read-only handle.
    """
    access = (
        0x40100000 if durable and _IS_WINDOWS else None
    )  # SYNCHRONIZE | GENERIC_WRITE
    if access is None or not _IS_WINDOWS:
        descriptor = open_file(path, _DIRECTORY_FLAGS)
    else:
        descriptor = _open_windows_nofollow(path, _DIRECTORY_FLAGS, access=access)
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("artifact path is not a directory")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def write_json_file(path: ArtifactFilePath, payload: bytes) -> None:
    """Write canonical JSON bytes to an already-created safe path."""
    descriptor = open_file(path, _WRITE_FILE_FLAGS)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()


def write_parquet_file(path: ArtifactFilePath, frame: pl.DataFrame) -> None:
    """Write one frame to an already-created safe path."""
    descriptor = open_file(path, _WRITE_FILE_FLAGS)
    with os.fdopen(descriptor, "wb") as stream:
        frame.write_parquet(stream)
        stream.flush()


def _read_path_bytes(path: ArtifactFilePath) -> bytes:
    descriptor = open_file(path, READ_FLAGS)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("artifact is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(descriptor)


def measure_json_artifact(path: ArtifactFilePath) -> _ArtifactMeasurement:
    """Measure one closed staged JSON file."""
    return _measure_json_bytes(_read_path_bytes(path))


def measure_parquet_artifact(path: ArtifactFilePath) -> _ArtifactMeasurement:
    """Measure one closed staged Parquet file."""
    return _measure_parquet_bytes(_read_path_bytes(path))


def publish_no_clobber(
    temporary: ArtifactFilePath,
    target: ArtifactFilePath,
) -> bool:
    """Atomically expose one inode without replacing an existing target."""
    try:
        link_entries(temporary, target)

    except FileExistsError:
        return False
    return True
