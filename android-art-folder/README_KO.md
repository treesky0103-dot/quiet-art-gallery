# 고요한 미술관 — Art 폴더 오프라인 랜덤 전시

- 태블릿 내부 저장소 또는 SD 카드에 Art 폴더를 만들고 이미지들을 넣습니다.
- APK 설치 후 최초 실행 시 'Art 폴더 선택'을 누르고 폴더를 고릅니다.
- JPG/JPEG/PNG/WEBP/BMP/GIF/HEIC/HEIF/AVIF 파일을 하위 폴더까지 찾습니다. GIF는 정적 첫 프레임입니다. 이미지 인식 가능 여부는 장치 코덱에 따릅니다.
- 원본 비율을 유지하는 FIT_CENTER 방식으로 전체화면에 표시하며, 30초마다 교체합니다.
- 매일 기기 현지 날짜가 달라지면 전시 순서를 새로 섞습니다. 당일 전체 목록 소진 전까지 중복이 없고, 소진하면 다시 전시합니다. 90일 제한은 없습니다.
- 앱을 닫고 다시 열면 같은 날짜의 다음 위치를 기억합니다.
- 최초 인덱싱과 수동 새로고침, 날짜 변경 시 이미지 목록을 다시 불러옵니다.
- 36.8GB 파일들은 태블릿에 그대로 있고 APK에 복제되지 않습니다. 인터넷 및 결제는 필요 없습니다.
- 선택적으로 Art/metadata.csv에 확정된 작품정보가 있을 때만 캡션을 표시합니다.

예시 metadata.csv (UTF-8):
relative_path,artist,title,year
Monet/water_lilies.jpg,Claude Monet,Water Lilies,1916

아무 CSV도 없으면 캡션은 나타나지 않습니다. 자동 이미지 인식으로 작가를 추정하지 않습니다.

개발 및 자동 빌드:
- Gradle 8.9, Android Gradle Plugin 8.7.3, SDK 35, Java 17
- cd android-art-folder && gradle :app:assembleDebug
- 산출물: android-art-folder/app/build/outputs/apk/debug/app-debug.apk
- APK는 디버그 서명으로 생성됩니다. Android 실기기 24시간 동작, 실제 36.8GB 로딩 성능, 특정 사진 코덱은 별도 검증 필요.
