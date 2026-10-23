# 0001. DB를 MySQL HeatWave Always Free로 옮긴다

- 상태: 채택 (2026-10-23, #63)
- 같은 결정: AI-Trend-News(#58), sandcorp-auth

## 맥락

DB는 운영 compose 안의 Postgres 17 컨테이너였다. 같은 oracle 호스트(ARM64, 공유)에서 세 서비스가 각자 Postgres를 띄우고 있었고, 백업·업그레이드·메모리를 각자 떠안았다. OCI Always Free에는 관리형 MySQL HeatWave 인스턴스가 하나 들어 있다(무료, 같은 VCN의 사설 IP). 2026-10-23 세 저장소를 Oracle ADB와 MySQL HeatWave에 각각 붙여 시험한 결과 MySQL은 설정만 바꿔 이 저장소의 시험 340건이 모두 통과했고, Oracle은 `select_for_update().first()` 등에서 코드 변경이 필요했다. Django가 1순위로 지원하는 백엔드이기도 하다.

## 결정

- 운영·개발·시험 모두 **MySQL 하나**를 쓴다(Postgres 지원과 환경 변수 분기는 두지 않는다). 운영은 HeatWave의 `utf8mb4` / `utf8mb4_0900_as_cs` 데이터베이스, 로컬은 `mysql:26.10.0` 컨테이너(같은 콜레이션). 드라이버는 `mysqlclient`.
- 콜레이션은 대소문자·악센트를 구분하는 `utf8mb4_0900_as_cs`로 정해 slug·고객 코드·username이 Postgres와 같은 뜻을 갖게 한다.
- 트랜잭션 격리는 Django 기본(READ COMMITTED)을 그대로 둔다. 문서번호 직렬화(`services/publishing.py`)가 잠금 뒤 최신 커밋을 읽는 데 기대고, REPEATABLE READ에서는 갭 락 교착이 났다.
- MySQL에 없는 부분 유일 제약(`event_first_view_once`)은 같은 뜻의 식 기반 유일 인덱스로 바꾼다.
- 백업은 `mysqldump`(gzip)로 바꾸고 버킷·보관 규칙은 그대로 둔다.

## 결과

- 운영 compose에서 DB 컨테이너가 빠져 호스트 메모리 512 MB를 돌려받는다. 대신 DB가 compose 밖에 있어 `deploy.sh`는 접속을 기다리기만 한다.
- JSON 열의 객체 키 순서를 MySQL이 정규화한다. JSON을 그대로 직렬화해 해시·ETag·diff를 만들 때는 키를 정렬해야 한다.
- 인덱스 없는 `ORDER BY … FOR UPDATE SKIP LOCKED`가 InnoDB에서는 조건에 맞는 행을 모두 잠근다. 작업 큐 질의는 인덱스를 타게 짠다(`PdfJob` `pdfjob_due`).
- mysqlclient는 리눅스 휠이 없어 이미지 빌드 단계에서 컴파일한다(로컬 개발에도 `libmysqlclient-dev`·`pkg-config`가 필요하다).
