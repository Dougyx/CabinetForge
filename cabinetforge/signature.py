"""Windows Authenticode signature helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def get_signature_status(path: Path) -> dict[str, str]:
    """Return signature details for a CAB file path using PowerShell."""

    script = (
        "$s=Get-AuthenticodeSignature -FilePath '"
        + str(path).replace("'", "''")
        + "';"
        "[pscustomobject]@{"
        "Status=$s.Status.ToString();"
        "StatusMessage=$s.StatusMessage;"
        "Signer=if($s.SignerCertificate){$s.SignerCertificate.Subject}else{''};"
        "Timestamp=if($s.TimeStamperCertificate){$s.TimeStamperCertificate.Subject}else{''}"
        "}|ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {
            "Status": "Unknown",
            "StatusMessage": result.stderr.strip() or "Signature check failed",
            "Signer": "",
            "Timestamp": "",
        }

    try:
        parsed = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {
            "Status": "Unknown",
            "StatusMessage": result.stdout.strip() or "No signature output",
            "Signer": "",
            "Timestamp": "",
        }

    return {
        "Status": str(parsed.get("Status", "Unknown")),
        "StatusMessage": str(parsed.get("StatusMessage", "")),
        "Signer": str(parsed.get("Signer", "")),
        "Timestamp": str(parsed.get("Timestamp", "")),
    }
