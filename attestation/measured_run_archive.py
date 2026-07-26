#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Deterministic, link-free archive transport for measured-run packages."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile


class ArchiveError(RuntimeError):
    pass


def _safe_name(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(
        part in ("", ".", "..") for part in path.parts
    ):
        raise ArchiveError(f"unsafe measured-run archive member: {value!r}")
    return value


def _stable_metadata(metadata: os.stat_result) -> tuple[int, ...]:
    """Return the fields that must not change while an entry is archived."""

    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _require_same_entry(
    expected: os.stat_result, actual: os.stat_result, relative: str
) -> None:
    if _stable_metadata(expected) != _stable_metadata(actual):
        raise ArchiveError(f"measured-run package changed while archiving: {relative}")


def _member_info(relative: str, metadata: os.stat_result) -> tarfile.TarInfo:
    info = tarfile.TarInfo(relative)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    if stat.S_ISDIR(metadata.st_mode):
        info.type = tarfile.DIRTYPE
        info.mode = 0o500
    else:
        info.type = tarfile.REGTYPE
        info.mode = 0o500 if metadata.st_mode & 0o111 else 0o400
        info.size = metadata.st_size
    return info


def _archive_directory(
    archive: tarfile.TarFile,
    directory_descriptor: int,
    relative_parts: tuple[str, ...] = (),
) -> None:
    """Archive one directory through already-open, non-following descriptors."""

    directory_before = os.fstat(directory_descriptor)
    if not stat.S_ISDIR(directory_before.st_mode):
        raise ArchiveError("measured-run archive root changed type")
    try:
        with os.scandir(directory_descriptor) as iterator:
            entries = [
                (entry.name, entry.stat(follow_symlinks=False)) for entry in iterator
            ]
    except OSError as error:
        raise ArchiveError(f"cannot enumerate measured-run package: {error}") from error

    for name, listed_metadata in sorted(entries, key=lambda item: item[0]):
        relative = _safe_name(PurePosixPath(*relative_parts, name).as_posix())
        if stat.S_ISLNK(listed_metadata.st_mode):
            raise ArchiveError(f"measured-run package contains a symlink: {relative}")
        is_directory = stat.S_ISDIR(listed_metadata.st_mode)
        is_regular = stat.S_ISREG(listed_metadata.st_mode)
        if not (is_directory or is_regular):
            raise ArchiveError(f"measured-run package contains a special file: {relative}")

        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        if is_directory:
            flags |= os.O_DIRECTORY
        else:
            # Avoid blocking if an attacker swaps a regular file for a FIFO
            # between directory enumeration and openat(2).
            flags |= os.O_NONBLOCK
        try:
            descriptor = os.open(name, flags, dir_fd=directory_descriptor)
        except OSError as error:
            raise ArchiveError(
                f"cannot open measured-run package member without following links: {relative}: {error}"
            ) from error
        try:
            opened_metadata = os.fstat(descriptor)
            _require_same_entry(listed_metadata, opened_metadata, relative)
            if is_directory:
                archive.addfile(_member_info(relative, opened_metadata))
                _archive_directory(
                    archive, descriptor, (*relative_parts, name)
                )
            else:
                if opened_metadata.st_nlink != 1:
                    raise ArchiveError(
                        f"measured-run package contains a hard-linked file: {relative}"
                    )
                info = _member_info(relative, opened_metadata)
                with os.fdopen(os.dup(descriptor), "rb") as source:
                    archive.addfile(info, source)
                _require_same_entry(opened_metadata, os.fstat(descriptor), relative)
        finally:
            os.close(descriptor)

    _require_same_entry(
        directory_before,
        os.fstat(directory_descriptor),
        PurePosixPath(*relative_parts).as_posix() or ".",
    )


def create_archive(source_root: Path, destination: Path) -> None:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ArchiveError("measured-run archiving requires O_NOFOLLOW and O_DIRECTORY")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    root_descriptor = -1
    destination_descriptor = -1
    try:
        root_descriptor = os.open(
            source_root,
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        destination_descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(destination_descriptor, "wb") as output:
            destination_descriptor = -1
            with tarfile.open(fileobj=output, mode="w", format=tarfile.GNU_FORMAT) as archive:
                _archive_directory(archive, root_descriptor)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), 0o400)
    except OSError as error:
        destination.unlink(missing_ok=True)
        raise ArchiveError(f"cannot create measured-run archive: {error}") from error
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if destination_descriptor >= 0:
            os.close(destination_descriptor)
        if root_descriptor >= 0:
            os.close(root_descriptor)


