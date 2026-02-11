param(
    [string]$PythonExe = "python"
)

& $PythonExe -m pip install --no-index --find-links "vendor/wheels" -r requirements.lock.txt
