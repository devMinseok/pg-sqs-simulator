import os
import sys
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "sqs_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# psycopg (v3) 우선 시도, 실패 시 psycopg2 호환
try:
    import psycopg
    from psycopg.rows import dict_row

    def get_connection():
        return psycopg.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            row_factory=dict_row
        )

except ImportError:
    try:
        import psycopg2
        import psycopg2.extras

        def get_connection():
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            return conn

    except ImportError:
        def get_connection():
            raise RuntimeError(
                "psycopg 또는 psycopg2 패키지가 설치되지 않았습니다. 'pip install -r requirements.txt'를 실행하세요."
            )


def query_all(sql: str, params: tuple = None) -> list:
    """여러 행을 조회하여 딕셔너리 리스트로 반환"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            # psycopg v3 dict_row 처리
            if hasattr(cur, "fetchall"):
                rows = cur.fetchall()
                # psycopg2 대응
                if rows and not isinstance(rows[0], dict):
                    colnames = [desc[0] for desc in cur.description]
                    return [dict(zip(colnames, row)) for row in rows]
                return rows
            return []


def query_one(sql: str, params: tuple = None) -> dict:
    """단일 행을 조회하여 딕셔너리로 반환"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            if row is not None and not isinstance(row, dict):
                colnames = [desc[0] for desc in cur.description]
                return dict(zip(colnames, row))
            return row


def execute(sql: str, params: tuple = None) -> int:
    """INSERT, UPDATE, DELETE 문 실행 후 영향받은 행 수 반환"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            conn.commit()
            return cur.rowcount


def execute_returning(sql: str, params: tuple = None) -> dict:
    """RETURNING 절이 포함된 DML 실행 후 반환 행 리턴"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            conn.commit()
            if row is not None and not isinstance(row, dict):
                colnames = [desc[0] for desc in cur.description]
                return dict(zip(colnames, row))
            return row


def check_db_health() -> bool:
    """DB 연결 테스트"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return True
    except Exception:
        return False