def extract_archive(
    archive_path: Path,
    destination_root: Path,
    *,
    maximum_files: int = 100_000,
    maximum_bytes: int = 256 * 1024**3,
) -> None:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ArchiveError("measured-run extraction requires O_NOFOLLOW")
    archive_descriptor = -1
    try:
        archive_descriptor = os.open(
            archive_path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
        archive_before = os.fstat(archive_descriptor)
        if not stat.S_ISREG(archive_before.st_mode) or archive_before.st_nlink != 1:
            raise ArchiveError(
                "measured-run archive must be one non-hard-linked regular file"
            )
        destination_root.mkdir(mode=0o700, parents=False, exist_ok=False)
        seen: set[str] = set()
        total_bytes = 0
        member_count = 0
        with os.fdopen(os.dup(archive_descriptor), "rb") as archive_stream:
            with tarfile.open(fileobj=archive_stream, mode="r|") as archive:
                for member in archive:
                    member_count += 1
                    if member_count > maximum_files:
                        raise ArchiveError(
                            "measured-run archive exceeds the member-count limit"
                        )
                    name = _safe_name(member.name)
                    if name in seen:
                        raise ArchiveError(f"duplicate measured-run archive member: {name}")
                    seen.add(name)
                    if not (member.isdir() or member.isreg()):
                        raise ArchiveError(
                            f"links and special archive members are forbidden: {name}"
                        )
                    if member.uid != 0 or member.gid != 0 or member.mtime != 0:
                        raise ArchiveError(
                            f"archive member metadata is not canonical: {name}"
                        )
                    target = destination_root.joinpath(*PurePosixPath(name).parts)
                    try:
                        target.relative_to(destination_root)
                    except ValueError as error:
                        raise ArchiveError(
                            f"archive member escapes destination: {name}"
                        ) from error
                    if member.isdir():
                        target.mkdir(mode=0o700, parents=True, exist_ok=False)
                        continue
                    total_bytes += member.size
                    if total_bytes > maximum_bytes:
                        raise ArchiveError(
                            "measured-run archive exceeds the extraction byte limit"
                        )
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        raise ArchiveError(f"cannot read archive member: {name}")
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                    descriptor = os.open(
                        target,
                        flags,
                        0o500 if member.mode & 0o111 else 0o400,
                    )
                    try:
                        remaining = member.size
                        while remaining:
                            block = extracted.read(min(1024 * 1024, remaining))
                            if not block:
                                raise ArchiveError(
                                    f"archive member is truncated: {name}"
                                )
                            view = memoryview(block)
                            while view:
                                count = os.write(descriptor, view)
                                view = view[count:]
                            remaining -= len(block)
                        if extracted.read(1):
                            raise ArchiveError(
                                f"archive member exceeds declared size: {name}"
                            )
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
        if member_count == 0:
            raise ArchiveError("measured-run archive has no members")
        _require_same_entry(archive_before, os.fstat(archive_descriptor), str(archive_path))
    except OSError as error:
        shutil.rmtree(destination_root, ignore_errors=True)
        raise ArchiveError(f"cannot extract measured-run archive: {error}") from error
    except BaseException:
        shutil.rmtree(destination_root, ignore_errors=True)
        raise
    finally:
        if archive_descriptor >= 0:
            os.close(archive_descriptor)
