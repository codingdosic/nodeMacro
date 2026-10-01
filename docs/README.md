# Docs

| 문서 | 설명 |
|------|------|
| [editor-ux-roadmap.md](./editor-ux-roadmap.md) | 에디터 UX / 노드 개선 구현 순서, 세부사항, 세션 인수인계 |
| [PRIVACY.md](./PRIVACY.md) | 로컬 데이터, 녹화 및 개인정보 처리 안내 |
| [LGPL_COMPLIANCE.md](./LGPL_COMPLIANCE.md) | LGPL 구성요소의 버전, 대응 소스 및 재결합 안내 |
| [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) | 배포물에 포함되는 제3자 구성요소 고지 |
| [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md) | 유료 배포 전 검증·법무·서명 체크리스트 |

새 세션을 시작할 때는 `editor-ux-roadmap.md`의 **「다음 세션 시작 프롬프트」**를 복사해 사용하세요.

### 트랙 안내

| 트랙 | 단계 | 비고 |
|------|------|------|
| UX / 노드 | 1–12 | 12 반복문은 사용자 검증(에이전트 보류) |
| 저장·로드·히스토리 | 13–15 | A: `scripts/<name>/`+`imgs/` → B: 로드·덮어쓰기 확인 → C: undo(구조만)/redo |
