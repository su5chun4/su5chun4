# Photo Organizer AI — Windows / macOS 설치형 빌드 준비판

이 ZIP은 **완성된 EXE/APP가 아닌 소스코드와 자동 빌드 설정**입니다. Windows 및 macOS에서 별도로 빌드된 결과물은 실행하는 컴퓨터에 Python 설치가 필요 없습니다.

## Python 없이 실행 파일 받는 방법 (GitHub Actions)
1. GitHub에서 새 비공개 저장소(repository)를 만듭니다.
2. 이 폴더 안의 파일과 `.github/workflows/build.yml`을 저장소 최상위에 업로드합니다. (숨김 폴더 포함)
3. 저장소의 **Actions > Build Windows and macOS apps > Run workflow**를 실행합니다.
4. 빌드가 완료되면 해당 실행 페이지 하단 **Artifacts**에서 `PhotoOrganizerAI-Windows`, `PhotoOrganizerAI-macOS`를 다운로드합니다.
5. Windows는 다운로드한 ZIP을 풀고 `PhotoOrganizerAI.exe`를 실행합니다. Mac은 ZIP을 풀고 `PhotoOrganizerAI.app`을 실행합니다.

GitHub 계정 및 Actions 사용이 필요하며, 빌드 완료는 실제로 확인되지 않았습니다. 서명되지 않은 앱이므로 Windows SmartScreen 또는 macOS Gatekeeper 경고가 발생할 수 있습니다. Mac에서 배포용으로 사용하려면 별도의 코드 서명/공증이 권장됩니다.

## 개발자용 로컬 빌드
Windows에서 `build_windows.bat`, Mac에서 `bash build_mac.sh` 실행. **빌드 컴퓨터에만** Python 3.10+ 설치가 필요합니다.

## 현재 구현된 기능
- 사진 폴더 재귀 검색 및 날짜별 정리
- SHA-256 완전 중복 검색, perceptual hash 유사 사진 감지
- 수동 분류, 파일명 변경 및 복사 정리 (원본 유지)

## 아직 구현되지 않은 기능
- 실제 AI 내용 인식, 자연어 검색, 썸네일 미리보기, HEIC 및 동영상 지원
- 배포용 코드 서명/공증, 설치 마법사

대량의 사진을 처리하기 전 소규모 테스트를 권장합니다.
