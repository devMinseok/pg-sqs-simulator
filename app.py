import os
from flask import Flask, render_template, request, redirect, url_for, flash
import db

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-pg-sqs-simulator")


# ==============================================================================
# 0. 헬퍼 컨텍스트
# ==============================================================================
@app.context_processor
def inject_common():
    return {
        "db_healthy": db.check_db_health()
    }


# ==============================================================================
# 1. 큐 & 워커 관리 화면 (queues.html)
#    - Natural Join (큐 + 유형 조회)
#    - INSERT (큐 생성, 워커 등록)
#    - UPDATE (가시성 타임아웃 변경, 워커 상태 토글)
#    - DELETE (큐 삭제, 워커 삭제)
# ==============================================================================
@app.route("/", methods=["GET"])
@app.route("/queues", methods=["GET"])
def list_queues():
    # WHERE 조건 사용자 입력값 (<form method="get">)
    type_id_filter = request.args.get("type_id", type=int)

    # [SQL 유형 1: Natural Join]
    # message_queue와 queue_type의 type_id 공통 컬럼 기준 결합 및 조건 조회
    if type_id_filter:
        queues_sql = """
            SELECT queue_id, queue_name, type_id, type_name, max_message_size_kb,
                   retention_seconds, visibility_timeout, max_receive_count, created_at
            FROM message_queue NATURAL JOIN queue_type
            WHERE type_id = %s
            ORDER BY queue_id ASC;
        """
        queues = db.query_all(queues_sql, (type_id_filter,))
    else:
        queues_sql = """
            SELECT queue_id, queue_name, type_id, type_name, max_message_size_kb,
                   retention_seconds, visibility_timeout, max_receive_count, created_at
            FROM message_queue NATURAL JOIN queue_type
            ORDER BY queue_id ASC;
        """
        queues = db.query_all(queues_sql)

    # 큐 유형 목록 (생성 폼 및 필터 드롭다운용)
    types_sql = "SELECT type_id, type_name FROM queue_type ORDER BY type_id ASC;"
    queue_types = db.query_all(types_sql)

    # 워커 목록 조회
    consumers_sql = """
        SELECT consumer_id, consumer_name, ip_address, status, registered_at
        FROM consumer
        ORDER BY consumer_id ASC;
    """
    consumers = db.query_all(consumers_sql)

    return render_template(
        "queues.html",
        queues=queues,
        queue_types=queue_types,
        consumers=consumers,
        selected_type_id=type_id_filter
    )


@app.route("/queues/create", methods=["POST"])
def create_queue():
    """[SQL 유형 2: INSERT] 신규 큐 생성"""
    queue_name = request.form.get("queue_name", "").strip()
    type_id = request.form.get("type_id", type=int)
    visibility_timeout = request.form.get("visibility_timeout", default=30, type=int)
    max_receive_count = request.form.get("max_receive_count", default=5, type=int)

    if not queue_name or not type_id:
        flash("큐 이름과 유형은 필수 입력값입니다.", "danger")
        return redirect(url_for("list_queues"))

    try:
        insert_sql = """
            INSERT INTO message_queue (queue_name, type_id, visibility_timeout, max_receive_count)
            VALUES (%s, %s, %s, %s);
        """
        db.execute(insert_sql, (queue_name, type_id, visibility_timeout, max_receive_count))
        flash(f"큐 '{queue_name}'이(가) 성공적으로 생성되었습니다.", "success")
    except Exception as e:
        flash(f"큐 생성 실패: {e}", "danger")

    return redirect(url_for("list_queues"))


