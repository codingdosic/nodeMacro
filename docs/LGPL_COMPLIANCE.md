# LGPL 구성요소 배포 안내

D5 Macro 1.0.0 배포물에는 다음 LGPL 구성요소가 포함됩니다.

| 구성요소 | 버전 | 라이선스 | 대응 소스 |
|---|---:|---|---|
| pynput | 1.8.1 | LGPL-3.0 | [PyPI 1.8.1 source distribution](https://pypi.org/project/pynput/1.8.1/#files) |
| pystray | 0.19.5 | LGPL-3.0 | [PyPI 0.19.5 source distribution](https://pypi.org/project/pystray/0.19.5/#files) |

공식 바이너리는 해당 버전의 라이브러리를 수정하지 않고 사용합니다. 배포
바이너리와 동일한 D5 Macro Application Code는 같은 버전의 Git 태그에서
제공합니다. `requirements.txt`, `requirements-build.txt`, `build.ps1`과
`D5Macro.spec`은 의존성 설치와 재빌드에 필요한 정보를 포함합니다.

공식 배포물을 적법하게 받은 사용자는 LGPL 구성요소를 수정한 뒤 자신의
용도로 D5 Macro와 다시 결합하고, 그 수정 사항을 디버깅하는 데 필요한 범위에서
Application Code를 복제·수정할 수 있습니다. 해당 목적의 역공학도 제한하지
않습니다. 자세한 조건은 배포물의 `THIRD_PARTY_LICENSES.txt`와 각 프로젝트의
라이선스 원문을 따릅니다.

릴리스할 때는 다음을 함께 제공해야 합니다.

1. 바이너리와 정확히 일치하는 D5 Macro Git 태그
2. `pynput 1.8.1`, `pystray 0.19.5`의 정확한 소스 링크 또는 소스 아카이브
3. `THIRD_PARTY_NOTICES.md`와 `THIRD_PARTY_LICENSES.txt`
4. 수정된 LGPL 구성요소가 있다면 그 수정 소스와 빌드 방법

이 문서는 법률 자문을 대신하지 않습니다.
