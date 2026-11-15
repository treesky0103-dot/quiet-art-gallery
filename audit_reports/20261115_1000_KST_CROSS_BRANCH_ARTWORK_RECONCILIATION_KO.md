# 《고요한 미술관》 2026-11-15 10:00 KST 수집 감사

## 기존 두 연구 분기의 최신 장부 대조

- 원본 연구 대장 `data/verified_80pct/verified_artwork_manifest.csv`: 서로 다른 작품 ID·파일 SHA256 **675개** (1800년 이후 522, 이전 153).
- 공개 커뮤니티/도서관 확장 `data/verified_80pct/additional_global_art_unknown_year.csv`: 파일 SHA256 **61개**, 제작 연도 확인 **0개**, 모두 `unknown`. 이 파일들의 실물 JPG는 GitHub Actions 임시 artifact에만 있다.
- 별도 연속 수집 연구 분기 `feat-continuous-global-openart-collector-20261114`의 `data/collector_10min/new_verified.csv`: **390행** (1800년 이후 **310**, 1800년 이전 **80**). 해당 분기의 `state.json` `new_verified=390`과 행 수 일치. 개별 제작연도 시작·끝 필드 390/390 기록됨. 대부분의 JPEG는 다운로드·디코딩 후 실행기에서 삭제됐으며 **4개만 해당 마지막 회차의 증빙 JPEG로 선택**됐지만, 실행 43655343543은 artifact 보관이 용량 상한에 걸려 업로드하지 않았음.
- 이번 대조에서는 세 대장 사이에 동일 SHA256 또는 `source+artwork_id` 중복이 **0건**. 기존 연구 검증·장부 기준 **1,126개** = 675+61+390. 이는 *장부상의 고유 검증 이미지 기록*이며 태블릿에 존재하는 1,126개 JPEG를 뜻하지 않음.
- 제작 연도별 분류: **1800년 이후 832개** (522+310), **1800년 이전 233개** (153+80), **제작 연도 불명 61개**. 분류 완료 1,065개 가운데 1800년 이후 비율 약 78.12%, 불명 포함 전체 1,126개 대비 약 73.89%. 1800년 이후 80% 목표 207,360개에 **206,528개 부족**.
- 90일 30초 간격 전체 259,200개에 **258,074개 부족**. 작품 ID·해시만으로 서로 다른 촬영본의 동일 작품까지 완전히 배제하지는 못함.

## 공급원 상태

- Wikimedia Commons: 이전 2회 실제 다운로드·디코딩·세로화면·SHA 검증 17+58건, 중복 page ID 14건을 제외해 61개. 429로 요청 제한 발생.
- Openverse: 401/429로 해당 연구 실행에서 신규 다운로드 0개. 무인증 무료 경로의 속도 제한을 우회하지 않음.
- 미국 의회도서관 Library of Congress: 429로 신규 파일 0개.
- Internet Archive: 검색 메타데이터 42건, 5건 이용 문구 후보, 이미지 실물 적격 0개. 나머지는 권리 미확인 후보로만 취급.
- Getty Open Content/Linked Art: 문서·공급원 후보로만 등록, 새 파일 0개. Getty의 모든 소장품이 공개 재배포 가능하다고 간주하지 않음.
- Cleveland Museum of Art: 연속 연구 수집기의 마지막 실행 43655343543에서 80개 다운로드·검증, 그 가운데 대부분 파일은 장기 보관되지 않음. 장부 누적은 390개.
- Art Institute of Chicago IIIF: 이전 연구의 HTTP 403 이력, 이번에 우회하지 않음.
- Smithsonian, Wellcome, Rijksmuseum, SMK, Met, NGA, Yale 등: 과거 실물 증빙과 대장 존재, 이번 감사에서 해당 바이너리를 모두 재다운로드·재검증하지 않음.

## 실물 저장/운영 상태

- GitHub Actions 43569337831의 첫 번째 공개 이미지 artifact 17개: 만료 **2026-11-16T07:06:12Z**.
- GitHub Actions 43570622654의 두 번째 공개 이미지 artifact 58개: 만료 **2026-11-16T07:22:28Z**.
- 위 두 artifact의 합계 75개 파일 가운데 동일 Commons page ID 14건이 있어 신규 고유 61개. 원본 JPG를 저장소/태블릿에 영구 보존한 증거는 없음.
- 연속 수집기 최신 실행 <https://github.com/treesky0103-dot/quiet-art-gallery/actions/runs/43655343543>: 장부에 80개 추가, 전체 연속 수집기 390개. 마지막 회차 로그에 `ARTIFACT_STORAGE_BUDGET allow=false total_bytes=946380872 maximum_bytes=314572800`가 기록되어 해당 회차 실물 업로드 **0개**. 기존 장부의 `artifact_run` 필드는 해당 실행에서 실물 파일이 현재 보존됨을 증명하지 않음.
- 기존 운영용 **v1.7.2 APK / main 브랜치 수정 없음**. 새 연구용 APK 빌드 기록이 있더라도 Android A7/A8에 설치·8GB 저장·90일 무중복 연속 재생을 검증한 결과는 없음.

## 판정

**미완료.** 추가 장부 390개를 확인했지만 해당 수량만큼의 **장기 보존 이미지 파일 확보는 미증명**. 특히 과거 누적 675개와 390개의 파일은 SHA/출처 대장과 당시 실물 검증 로그를 분리해야 한다. 공급원 수나 검색 후보 수를 실제 적격 파일 수에 더하지 않는다. 401/403/429, robots, 로그인/구독 및 이용 약관을 우회하지 않으며 무료·결제수단 불필요 경로만 연구한다.

증빙:
- <https://github.com/treesky0103-dot/quiet-art-gallery/actions/runs/43570968757>
- <https://github.com/treesky0103-dot/quiet-art-gallery/actions/runs/43570622654>
- <https://github.com/treesky0103-dot/quiet-art-gallery/actions/runs/43655343543>
- <https://github.com/treesky0103-dot/quiet-art-gallery/blob/feat-continuous-global-openart-collector-20261114/data/collector_10min/new_verified.csv>
