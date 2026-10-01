# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("frontend/dist", "frontend/dist"),
        ("branding", "branding"),
        ("LICENSE", "docs"),
        ("docs/PRIVACY.md", "docs"),
        ("docs/LGPL_COMPLIANCE.md", "docs"),
        ("docs/THIRD_PARTY_NOTICES.md", "docs"),
        ("docs/THIRD_PARTY_LICENSES.txt", "docs"),
    ],
    hiddenimports=["pystray._win32"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "IPython", "Cython", "PyQt5", "PyQt6", "PySide2", "PySide6",
        "matplotlib", "jedi", "lxml", "pygame", "psutil", "zmq",
        "bcrypt", "chardet", "cryptography", "pygments", "rich", "tzdata",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="D5Macro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="branding/d5macro.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="D5Macro",
)
