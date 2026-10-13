# Nodetavi Macro: LGPL libraries and replacement guide

Nodetavi Macro uses these unmodified third-party libraries:

- pynput 1.8.1, LGPL-3.0-or-later: https://pypi.org/project/pynput/1.8.1/
- pystray 0.19.5, LGPL-3.0-or-later: https://pypi.org/project/pystray/0.19.5/

They are loaded at runtime from editable Python source files in the installation
folder, not from the application executable's internal Python archive. This
distribution uses the replaceable-library approach in LGPLv3 section 4(d)(1).
The proprietary application code is not provided as a public Git tag.

## Included source and licenses

The installer includes `_internal/docs/ThirdParty-Sources.zip`. It contains the
exact upstream source archives, their SHA-256 checksums, license files,
and these instructions. No extra purchase, account, or development environment
is needed to obtain or read the source. Standard ZIP and tar.gz extraction tools
can open the archives. pystray's source archive is pinned to its v0.19.5 Git
commit, because PyPI publishes only a wheel for that version. Its wheel-generated
`_info.py` is supplied separately under `generated/pystray` in the ZIP.
The complete license texts, including the GPLv3 text
incorporated by LGPLv3, are in `THIRD_PARTY_LICENSES.txt`.

The same ZIP is also supplied as a separate download with the official release.
Library source archives may be copied, modified, and redistributed under their
licenses. The app's EULA does not restrict those rights or reverse engineering
to debug modifications of the LGPL portions of the combined work.

## Replace a library on your own computer

1. Exit Nodetavi Macro using its tray menu. Back up the library folder you will change.
2. Open the installation folder. By default it is
   `%LOCALAPPDATA%\Programs\NodetaviMacro`.
3. The loaded libraries are `_internal\pynput` and `_internal\pystray`.
   Edit the relevant `.py` files there, or replace the package folder with an
   interface-compatible version. The upstream tar.gz source distributions in
   the ZIP store packages under `lib\pynput` and `lib\pystray`. For pystray,
   also copy the ZIP's `generated\pystray\_info.py` into the package folder.
4. Preserve the package layout, including `__init__.py`, and the Windows backend
   modules. Remove that package's `__pycache__` folders if present, so stale
   bytecode cannot be used. Do not replace or delete unrelated application files.
5. Start Nodetavi Macro normally. A compatible pure-Python modification requires no
   Python installation, app rebuild, publisher signature, or license key.
6. If a modification adds new dependencies, those must also be made available
   to the bundled interpreter; compatibility is your responsibility. The shipped
   interpreter version is recorded in the ZIP's manifest. Windows/x64 binary
   extensions must match that interpreter.
7. To restore the original libraries, restore your backup or reinstall the
   official installer. An update/reinstallation may overwrite library changes;
   keep your modified files outside the installation folder as a backup.

Modified libraries execute code with the application's permissions. Only use
changes you trust, especially when running the app as administrator. This is
not a mechanism for downloading or running arbitrary remote plugins.

Official support is for the unmodified release. You may report issues with a
modified version, but identify the changes first. This does not limit your
license rights. Contact: yanche2990@gmail.com.

## 한국어 요약

설치 파일 하나로 설치할 수 있으며 Python을 따로 설치할 필요가 없습니다.
LGPL 라이브러리만 설치 폴더의 `_internal\pynput`, `_internal\pystray`에서
수정·교체할 수 있습니다. 앱을 종료하고 원본을 백업한 뒤 호환되는 `.py`
파일로 교체하세요. 앱 자체 소스는 비공개이며, 라이브러리 원본 소스와
라이선스는 `_internal\docs\ThirdParty-Sources.zip`에 포함됩니다.
재설치·업데이트 시 수정 파일이 덮어써질 수 있으므로 별도로 백업하세요.
라이브러리의 수정·재배포 및 수정 디버깅을 위한 역공학 권리는 제한하지 않습니다.

This guide describes our packaging approach, not a legal opinion or guarantee.
