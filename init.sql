-- ============================================================
-- Web SQS 관리 및 시뮬레이션 콘솔 (pg-sqs-simulator)
-- 데이터베이스 초기화 및 DDL / DML 스크립트
-- ============================================================

-- 1. 기존 테이블 초기화 (의존성 역순 삭제)
DROP TABLE IF EXISTS message_receipt CASCADE;
DROP TABLE IF EXISTS message CASCADE;
DROP TABLE IF EXISTS consumer CASCADE;
DROP TABLE IF EXISTS message_queue CASCADE;
DROP TABLE IF EXISTS queue_type CASCADE;

-- 2. DDL: 테이블 및 무결성 제약조건 생성

-- [테이블 1] queue_type (큐 유형 마스터)
CREATE TABLE queue_type (
    type_id SERIAL PRIMARY KEY,
    type_name VARCHAR(30) NOT NULL UNIQUE,
    max_message_size_kb INTEGER NOT NULL DEFAULT 256,
    retention_seconds INTEGER NOT NULL DEFAULT 345600,
    supports_dedup BOOLEAN NOT NULL DEFAULT FALSE,
    description VARCHAR(200)
);

-- [테이블 2] message_queue (메시지 큐 인스턴스)
-- FK 1: type_id -> queue_type(type_id)
CREATE TABLE message_queue (
    queue_id SERIAL PRIMARY KEY,
    queue_name VARCHAR(80) NOT NULL UNIQUE,
    type_id INTEGER NOT NULL REFERENCES queue_type(type_id) ON DELETE RESTRICT,
    visibility_timeout INTEGER NOT NULL DEFAULT 30,
    max_receive_count INTEGER NOT NULL DEFAULT 5,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- [테이블 3] consumer (컨슈머 워커 노드)
CREATE TABLE consumer (
    consumer_id SERIAL PRIMARY KEY,
    consumer_name VARCHAR(60) NOT NULL UNIQUE,
    ip_address VARCHAR(45) NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE')),
    registered_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- [테이블 4] message (큐에 적재된 메시지 본문)
-- FK 2: queue_id -> message_queue(queue_id)
CREATE TABLE message (
    message_id SERIAL PRIMARY KEY,
    queue_id INTEGER NOT NULL REFERENCES message_queue(queue_id) ON DELETE CASCADE,
    message_body TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- [테이블 5] message_receipt (메시지 수신 영수증 / 처리 이력)
-- FK 3: message_id -> message(message_id)
-- FK 4: consumer_id -> consumer(consumer_id)
CREATE TABLE message_receipt (
    receipt_id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES message(message_id) ON DELETE CASCADE,
    consumer_id INTEGER NOT NULL REFERENCES consumer(consumer_id) ON DELETE CASCADE,
    received_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX idx_queue_type_id ON message_queue(type_id);
CREATE INDEX idx_message_queue_id ON message(queue_id);
CREATE INDEX idx_receipt_message_id ON message_receipt(message_id);
CREATE INDEX idx_receipt_consumer_id ON message_receipt(consumer_id);


-- ============================================================
-- 3. DML: 초기 시드 데이터 삽입
-- ============================================================

-- (1) 큐 유형 초기 데이터
INSERT INTO queue_type (type_id, type_name, max_message_size_kb, retention_seconds, supports_dedup, description) VALUES
(1, 'Standard Queue', 256, 345600, FALSE, '최대 처리량 보장, 최선 노력 순서 전달, 최소 1회 전달'),
(2, 'FIFO Queue', 256, 345600, TRUE, '엄격한 선입선출(FIFO) 순서 보장, 정확히 1회 처리');

SELECT setval('queue_type_type_id_seq', (SELECT MAX(type_id) FROM queue_type));

-- (2) 샘플 큐 생성
INSERT INTO message_queue (queue_id, queue_name, type_id, visibility_timeout, max_receive_count, created_at) VALUES
(1, 'order-processing-queue', 1, 30, 5, NOW() - INTERVAL '3 hours'),
(2, 'notification-dispatch-queue', 1, 60, 3, NOW() - INTERVAL '2 hours'),
(3, 'payment-settlement.fifo', 2, 45, 5, NOW() - INTERVAL '1 hour');

SELECT setval('message_queue_queue_id_seq', (SELECT MAX(queue_id) FROM message_queue));

-- (3) 샘플 워커 등록
INSERT INTO consumer (consumer_id, consumer_name, ip_address, status, registered_at) VALUES
(1, 'Worker-Alpha-01', '10.0.1.101', 'ACTIVE', NOW() - INTERVAL '5 hours'),
(2, 'Worker-Beta-02', '10.0.1.102', 'ACTIVE', NOW() - INTERVAL '4 hours'),
(3, 'Worker-Gamma-03', '10.0.1.103', 'INACTIVE', NOW() - INTERVAL '2 hours');

SELECT setval('consumer_consumer_id_seq', (SELECT MAX(consumer_id) FROM consumer));

-- (4) 샘플 메시지 발행
INSERT INTO message (message_id, queue_id, message_body, created_at) VALUES
(1, 1, '{"order_id": "ORD-1001", "item": "MacBook Pro", "amount": 2500000}', NOW() - INTERVAL '40 minutes'),
(2, 1, '{"order_id": "ORD-1002", "item": "Magic Mouse", "amount": 119000}', NOW() - INTERVAL '30 minutes'),
(3, 1, '{"order_id": "ORD-1003", "item": "Studio Display", "amount": 2090000}', NOW() - INTERVAL '20 minutes'),
(4, 2, '{"user_id": 901, "template": "WELCOME_EMAIL", "email": "dev@example.com"}', NOW() - INTERVAL '15 minutes'),
(5, 3, '{"payment_id": "PAY-501", "status": "APPROVED", "timestamp": "2026-11-12T20:00:00Z"}', NOW() - INTERVAL '10 minutes');

SELECT setval('message_message_id_seq', (SELECT MAX(message_id) FROM message));

-- (5) 샘플 수신 영수증 생성 (일부 메시지는 이미 워커가 수신한 상태로 구성)
-- 메시지 1번은 Worker-Alpha가 수신 중 (In-Flight 상태)
INSERT INTO message_receipt (receipt_id, message_id, consumer_id, received_at) VALUES
(1, 1, 1, NOW() - INTERVAL '5 minutes');

SELECT setval('message_receipt_receipt_id_seq', (SELECT MAX(receipt_id) FROM message_receipt));
