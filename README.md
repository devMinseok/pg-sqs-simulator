# pg-sqs-simulator: Web SQS 관리 및 시뮬레이션 콘솔

> **PostgreSQL 기반 AWS Simple Queue Service(SQS) 아키텍처 모델링 및 Flask 웹 콘솔**  
> 숭실대학교 데이터베이스 텀프로젝트 (중간대체) 과제 요건 100% 충족

---

## 1. 프로젝트 개요

**`pg-sqs-simulator`**는 클라우드 분산 시스템의 핵심 비동기 메시징 서비스인 **AWS SQS(Simple Queue Service)**의 아키텍처를 관계형 데이터베이스(PostgreSQL)의 트랜잭션과 무결성 제약조건 모델로 재해석하고, 이를 웹 기반 어드민 콘솔(Flask)로 제어 및 모니터링하는 프로젝트입니다.

### 핵심 기능
- **큐 & 워커 관리 (`queues.html`)**: Standard / FIFO 큐 생성, 가시성 타임아웃 수정, 큐 삭제, 컨슈머 워커 등록 및 상태 관리.
- **메시지 송수신 및 처리 (`messages.html`)**: 프로듀서의 메시지 발행(Send), 컨슈머 워커의 가용 메시지 수신(Receive), 메시지 처리 완료 후 영구 삭제(Delete/Ack).
- **CloudWatch 지표 및 매트릭스 (`metrics.html`)**: 큐별 대기/수신 중 메시지 수 실시간 집계(COUNT), 워커 × 큐 활동 매트릭스(CROSS JOIN).

---

## 2. 기술 스택 및 아키텍처

- **Database**: PostgreSQL 16 (Docker Compose)
- **Backend**: Python 3.10+, Flask 3.0+, Psycopg (v3)
- **Frontend**: HTML5, CSS3 (AWS Management Console 룩앤필 디자인)
- **Container**: Docker, Docker Compose

```
[ Client Browser (HTML <form>) ]
           │   ▲
           │   │  HTTP Request / Response
           ▼   │
[ Flask Backend (app.py, db.py) ]
           │   ▲
           │   │  psycopg (%s Parameterized Query)
           ▼   │
[ PostgreSQL 16 (Docker: sqs_db) ]
  ├── queue_type (큐 정책 마스터)
  ├── message_queue (생성된 큐)
  ├── consumer (워커 노드)
  ├── message (적재된 메시지)
  └── message_receipt (수신 영수증)
```

---

## 3. 데이터베이스 스키마 및 제약조건

총 **5개 테이블**과 **4개 외래키(FK)**로 구성되어 참조 무결성을 완벽하게 보장합니다.

```
queue_type (1) ───────< (N) message_queue (1) ───────< (N) message (1)
                                                            │
                                                            │ (1)
                                                            V
consumer (1) ─────────< (N) message_receipt ───────────────< (N)
```

1. **`queue_type` (PK: `type_id`)**: Standard / FIFO 큐 유형별 최대 크기, 보관 기간 정책 정의.
2. **`message_queue` (PK: `queue_id`, FK: `type_id`)**: 개별 큐 인스턴스 정보 및 가시성 타임아웃 관리.
3. **`consumer` (PK: `consumer_id`)**: 메시지를 수신/소비하는 워커 프로세스 정보 및 상태(ACTIVE/INACTIVE).
4. **`message` (PK: `message_id`, FK: `queue_id`)**: 큐에 적재된 메시지 페이로드 내용.
5. **`message_receipt` (PK: `receipt_id`, FK: `message_id`, FK: `consumer_id`)**: 수신 영수증(ReceiptHandle)을 통한 중복 수신 방지 및 상태 추적.

---

## 4. 필수 SQL 7대 유형 구현 매핑표

본 프로젝트는 강의 요건인 **필수 SQL 7종을 100% 충족**하며, 모든 조건값은 **HTML `<form>`을 통해 전달**되어 `%s` 매개변수로 안전하게 바인딩됩니다.

| # | SQL 유형 | 적용 기능 | 소스 위치 | 핵심 SQL 문장 |
| :-: | :--- | :--- | :--- | :--- |
| **1** | **`Natural join`** | 큐 목록 및 정책 결합 조회 (유형별 필터) | `app.py:list_queues()` | `SELECT * FROM message_queue NATURAL JOIN queue_type WHERE type_id = %s;` |
| **2** | **`INSERT`** | 큐 생성, 메시지 발행, 워커 등록 | `app.py:send_message()` 등 | `INSERT INTO message (queue_id, message_body) VALUES (%s, %s);` |
| **3** | **`UPDATE`** | 가시성 타임아웃 수정, 워커 상태 토글 | `app.py:update_queue()` | `UPDATE message_queue SET visibility_timeout = %s WHERE queue_id = %s;` |
| **4** | **`DELETE`** | 메시지 처리 완료 삭제 (Ack), 큐/워커 삭제 | `app.py:ack_message()` | `DELETE FROM message WHERE message_id = %s;` |
| **5** | **`Nested subquery`<br>(NOT EXISTS)** | 가용 메시지 선별 수신 (미수신 메시지 탐색) | `app.py:receive_message()` | `SELECT * FROM message m WHERE m.queue_id = %s AND NOT EXISTS (SELECT 1 FROM message_receipt r WHERE r.message_id = m.message_id) LIMIT 1;` |
| **6** | **`Cartesian product`<br>(CROSS JOIN)** | 큐 × 워커 활동 매트릭스 전체 조합 | `app.py:view_metrics()` | `SELECT q.queue_name, c.consumer_name FROM message_queue q CROSS JOIN consumer c WHERE c.status = %s;` |
| **7** | **`Aggregate function`<br>(COUNT + GROUP BY)** | CloudWatch 큐별 적재 메시지 지표 집계 | `app.py:view_metrics()` | `SELECT q.queue_name, COUNT(m.message_id) FROM message_queue q LEFT JOIN message m ON q.queue_id = m.queue_id GROUP BY q.queue_id HAVING COUNT(m.message_id) >= %s;` |

