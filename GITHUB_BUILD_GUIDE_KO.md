# 고요한 미술관 v1.1 · 무료 APK 빌드 가이드

이 파일은 소스 패키지 루트에 위치합니다. APK는 이 ZIP 안에 포함되어 있지 않습니다.

1. https://github.com/new 에서 새 **Public** 저장소(예: `quiet-art-gallery`)를 생성합니다. 개인 API 키·서명키·사용 기록은 저장소에 절대 올리지 마세요. GitHub에서 공개 저장소 Actions 실행은 무료라고 안내합니다.
2. `Quiet_Art_Gallery_Android_v1_1_SOURCE.zip`을 PC에서 풀고, **ZIP 안의 `.github/`, `android-app/`, `web/`, `tests/` 및 README 파일**을 새 저장소 루트에 그대로 업로드합니다. `.github` 폴더는 필수입니다.
3. GitHub 저장소의 **Actions → Build Gallery APK → Run workflow**를 실행합니다.
4. 성공 상태(초록색 체크)인 실행을 열고 `Artifacts → QuietArtGallery-debug-APK` ZIP을 내려받습니다. `app-debug.apk`를 추출합니다.
5. 안드로이드 태블릿에서 APK를 열고 시스템의 설치 허용 요청에 동의합니다. 앱 실행 시 Wi-Fi를 연결해 공개 작품 로딩 상태를 확인합니다.
6. 업데이트용 APK를 다시 빌드하면 디버그 서명이 달라져 기존 앱 위에 설치되지 않을 수 있습니다. 기존 앱 설정에서 **감상 기록 백업**을 먼저 하고, 필요하면 이전 앱을 제거한 후 신규 APK를 설치하여 **감상 기록 복원**으로 기존 90일 기록을 복구합니다.

> **중요:** 2026-11-12 현재, 위 GitHub Actions 워크플로는 작성했지만 실제 계정에서 실행·빌드 성공을 확인하지 못했습니다. 로컬 빌드에도 Android SDK 및 인터넷 연결이 없어 APK를 생성하지 못했습니다. 결과 확인 전까지 `app-debug.apk`가 존재한다고 주장하지 않습니다. 기기 Android 8.0(API 26) 이상이 필요합니다.
