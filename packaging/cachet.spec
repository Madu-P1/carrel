# PyInstaller spec for the bundled Cachet desktop app (onefile, double-click).
#
# Build:  pyinstaller --clean --noconfirm packaging/cachet.spec
# Output: dist/Cachet (macOS/Linux) or dist/Cachet.exe (Windows).
#
# Scope = the deterministic core. The heavy ML deps (Docling OCR, fastembed
# embeddings + onnxruntime) are LAZY-imported in the backend, so excluding them
# here keeps the bundle to tens of MB and the app falls back to FTS5 retrieval;
# scanned-PDF OCR is unavailable. DOCX / digital-PDF + cite-existence +
# verbatim-quote all work. See packaging/cachet_frozen.py.

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

ROOT = Path(SPECPATH).resolve().parent  # packaging/ -> repo root

# --- read-only resources the app serves / reads ---
datas = [
    (str(ROOT / "frontend" / "dist-cachet"), "dist-cachet"),  # the served frontend
    (str(ROOT / "migrations"), "migrations"),  # DB schema, source of truth
    (str(ROOT / "static"), "static"),  # main.py mounts /static unconditionally
]
_schema = ROOT / "schema.sql"
if _schema.is_file():
    datas.append((str(_schema), "."))
datas += collect_data_files("sqlite_vec")  # the loadable vec0 extension payload

# --- the sqlite-vec native extension (.dylib / .dll / .so) ---
binaries = collect_dynamic_libs("sqlite_vec")

# --- follow the backend's lazy/in-function imports that actually run ---
# main.py imports several modules inside functions (lifespan, route registration),
# which PyInstaller's static graph would miss; collect every submodule of the app
# packages so nothing is absent at runtime.
hiddenimports = (
    collect_submodules("routes")
    + collect_submodules("services")
    + collect_submodules("ai")
    + [
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "sqlite_vec",
    ]
)

# --- keep the heavy ML stack OUT (lazy in the backend; not in this scope) ---
excludes = [
    "docling",
    "docling_core",
    "docling_ibm_models",
    "fastembed",
    "onnxruntime",
    "onnx",
    "torch",
    "transformers",
    "tokenizers",
    "huggingface_hub",
    "tkinter",
]

a = Analysis(
    [str(ROOT / "packaging" / "cachet_frozen.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Cachet",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,  # shows the "running at http://127.0.0.1:..." line; windowed later
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
