"""Upload validation and persistence helpers."""

from __future__ import annotations

import uuid
from pathlib import Path

from cabarchive import CabArchive
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


def is_valid_cab_upload(upload: FileStorage) -> tuple[bool, str]:
    """Validate extension, magic header, and parseability for uploaded CAB."""

    filename = secure_filename(upload.filename or "")
    if not filename:
        return False, "Missing filename"
    if Path(filename).suffix.lower() != ".cab":
        return False, "Only .cab files are allowed"

    stream = upload.stream
    if not stream.seekable():
        return False, "Upload stream is not seekable"

    pos = stream.tell()
    header = stream.read(4)
    stream.seek(pos)
    if header != b"MSCF":
        return False, "File does not have valid CAB header"

    try:
        data = upload.read()
        upload.stream.seek(0)
        CabArchive(data)
    except Exception:
        return False, "CAB parser rejected file"

    return True, ""


def save_uploaded_cab(upload: FileStorage, upload_dir: Path) -> Path:
    """Persist a validated CAB upload into application workspace storage."""

    valid, reason = is_valid_cab_upload(upload)
    if not valid:
        raise ValueError(reason)

    filename = secure_filename(upload.filename or "upload.cab")
    target = upload_dir / f"{Path(filename).stem}_{uuid.uuid4().hex[:8]}.cab"
    upload.save(target)
    return target