@app.route("/queues/<int:queue_id>/update", methods=["POST"])
def update_queue(queue_id):
    """[SQL 유형 3: UPDATE] 큐 가시성 타임아웃 및 재시도 설정 수정"""
    visibility_timeout = request.form.get("visibility_timeout", type=int)
    max_receive_count = request.form.get("max_receive_count", type=int)

    if visibility_timeout is None or max_receive_count is None:
        flash("가시성 타임아웃과 최대 수신 횟수를 올바르게 입력해주세요.", "danger")
        return redirect(url_for("list_queues"))

    try:
        update_sql = """
            UPDATE message_queue
            SET visibility_timeout = %s, max_receive_count = %s
            WHERE queue_id = %s;
        """
        db.execute(update_sql, (visibility_timeout, max_receive_count, queue_id))
        flash(f"큐(ID: {queue_id}) 설정이 업데이트되었습니다.", "success")
    except Exception as e:
        flash(f"큐 설정 수정 실패: {e}", "danger")

    return redirect(url_for("list_queues"))


@app.route("/queues/<int:queue_id>/delete", methods=["POST"])
def delete_queue(queue_id):
    """[SQL 유형 4: DELETE] 큐 삭제 (외래키 CASCADE 동작)"""
    try:
        delete_sql = "DELETE FROM message_queue WHERE queue_id = %s;"
        db.execute(delete_sql, (queue_id,))
        flash(f"큐(ID: {queue_id}) 및 소속 메시지가 삭제되었습니다.", "success")
    except Exception as e:
        flash(f"큐 삭제 실패: {e}", "danger")

    return redirect(url_for("list_queues"))


@app.route("/consumers/create", methods=["POST"])
def create_consumer():
    """신규 컨슈머 워커 등록 (INSERT)"""
    consumer_name = request.form.get("consumer_name", "").strip()
    ip_address = request.form.get("ip_address", "").strip()
    status = request.form.get("status", "ACTIVE")

    if not consumer_name or not ip_address:
        flash("워커 이름과 IP 주소는 필수입니다.", "danger")
        return redirect(url_for("list_queues"))

    try:
        insert_sql = """
            INSERT INTO consumer (consumer_name, ip_address, status)
            VALUES (%s, %s, %s);
        """
        db.execute(insert_sql, (consumer_name, ip_address, status))
        flash(f"워커 '{consumer_name}'이(가) 등록되었습니다.", "success")
    except Exception as e:
        flash(f"워커 등록 실패: {e}", "danger")

    return redirect(url_for("list_queues"))


@app.route("/consumers/<int:consumer_id>/toggle-status", methods=["POST"])
def toggle_consumer_status(consumer_id):
    """워커 상태 변경 (UPDATE)"""
    new_status = request.form.get("status", "ACTIVE")
    try:
        update_sql = "UPDATE consumer SET status = %s WHERE consumer_id = %s;"
        db.execute(update_sql, (new_status, consumer_id))
        flash(f"워커(ID: {consumer_id}) 상태가 '{new_status}'(으)로 변경되었습니다.", "info")
    except Exception as e:
        flash(f"워커 상태 변경 실패: {e}", "danger")

    return redirect(url_for("list_queues"))


@app.route("/consumers/<int:consumer_id>/delete", methods=["POST"])
def delete_consumer(consumer_id):
    """워커 삭제 (DELETE)"""
    try:
        delete_sql = "DELETE FROM consumer WHERE consumer_id = %s;"
        db.execute(delete_sql, (consumer_id,))
        flash(f"워커(ID: {consumer_id})가 삭제되었습니다.", "success")
    except Exception as e:
        flash(f"워커 삭제 실패: {e}", "danger")

    return redirect(url_for("list_queues"))