---

## 5. 실행 방법 (Getting Started)

### 사전 준비
- Docker 및 Docker Compose (또는 로컬 PostgreSQL)
- Python 3.10 이상

### Step 1. 저장소 클론 및 이동
```bash
git clone https://github.com/devminseok/pg-sqs-simulator.git
cd pg-sqs-simulator
```

### Step 2. Docker로 PostgreSQL 실행 (원터치 초기화)
`docker-compose.yml`에는 `init.sql`이 자동 마운트되어 있어, 컨테이너 실행 즉시 테이블 5개와 기초 시드 데이터가 자동으로 구축됩니다.
```bash
docker compose up -d
```
> DB가 정상 구동되었는지 확인:
> ```bash
> docker compose ps
> ```

### Step 3. Python 가상환경 및 패키지 설치
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 4. 환경변수 확인 (`.env`)
기본 `.env.example` 파일을 기반으로 환경변수가 세팅되어 있습니다. Docker 포트(5432)와 기본 계정(`postgres`/`postgres`)을 그대로 사용합니다.
```bash
cp .env.example .env
```

### Step 5. Flask 웹 애플리케이션 실행
```bash
python3 app.py
```

웹 브라우저에서 **`http://localhost:5001`** 접속!

---

## 6. 화면별 기능 안내

1. **Queues & Workers (`/queues`)**
   - 큐 목록 조회: 큐 유형 필터 드롭다운(GET 폼)으로 `Natural Join` 결과 필터링.
   - 신규 큐 생성(POST `INSERT`), 가시성 타임아웃 인라인 수정(POST `UPDATE`), 큐 삭제(POST `DELETE`).
   - 컨슈머 워커 등록 및 ACTIVE/INACTIVE 상태 토글.
2. **Send and receive messages (`/messages`)**
   - Producer 영역: 대상 큐 선택 후 JSON/텍스트 페이로드 메시지 발행 (`INSERT`).
   - Consumer 영역: 큐와 활성 워커를 선택하고 `Receive` 클릭 시, `NOT EXISTS` 중첩 서브쿼리로 아직 수신되지 않은 가용 메시지 1건을 조회하여 영수증(`message_receipt`) 발행.
   - 메시지 목록에서 `Ack / Delete` 버튼 클릭 시 `DELETE` 실행으로 큐에서 영구 삭제.
3. **CloudWatch Metrics (`/metrics`)**
   - 큐별 적재량 카드 및 테이블: `COUNT` 및 `GROUP BY`로 전체, In-Flight(수신 중), Available(대기 중) 수치 집계. 최소 메시지 수 필터(`HAVING`).
   - 워커 × 큐 구독 매트릭스: `CROSS JOIN`을 통해 모든 큐와 워커의 조합 표를 출력하고, 실제 처리 건수를 매핑하여 미활동 조합 식별.

---

## 7. 프로젝트 파일 구성

```text
pg-sqs-simulator/
├── docker-compose.yml        # PostgreSQL 16 컨테이너 정의 (init.sql 자동 적재)
├── .env.example              # 데이터베이스 및 Flask 환경변수 템플릿
├── requirements.txt          # 의존성 패키지 (Flask, psycopg, python-dotenv)
├── init.sql                  # DDL(테이블 5개, FK 4개) 및 초기 시드 데이터 삽입 스크립트
├── app.py                    # Flask 메인 애플리케이션 (라우팅 및 컨트롤러)
├── db.py                     # psycopg 기반 DB 커넥션 및 파라미터화 쿼리 모듈
├── templates/                # HTML 템플릿 파일
│   ├── base.html             # AWS 콘솔 스타일 레이아웃 베이스
│   ├── queues.html           # 화면 1: 큐 & 워커 관리 화면
│   ├── messages.html         # 화면 2: 메시지 송수신 및 처리 화면
│   └── metrics.html          # 화면 3: CloudWatch 지표 및 CROSS JOIN 매트릭스
├── static/
│   └── css/
│       └── style.css         # AWS Management Console 룩앤필 스타일시트
└── README.md                 # 프로젝트 문서 및 매뉴얼
```
