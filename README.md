# CabinetForge

CabinetForge is a Flask web UI for editing CAB files (add, replace, remove, repack) with session-isolated workspaces so multiple users can use the app at the same time.

## What Changed

- Session-scoped editor state (no global singleton editor).
- Package-based structure (`cabinetforge/`) with docstrings and clearer module boundaries.
- App factory pattern for production deployment.
- Offline dependency bundle in `vendor/wheels`.
- Docker and docker-compose support.

## Project Structure

- `app.py`: local entrypoint.
- `cabinetforge/app_factory.py`: Flask app factory.
- `cabinetforge/routes.py`: HTTP routes/handlers.
- `cabinetforge/cab_editor.py`: CAB and `_setup.xml` edit logic.
- `cabinetforge/validation.py`: CAB upload validation and persistence.
- `cabinetforge/signature.py`: Authenticode status helper.
- `cabinetforge/workspace.py`: per-session workspace manager.
- `cabinetforge/config.py`: runtime configuration.

## Run Locally (Easy)

```powershell
cd c:\Users\Lewis\OneDrive\Desktop\CABs\cab_webui
python -m pip install -r requirements.txt
python app.py
```

Open: `http://127.0.0.1:5000`

## Run Locally (Offline / No Internet)

Dependencies are vendored in `vendor/wheels`.

PowerShell:

```powershell
cd c:\Users\Lewis\OneDrive\Desktop\CABs\cab_webui
.\scripts\install_offline.ps1
python app.py
```

CMD:

```bat
cd c:\Users\Lewis\OneDrive\Desktop\CABs\cab_webui
scripts\install_offline.bat
python app.py
```

## Docker

Build and run:

```powershell
docker compose up --build
```

Open: `http://127.0.0.1:8000`

The Docker image installs from local wheel files (`vendor/wheels`) so build does not require external PyPI access.

Concurrency note:
- Current workspace storage is in-memory per process.
- Docker default runs one Gunicorn worker with multiple threads, which supports multiple concurrent users safely in one instance.
- For multi-worker or multi-instance deployments, move workspace state to a shared backend (for example Redis) before scaling out.

## Environment Variables

- `CABINETFORGE_SECRET_KEY`: Flask secret key.
- `CABINETFORGE_MAX_UPLOAD_BYTES`: max upload size in bytes.
- `CABINETFORGE_UPLOAD_DIR`: temp storage for uploaded CABs.
- `CABINETFORGE_EXTRACT_DIR`: temp storage for extracted files.
- `CABINETFORGE_SESSION_TTL`: session workspace retention in seconds.

## Security Notes

- CAB upload validation checks extension, `MSCF` header, and parser acceptance.
- CAB signatures are optional.
- Modifying content invalidates prior signature trust.
- App reports signature status; it does not re-sign CABs.