# ==============================================================================
# 2. 메시지 송수신 및 처리 화면 (messages.html)
#    - INSERT (SendMessage 메시지 발행, ReceiveMessage 수신 영수증 생성)
#    - Nested Subquery: NOT EXISTS (아직 수신되지 않은 가용 메시지 선별)
#    - DELETE (Ack 완료 메시지 삭제)
# ==============================================================================
@app.route("/messages", methods=["GET"])
def view_messages():
    # 선택된 큐 필터
    selected_queue_id = request.args.get("queue_id", type=int)

    # 큐 목록 및 활성 워커 목록
    queues = db.query_all("SELECT queue_id, queue_name FROM message_queue ORDER BY queue_id ASC;")
    active_consumers = db.query_all("SELECT consumer_id, consumer_name FROM consumer WHERE status = 'ACTIVE' ORDER BY consumer_id ASC;")

    # 메시지 목록 조회 (수신 영수증 존재 여부로 In-Flight 여부 판별)
    messages_query = """
        SELECT m.message_id, m.queue_id, q.queue_name, m.message_body, m.created_at,
               r.receipt_id, r.consumer_id, c.consumer_name, r.received_at,
               CASE WHEN r.receipt_id IS NOT NULL THEN 'IN_FLIGHT' ELSE 'AVAILABLE' END AS status
        FROM message m
        JOIN message_queue q ON m.queue_id = q.queue_id
        LEFT JOIN message_receipt r ON m.message_id = r.message_id
        LEFT JOIN consumer c ON r.consumer_id = c.consumer_id
    """

    if selected_queue_id:
        messages_query += " WHERE m.queue_id = %s ORDER BY m.created_at DESC;"
        messages = db.query_all(messages_query, (selected_queue_id,))
    else:
        messages_query += " ORDER BY m.created_at DESC;"
        messages = db.query_all(messages_query)

    return render_template(
        "messages.html",
        messages=messages,
        queues=queues,
        active_consumers=active_consumers,
        selected_queue_id=selected_queue_id
    )


@app.route("/messages/send", methods=["POST"])
def send_message():
    """메시지 발행 (SendMessage - INSERT)"""
    queue_id = request.form.get("queue_id", type=int)
    message_body = request.form.get("message_body", "").strip()

    if not queue_id or not message_body:
        flash("대상 큐와 메시지 본문을 모두 입력해야 합니다.", "danger")
        return redirect(url_for("view_messages", queue_id=queue_id))

    try:
        insert_sql = "INSERT INTO message (queue_id, message_body) VALUES (%s, %s);"
        db.execute(insert_sql, (queue_id, message_body))
        flash("메시지가 큐에 정상적으로 발행되었습니다.", "success")
    except Exception as e:
        flash(f"메시지 발행 실패: {e}", "danger")

    return redirect(url_for("view_messages", queue_id=queue_id))


@app.route("/messages/receive", methods=["POST"])
def receive_message():
    """
    [SQL 유형 5: Nested subquery (NOT EXISTS)]
    선택한 큐에서 아직 message_receipt가 없는(수신되지 않은) 순수 가용 메시지 1건을 선별하여
    해당 워커 앞으로 영수증(receipt)을 발급(INSERT)합니다.
    """
    queue_id = request.form.get("queue_id", type=int)
    consumer_id = request.form.get("consumer_id", type=int)

    if not queue_id or not consumer_id:
        flash("메시지를 수신할 큐와 워커를 모두 선택해주세요.", "danger")
        return redirect(url_for("view_messages"))

    try:
        # 중첩 하위질의(NOT EXISTS)로 아직 영수증이 없는 가장 오래된 가용 메시지 1건 탐색
        subquery_sql = """
            SELECT m.message_id, m.message_body
            FROM message m
            WHERE m.queue_id = %s
              AND NOT EXISTS (
                  SELECT 1 FROM message_receipt r
                  WHERE r.message_id = m.message_id
              )
            ORDER BY m.created_at ASC
            LIMIT 1;
        """
        available_msg = db.query_one(subquery_sql, (queue_id,))

        if not available_msg:
            flash("선택한 큐에 현재 대기 중인 가용 메시지가 없습니다.", "warning")
            return redirect(url_for("view_messages", queue_id=queue_id))

        # 메시지 수신 영수증 생성 (In-Flight 상태로 전환)
        receipt_sql = """
            INSERT INTO message_receipt (message_id, consumer_id)
            VALUES (%s, %s);
        """
        db.execute(receipt_sql, (available_msg["message_id"], consumer_id))
        flash(f"워커가 메시지(ID: {available_msg['message_id']})를 성공적으로 수신했습니다.", "success")

    except Exception as e:
        flash(f"메시지 수신 실패: {e}", "danger")

    return redirect(url_for("view_messages", queue_id=queue_id))


