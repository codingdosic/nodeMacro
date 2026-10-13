# Third-party notices

Nodetavi Macro는 다음 오픈소스 프로젝트를 사용합니다. 실제 빌드에 포함된 라이선스 원문은 설치 패키지의 `THIRD_PARTY_LICENSES.txt`에 함께 배포됩니다.

- FastAPI — MIT
- Uvicorn — BSD-3-Clause
- websockets — BSD-3-Clause
- PyAutoGUI — BSD 계열
- pynput 1.8.1 — LGPL-3.0-or-later
- OpenCV — Apache-2.0
- NumPy — BSD-3-Clause
- Pillow — HPND
- pystray 0.19.5 — LGPL-3.0-or-later
- React / React DOM — MIT
- React Flow (`@xyflow/react`) — MIT
- Axios — MIT
- Vite — MIT

LGPL 구성요소의 정확한 버전, 대응 소스와 교체 방법은 [LGPL_COMPLIANCE.md](./LGPL_COMPLIANCE.md)에서 확인할 수 있습니다. 원본 소스는 설치 파일에 포함된 `ThirdParty-Sources.zip`으로 제공합니다. LGPL 라이브러리는 실행 파일 내부 아카이브가 아닌 별도의 `.py` 파일로 로드됩니다. 앱 자체 소스는 비공개입니다. 라이브러리의 수정·재배포 및 수정 사항의 디버깅을 위한 역공학 권리는 해당 라이선스에 따라 보장됩니다.

English: Nodetavi Macro includes pynput 1.8.1 and pystray 0.19.5 under LGPLv3 or later.
Their exact upstream sources accompany the installer in `ThirdParty-Sources.zip`.
They are loaded from replaceable `.py` files. See `LGPL_COMPLIANCE.md` for
replacement instructions and `THIRD_PARTY_LICENSES.txt` for complete license
texts. Third-party license rights take precedence over the application's EULA.

이 문서는 고지 목록이며 각 프로젝트의 라이선스 원문을 대체하지 않습니다.
