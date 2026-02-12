"""CE-focused CAB layout parser/writer.

This module preserves CAB reserved fields and folder mapping when repacking,
which is required by some Windows CE installers.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Iterable
import zlib

from cabarchive import CabArchive
from cabarchive.utils import (
    FMT_CFDATA,
    FMT_CFFILE,
    FMT_CFFOLDER,
    FMT_CFHEADER,
    FMT_CFHEADER_RESERVE,
    _checksum_compute,
    _chunkify,
)


@dataclass
class CabLayoutTemplate:
    """Layout data captured from an existing CAB."""

    set_id: int
    cb_cfheader: int
    cb_cffolder: int
    cb_cfdata: int
    header_reserve: bytes
    folder_reserves: list[bytes]
    file_order: list[str]
    file_folders: dict[str, int]


@dataclass
class _FolderBuild:
    folder_key: int
    names: list[str]
    reserve: bytes
    blocks: list[tuple[bytes, int]]


def parse_cab_layout(buf: bytes) -> CabLayoutTemplate | None:
    """Parse minimal CAB layout state needed for CE-safe repacks."""

    try:
        (
            sig,
            _cab_size,
            off_cffile,
            _ver_minor,
            _ver_major,
            nr_folders,
            nr_files,
            flags,
            set_id,
            _idx_cab,
        ) = struct.unpack_from(FMT_CFHEADER, buf, 0)
    except struct.error:
        return None

    if sig != b"MSCF":
        return None

    offset = struct.calcsize(FMT_CFHEADER)
    cb_cfheader = 0
    cb_cffolder = 0
    cb_cfdata = 0
    header_reserve = b""
    folder_reserves: list[bytes] = []

    if flags & 0x0004:
        try:
            cb_cfheader, cb_cffolder, cb_cfdata = struct.unpack_from(FMT_CFHEADER_RESERVE, buf, offset)
        except struct.error:
            return None
        offset += struct.calcsize(FMT_CFHEADER_RESERVE)
        header_reserve = bytes(buf[offset : offset + cb_cfheader])
        offset += cb_cfheader

    for _ in range(nr_folders):
        try:
            struct.unpack_from(FMT_CFFOLDER, buf, offset)
        except struct.error:
            return None
        offset += struct.calcsize(FMT_CFFOLDER)
        reserve = bytes(buf[offset : offset + cb_cffolder]) if cb_cffolder else b""
        folder_reserves.append(reserve)
        offset += cb_cffolder

    file_order: list[str] = []
    file_folders: dict[str, int] = {}
    offset = off_cffile
    for _ in range(nr_files):
        try:
            (_usize, _uoff, folder_idx, _date, _time, _attr) = struct.unpack_from(FMT_CFFILE, buf, offset)
        except struct.error:
            return None
        offset += struct.calcsize(FMT_CFFILE)

        end = buf.find(b"\x00", offset)
        if end == -1:
            return None
        name = bytes(buf[offset:end]).decode("latin-1")
        offset = end + 1

        file_order.append(name)
        file_folders[name] = folder_idx

    return CabLayoutTemplate(
        set_id=set_id,
        cb_cfheader=cb_cfheader,
        cb_cffolder=cb_cffolder,
        cb_cfdata=cb_cfdata,
        header_reserve=header_reserve,
        folder_reserves=folder_reserves,
        file_order=file_order,
        file_folders=file_folders,
    )


def build_ce_cab_bytes(
    archive: CabArchive,
    compress: bool,
    template: CabLayoutTemplate | None,
    sort: bool = True,
) -> bytes:
    """Render archive to CAB bytes preserving CE-sensitive layout fields."""

    ordered_names = _order_names(archive, template, sort=sort)
    if not ordered_names:
        raise ValueError("CAB cannot be empty")

    if template is None:
        template = CabLayoutTemplate(
            set_id=getattr(archive, "set_id", 0),
            cb_cfheader=0,
            cb_cffolder=0,
            cb_cfdata=0,
            header_reserve=b"",
            folder_reserves=[],
            file_order=[],
            file_folders={},
        )

    use_reserve = bool(template.cb_cfheader or template.cb_cffolder or template.cb_cfdata or template.header_reserve)
    flags = 0x0004 if use_reserve else 0x0000

    folder_builds = _build_folders(
        archive=archive,
        ordered_names=ordered_names,
        template=template,
        compress=compress,
    )

    folder_count = len(folder_builds)
    if folder_count == 0:
        raise ValueError("CAB cannot be empty")

    header_size = struct.calcsize(FMT_CFHEADER)
    if use_reserve:
        header_size += struct.calcsize(FMT_CFHEADER_RESERVE) + template.cb_cfheader
    folder_table_size = folder_count * (struct.calcsize(FMT_CFFOLDER) + template.cb_cffolder)
    coff_files = header_size + folder_table_size

    folder_index_by_name: dict[str, int] = {}
    for idx, folder in enumerate(folder_builds):
        for name in folder.names:
            folder_index_by_name[name] = idx

    offsets_by_name = _build_uncompressed_offsets(archive, folder_builds)
    cffile_blob = _build_cffile_blob(archive, ordered_names, offsets_by_name, folder_index_by_name)

    cfdata_start = coff_files + len(cffile_blob)
    cffolder_blob, cfdata_blob = _build_folder_and_data_blobs(
        folder_builds=folder_builds,
        cfdata_start=cfdata_start,
        cb_cffolder=template.cb_cffolder,
        cb_cfdata=template.cb_cfdata,
        compress=compress,
    )

    cabinet_size = header_size + len(cffolder_blob) + len(cffile_blob) + len(cfdata_blob)

    header = struct.pack(
        FMT_CFHEADER,
        b"MSCF",
        cabinet_size,
        coff_files,
        3,
        1,
        folder_count,
        len(ordered_names),
        flags,
        template.set_id,
        0,
    )
    blocks: list[bytes] = [header]
    if use_reserve:
        blocks.append(struct.pack(FMT_CFHEADER_RESERVE, template.cb_cfheader, template.cb_cffolder, template.cb_cfdata))
        reserve = template.header_reserve[: template.cb_cfheader]
        if len(reserve) < template.cb_cfheader:
            reserve += b"\x00" * (template.cb_cfheader - len(reserve))
        blocks.append(reserve)

    blocks.append(cffolder_blob)
    blocks.append(cffile_blob)
    blocks.append(cfdata_blob)
    return b"".join(blocks)


def _order_names(archive: CabArchive, template: CabLayoutTemplate | None, sort: bool) -> list[str]:
    names = set(archive.keys())
    ordered: list[str] = []

    if template is not None:
        for name in template.file_order:
            if name in names:
                ordered.append(name)
                names.remove(name)

    extras = sorted(names) if sort else list(names)
    ordered.extend(extras)
    return ordered


def _build_folders(
    archive: CabArchive,
    ordered_names: list[str],
    template: CabLayoutTemplate,
    compress: bool,
) -> list[_FolderBuild]:
    keyed: dict[int, list[str]] = {}
    max_existing = max(template.file_folders.values(), default=-1)
    next_key = max_existing + 1

    for name in ordered_names:
        key = template.file_folders.get(name)
        if key is None:
            key = next_key
            next_key += 1
        keyed.setdefault(key, []).append(name)

    out: list[_FolderBuild] = []
    for key in keyed.keys():
        names = keyed[key]
        reserve = b"\x00" * template.cb_cffolder
        if 0 <= key < len(template.folder_reserves):
            reserve = template.folder_reserves[key]
        if len(reserve) < template.cb_cffolder:
            reserve += b"\x00" * (template.cb_cffolder - len(reserve))
        reserve = reserve[: template.cb_cffolder]

        raw = b"".join((archive[name].buf or b"") for name in names)
        chunks = _chunkify(raw, 0x8000)
        if not chunks:
            chunks = [memoryview(b"")]

        blocks: list[tuple[bytes, int]] = []
        for chunk in chunks:
            plain = bytes(chunk)
            if compress:
                z = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
                encoded = b"CK" + z.compress(plain) + z.flush()
            else:
                encoded = plain
            blocks.append((encoded, len(plain)))

        out.append(_FolderBuild(folder_key=key, names=names, reserve=reserve, blocks=blocks))
    return out


def _build_uncompressed_offsets(archive: CabArchive, folders: Iterable[_FolderBuild]) -> dict[str, int]:
    offsets: dict[str, int] = {}
    for folder in folders:
        offset = 0
        for name in folder.names:
            offsets[name] = offset
            offset += len(archive[name])
    return offsets


def _build_cffile_blob(
    archive: CabArchive,
    ordered_names: list[str],
    offsets_by_name: dict[str, int],
    folder_index_by_name: dict[str, int],
) -> bytes:
    out: list[bytes] = []
    for name in ordered_names:
        cab_file = archive[name]
        filename = getattr(cab_file, "_filename_win32", None) or name
        encoded_name = filename.encode("latin-1", errors="ignore")
        out.append(
            struct.pack(
                FMT_CFFILE,
                len(cab_file),
                offsets_by_name[name],
                folder_index_by_name[name],
                cab_file._date_encode(),
                cab_file._time_encode(),
                cab_file._attr_encode(),
            )
        )
        out.append(encoded_name + b"\x00")
    return b"".join(out)


def _build_folder_and_data_blobs(
    folder_builds: list[_FolderBuild],
    cfdata_start: int,
    cb_cffolder: int,
    cb_cfdata: int,
    compress: bool,
) -> tuple[bytes, bytes]:
    folder_blocks: list[bytes] = []
    data_blocks: list[bytes] = []
    cursor = cfdata_start

    for folder in folder_builds:
        block_bytes = 0
        for encoded, plain_size in folder.blocks:
            checksum = _checksum_compute(encoded)
            hdr = struct.pack("<HH", len(encoded), plain_size)
            checksum = _checksum_compute(hdr, checksum)
            data_blocks.append(struct.pack(FMT_CFDATA, checksum, len(encoded), plain_size))
            if cb_cfdata:
                data_blocks.append(b"\x00" * cb_cfdata)
            data_blocks.append(encoded)
            block_bytes += struct.calcsize(FMT_CFDATA) + cb_cfdata + len(encoded)

        compression_type = 1 if compress else 0
        folder_blocks.append(struct.pack(FMT_CFFOLDER, cursor, len(folder.blocks), compression_type))
        if cb_cffolder:
            folder_blocks.append(folder.reserve)
        cursor += block_bytes

    return b"".join(folder_blocks), b"".join(data_blocks)
