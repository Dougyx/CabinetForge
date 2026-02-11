"""Core CAB editing logic independent from Flask routes."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from cabarchive import CabArchive, CabFile
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .signature import get_signature_status


@dataclass
class CabRecord:
    """A display-friendly representation of a CAB entry."""

    display_name: str
    source_name: str
    size: int
    modified: str
    parent_type: str


class CabEditor:
    """In-memory editor for one loaded CAB archive."""

    def __init__(self) -> None:
        self.path: Path | None = None
        self.loaded_name: str = "cabinetforge_output"
        self.archive: CabArchive | None = None
        self.xml_root: ET.Element | None = None
        self.setup_encoding = "utf-8"
        self.records: list[CabRecord] = []
        self.directories: list[str] = []
        self.signature_before: dict[str, str] = {}

    def load(self, path: Path, display_name: str | None = None) -> None:
        """Load and index a CAB file from disk."""

        self.path = path
        candidate = (display_name or path.stem).strip()
        self.loaded_name = Path(candidate).stem or "cabinetforge_output"
        self.archive = CabArchive(path.read_bytes())
        self._load_setup_xml()
        self._rebuild_index()
        self.signature_before = get_signature_status(path)

    def update_file(self, source_name: str, upload: FileStorage) -> None:
        """Replace one CAB payload by source identifier."""

        self._require_archive()
        payload = upload.read()
        if source_name not in self.archive:
            raise KeyError(f"File {source_name} not found in CAB")
        if not payload:
            raise ValueError("Uploaded file is empty")

        self.archive[source_name] = CabFile(payload, mtime=dt.datetime.now())
        self._rebuild_index()

    def remove_file(self, source_name: str) -> None:
        """Remove one file from CAB and corresponding XML mapping."""

        self._require_archive()
        if source_name in self.archive:
            del self.archive[source_name]

        if self.xml_root is not None:
            removed = remove_xml_file_node(self.xml_root, source_name)
            if not removed:
                raise KeyError(f"No matching _setup.xml entry for {source_name}")
            self._update_numfiles()
            self._sync_setup_xml()

        self._rebuild_index()

    def add_file(self, upload: FileStorage, display_name: str, directory: str) -> None:
        """Add one new file payload and append XML mapping if present."""

        self._require_archive()
        filename = secure_filename(upload.filename or "")
        payload = upload.read()
        if not payload:
            raise ValueError("Uploaded file is empty")

        final_name = display_name.strip() if display_name else filename
        if not final_name:
            raise ValueError("Display name is required")

        existing = {name.lower() for name in self.archive.keys()}
        source_name = generate_source_name(final_name, existing)
        self.archive[source_name] = CabFile(payload, mtime=dt.datetime.now())

        if self.xml_root is not None:
            target_parent = resolve_target_parent(self.xml_root, directory)
            if target_parent is None:
                raise ValueError("Could not determine insertion directory in _setup.xml")
            append_xml_file_node(target_parent, final_name, source_name)
            self._update_numfiles()
            self._sync_setup_xml()

        self._rebuild_index()

    def get_file_bytes(self, source_name: str) -> bytes:
        """Return bytes for a source entry from the loaded archive."""

        self._require_archive()
        if source_name not in self.archive:
            raise KeyError(f"Missing file: {source_name}")
        return self.archive[source_name].buf or b""

    def build_cab_bytes(self, compress: bool) -> bytes:
        """Render current in-memory state back to CAB bytes."""

        self._require_archive()
        if self.xml_root is not None:
            self._sync_setup_xml()
        return self.archive.save(compress=compress, sort=True)

    def _require_archive(self) -> None:
        if not self.archive:
            raise RuntimeError("No CAB loaded")

    def _load_setup_xml(self) -> None:
        self.xml_root = None
        self.setup_encoding = "utf-8"
        if not self.archive or "_setup.xml" not in self.archive:
            return

        raw = self.archive["_setup.xml"].buf or b""
        for encoding in ("utf-8", "utf-16", "utf-16le", "latin-1"):
            try:
                text = raw.decode(encoding)
                self.xml_root = ET.fromstring(text)
                self.setup_encoding = encoding
                return
            except Exception:
                continue

    def _rebuild_index(self) -> None:
        self.records = []
        self.directories = []
        if not self.archive:
            return

        if self.xml_root is None:
            for source_name, cab_file in self.archive.items():
                self.records.append(
                    CabRecord(
                        display_name=source_name,
                        source_name=source_name,
                        size=len(cab_file.buf or b""),
                        modified=format_cabfile_time(cab_file),
                        parent_type="",
                    )
                )
            return

        for parent, file_node, extract_node in iter_file_nodes(self.xml_root):
            display_name = file_node.attrib.get("type", "")
            source_name = extract_node.attrib.get("value", "")
            parent_type = parent.attrib.get("type", "")
            if not display_name or not source_name:
                continue
            cab_file = self.archive.get(source_name)
            if cab_file is None:
                continue
            self.records.append(
                CabRecord(
                    display_name=display_name,
                    source_name=source_name,
                    size=len(cab_file.buf or b""),
                    modified=format_cabfile_time(cab_file),
                    parent_type=parent_type,
                )
            )

        self.directories = sorted(
            {
                rec.parent_type
                for rec in self.records
                if rec.parent_type and rec.parent_type.startswith("\\")
            }
        )

    def _update_numfiles(self) -> None:
        if self.xml_root is None:
            return
        parm = self.xml_root.find("./characteristic[@type='Install']/parm[@name='NumFiles']")
        if parm is not None:
            parm.set("value", str(len(self.records)))

    def _sync_setup_xml(self) -> None:
        if not self.archive or self.xml_root is None:
            return
        xml_bytes = ET.tostring(self.xml_root, encoding="utf-8")
        self.archive["_setup.xml"] = CabFile(xml_bytes, mtime=dt.datetime.now())


def iter_file_nodes(root: ET.Element):
    """Yield XML tuples used to build install-file mappings."""

    fileop = root.find("./characteristic[@type='FileOperation']")
    if fileop is None:
        return

    for parent in fileop.findall(".//characteristic"):
        for file_node in parent.findall("./characteristic"):
            extract = file_node.find("./characteristic[@type='Extract']/parm[@name='Source']")
            if extract is not None:
                yield parent, file_node, extract


def remove_xml_file_node(root: ET.Element, source_name: str) -> bool:
    """Remove file mapping node by source name."""

    fileop = root.find("./characteristic[@type='FileOperation']")
    if fileop is None:
        return False

    for parent in fileop.findall(".//characteristic"):
        for file_node in list(parent.findall("./characteristic")):
            extract = file_node.find("./characteristic[@type='Extract']/parm[@name='Source']")
            if extract is None:
                continue
            if (extract.attrib.get("value", "")).lower() == source_name.lower():
                parent.remove(file_node)
                return True
    return False


def append_xml_file_node(parent: ET.Element, display_name: str, source_name: str) -> None:
    """Append a new file mapping node under the chosen install directory."""

    file_node = ET.Element("characteristic", {"type": display_name, "translation": "install"})
    extract_node = ET.SubElement(file_node, "characteristic", {"type": "Extract"})
    ET.SubElement(extract_node, "parm", {"name": "Source", "value": source_name})
    parent.append(file_node)


def resolve_target_parent(root: ET.Element, directory: str) -> ET.Element | None:
    """Find best insertion location for new install file mapping."""

    fileop = root.find("./characteristic[@type='FileOperation']")
    if fileop is None:
        return None

    if directory:
        node = fileop.find(f"./characteristic[@type='{directory}']")
        if node is not None:
            return node

    for node in fileop.findall("./characteristic"):
        if node.attrib.get("translation") == "install":
            return node
    return fileop


def generate_source_name(display_name: str, existing_lower: set[str]) -> str:
    """Generate a short DOS-like source name that does not collide."""

    name = Path(display_name).name
    stem = "".join(ch for ch in Path(name).stem.upper() if ch.isalnum()) or "PYFILE"
    ext = "".join(ch for ch in Path(name).suffix.replace(".", "").upper() if ch.isalnum())
    ext = ext[:3] or "BIN"
    stem = stem[:6]

    for idx in range(1, 1000):
        candidate = f"{stem}~{idx}.{ext}"
        if candidate.lower() not in existing_lower:
            return candidate

    fallback = f"PY{int(dt.datetime.now().timestamp())}.DAT"
    if fallback.lower() not in existing_lower:
        return fallback
    raise RuntimeError("Unable to generate unique Source name")


def format_cabfile_time(cab_file: CabFile) -> str:
    """Format CAB internal timestamp into a compact display string."""

    date = getattr(cab_file, "date", None)
    time = getattr(cab_file, "time", None)
    if not date:
        return ""
    if time:
        return f"{date} {time.strftime('%H:%M:%S')}"
    return str(date)
