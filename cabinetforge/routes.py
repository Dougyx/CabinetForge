"""HTTP routes for CabinetForge."""

from __future__ import annotations

from io import BytesIO

from flask import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for

from .validation import save_uploaded_cab


def build_blueprint() -> Blueprint:
    """Create and return the application's route blueprint."""

    bp = Blueprint("cabinetforge", __name__)

    @bp.get("/")
    def index() -> str:
        workspace = current_app.extensions["workspace_manager"].current()
        with workspace.lock:
            workspace.touch()
            return render_template("index.html", editor=workspace.editor)

    @bp.post("/load")
    def load_cab() -> Response:
        upload = request.files.get("cab_file")
        if not upload or not upload.filename:
            flash("Select a CAB file to load", "error")
            return redirect(url_for("cabinetforge.index"))

        workspace = current_app.extensions["workspace_manager"].current()
        with workspace.lock:
            try:
                path = save_uploaded_cab(upload, current_app.config["CABINETFORGE_UPLOAD_DIR"])
                workspace.editor.load(path, display_name=upload.filename)
                flash(f"Loaded CAB: {path.name}", "ok")
            except Exception as exc:
                flash(f"Failed to load CAB: {exc}", "error")
        return redirect(url_for("cabinetforge.index"))

    @bp.post("/update/<source_name>")
    def update_file(source_name: str) -> Response:
        upload = request.files.get("file")
        if not upload or not upload.filename:
            if _wants_json_response():
                return jsonify({"ok": False, "error": "Select a file to upload"}), 400
            flash("Select a file to upload", "error")
            return redirect(url_for("cabinetforge.index"))

        workspace = current_app.extensions["workspace_manager"].current()
        with workspace.lock:
            try:
                workspace.editor.update_file(source_name, upload)
                if _wants_json_response():
                    return jsonify({"ok": True})
                flash(f"Updated {source_name}", "ok")
            except Exception as exc:
                if _wants_json_response():
                    return jsonify({"ok": False, "error": str(exc)}), 400
                flash(f"Update failed for {source_name}: {exc}", "error")
        return redirect(url_for("cabinetforge.index"))

    @bp.post("/remove/<source_name>")
    def remove_file(source_name: str) -> Response:
        workspace = current_app.extensions["workspace_manager"].current()
        with workspace.lock:
            try:
                workspace.editor.remove_file(source_name)
                flash(f"Removed {source_name}", "ok")
            except Exception as exc:
                flash(f"Remove failed for {source_name}: {exc}", "error")
        return redirect(url_for("cabinetforge.index"))

    @bp.post("/add")
    def add_file() -> Response:
        uploads = request.files.getlist("files")
        if not uploads:
            single = request.files.get("file")
            if single and single.filename:
                uploads = [single]

        display_name = request.form.get("display_name", "")
        directory = request.form.get("directory", "")

        if not uploads:
            flash("Select file(s) to add", "error")
            return redirect(url_for("cabinetforge.index"))

        workspace = current_app.extensions["workspace_manager"].current()
        with workspace.lock:
            try:
                added_count = 0
                for upload in uploads:
                    if not upload or not upload.filename:
                        continue
                    current_name = display_name if len(uploads) == 1 else ""
                    workspace.editor.add_file(upload, current_name, directory)
                    added_count += 1
                flash(f"Added {added_count} file(s)", "ok")
            except Exception as exc:
                flash(f"Add failed: {exc}", "error")
        return redirect(url_for("cabinetforge.index"))

    @bp.get("/download/<source_name>")
    def download_file(source_name: str) -> Response:
        workspace = current_app.extensions["workspace_manager"].current()
        with workspace.lock:
            rec = next((r for r in workspace.editor.records if r.source_name == source_name), None)
            if rec is None:
                flash("File not found", "error")
                return redirect(url_for("cabinetforge.index"))

            payload = workspace.editor.get_file_bytes(source_name)
            return send_file(
                BytesIO(payload),
                as_attachment=True,
                download_name=rec.display_name,
            )

    @bp.post("/save")
    def save_cab() -> Response:
        compress = bool(request.form.get("compress"))
        workspace = current_app.extensions["workspace_manager"].current()
        with workspace.lock:
            try:
                payload = workspace.editor.build_cab_bytes(compress=compress)
                source_name = workspace.editor.loaded_name or "cabinetforge_output"
                suffix = "_compressed" if compress else "_repacked"
                filename = f"{source_name}{suffix}.cab"
                return send_file(
                    BytesIO(payload),
                    as_attachment=True,
                    download_name=filename,
                    mimetype="application/vnd.ms-cab-compressed",
                )
            except Exception as exc:
                flash(f"Save failed: {exc}", "error")
                return redirect(url_for("cabinetforge.index"))

    return bp


def _wants_json_response() -> bool:
    """Detect AJAX requests used by the drag/drop replace workflow."""

    return request.headers.get("X-Requested-With") == "XMLHttpRequest"