@app.route("/messages/<int:message_id>/ack", methods=["POST"])
def ack_message(message_id):
    """
    메시지 처리 완료 후 큐에서 영구 삭제 (DeleteMessage / Ack)
    - [SQL 유형: DELETE]
    """
    queue_id = request.form.get("queue_id", type=int)
    try:
        delete_sql = "DELETE FROM message WHERE message_id = %s;"
        db.execute(delete_sql, (message_id,))
        flash(f"메시지(ID: {message_id})가 성공적으로 처리(Ack) 및 삭제되었습니다.", "success")
    except Exception as e:
        flash(f"메시지 삭제 실패: {e}", "danger")

    return redirect(url_for("view_messages", queue_id=queue_id))


# ==============================================================================
# 3. 지표 및 모니터링 화면 (metrics.html)
#    - Aggregate function (COUNT + GROUP BY + HAVING): 큐별 적재 지표 통계
#    - Cartesian product (CROSS JOIN): 전체 큐 × 전체 워커 활동 매트릭스
# ==============================================================================
@app.route("/metrics", methods=["GET"])
def view_metrics():
    # WHERE 조건 사용자 입력값 (<form method="get">)
    min_messages = request.args.get("min_messages", default=0, type=int)
    worker_status_filter = request.args.get("worker_status", default="", type=str).strip()

    # [SQL 유형 6: Aggregate function (COUNT, GROUP BY, HAVING)]
    # 큐별 총 메시지 수, 처리 중(In-Flight) 수, 대기 중(Available) 수 집계
    agg_sql = """
        SELECT q.queue_id, q.queue_name, t.type_name,
               COUNT(m.message_id) AS total_messages,
               COUNT(r.receipt_id) AS in_flight_messages,
               (COUNT(m.message_id) - COUNT(r.receipt_id)) AS available_messages
        FROM message_queue q
        JOIN queue_type t ON q.type_id = t.type_id
        LEFT JOIN message m ON q.queue_id = m.queue_id
        LEFT JOIN message_receipt r ON m.message_id = r.message_id
        GROUP BY q.queue_id, q.queue_name, t.type_name
        HAVING COUNT(m.message_id) >= %s
        ORDER BY q.queue_id ASC;
    """
    queue_metrics = db.query_all(agg_sql, (min_messages,))

    # [SQL 유형 7: Cartesian product (CROSS JOIN)]
    # 모든 큐 x 모든 워커 조합 매트릭스 생성 및 워커별 처리 이력 카운트
    if worker_status_filter in ("ACTIVE", "INACTIVE"):
        cross_sql = """
            SELECT q.queue_id, q.queue_name, c.consumer_id, c.consumer_name, c.status,
                   (
                       SELECT COUNT(*)
                       FROM message_receipt r
                       JOIN message m ON r.message_id = m.message_id
                       WHERE m.queue_id = q.queue_id AND r.consumer_id = c.consumer_id
                   ) AS processed_count
            FROM message_queue q
            CROSS JOIN consumer c
            WHERE c.status = %s
            ORDER BY q.queue_id ASC, c.consumer_id ASC;
        """
        matrix_rows = db.query_all(cross_sql, (worker_status_filter,))
    else:
        cross_sql = """
            SELECT q.queue_id, q.queue_name, c.consumer_id, c.consumer_name, c.status,
                   (
                       SELECT COUNT(*)
                       FROM message_receipt r
                       JOIN message m ON r.message_id = m.message_id
                       WHERE m.queue_id = q.queue_id AND r.consumer_id = c.consumer_id
                   ) AS processed_count
            FROM message_queue q
            CROSS JOIN consumer c
            ORDER BY q.queue_id ASC, c.consumer_id ASC;
        """
        matrix_rows = db.query_all(cross_sql)

    return render_template(
        "metrics.html",
        queue_metrics=queue_metrics,
        matrix_rows=matrix_rows,
        min_messages=min_messages,
        worker_status_filter=worker_status_filter
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
