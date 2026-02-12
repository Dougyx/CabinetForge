# CabinetForge

CabinetForge is a Flask web UI for editing CAB files. It supports loading a CAB, replacing files, adding files, removing files, and saving a repacked CAB while maintaining Windows CE-relevant cabinet layout characteristics from the source archive.

## Core Behavior

- Uses per-session workspaces so multiple users can work concurrently in a single app instance.
- Loads CABs into an in-memory editor and keeps `_setup.xml` mappings synchronized during add/remove operations.
- Exposes file-level edit actions through the web UI and returns a downloadable repacked CAB.
- Reports Authenticode status for the loaded CAB.

## Windows CE CAB Repacking

CabinetForge uses an internal CE-aware writer for output (`cabinetforge/ce_cab_writer.py`). On load, it captures layout metadata from the source CAB and reuses it when saving.

Preserved layout/header characteristics:
- `CFHEADER.flags` reserved bit (`0x0004`) state.
- `setID`.
- Reserved sizes: `cbCFHeader`, `cbCFFolder`, `cbCFData`.
- Reserved header bytes (`abReserve`).
- Per-folder reserve byte blocks.
- Source file order.
- Source file-to-folder mapping.
- Folder count implied by the preserved mapping.

Example characteristics from `app.CAB`:
- `flags = 0x0004` (reserved fields enabled)
- `cFolders = 33`
- `cFiles = 47`
- `cbCFHeader = 0`
- `cbCFFolder = 64`
- `cbCFData = 0`

These values are read from each loaded CAB and carried forward during repack.

## Limitations

- Per-`CFDATA` reserve payload bytes are emitted as zero-filled when `cbCFData > 0`. Reserve size is preserved, original reserve payload content is not.
- Chained/multi-cab sets (prev/next cabinet linkage) are not supported.
- CAB digital signatures are not preserved after edits. Modified CABs should be treated as unsigned unless re-signed externally.
- Workspace state is in-process memory. Multi-worker/multi-instance deployments require a shared state backend before scale-out.

## Project Layout

- `app.py`: local entrypoint.
- `cabinetforge/app_factory.py`: Flask app factory.
- `cabinetforge/routes.py`: HTTP routes and handlers.
- `cabinetforge/cab_editor.py`: editor logic for CAB entries and `_setup.xml`.
- `cabinetforge/ce_cab_writer.py`: CE-aware CAB layout parser/writer.
- `cabinetforge/validation.py`: upload validation and persistence.
- `cabinetforge/signature.py`: Authenticode status helper.
- `cabinetforge/workspace.py`: session workspace manager.
- `cabinetforge/config.py`: runtime configuration.

## Run Locally

```powershell
cd c:\Users\Lewis\OneDrive\Desktop\CABs\cab_webui
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Run Offline

Dependencies are vendored in `vendor/wheels`.

PowerShell:

```powershell
.\scripts\install_offline.ps1
python app.py
```

CMD:

```bat
scripts\install_offline.bat
python app.py
```

## Docker

```powershell
docker compose up --build
```

Open `http://127.0.0.1:8000`.

The container installs from local wheels in `vendor/wheels`, so it does not require external PyPI access during build.

## Configuration

- `CABINETFORGE_SECRET_KEY`: Flask secret key.
- `CABINETFORGE_MAX_UPLOAD_BYTES`: max upload size in bytes.
- `CABINETFORGE_UPLOAD_DIR`: temp storage for uploaded CABs.
- `CABINETFORGE_EXTRACT_DIR`: temp storage for extracted files.
- `CABINETFORGE_SESSION_TTL`: session workspace retention in seconds.

## Security

- Upload validation checks extension, `MSCF` header, and parser acceptance.
- Signature status is informational.
- Editing content invalidates prior signature trust.
- CabinetForge does not re-sign CAB output.
