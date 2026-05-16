import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_PATH = os.getenv("DATABASE_PATH", "nfe_licensing.db")

USING_POSTGRES = bool(DATABASE_URL)


def get_db():
    if USING_POSTGRES:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    else:
        import sqlite3
        conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn


def _execute(conn, query, params=None):
    cur = conn.cursor()
    if USING_POSTGRES:
        query = query.replace("?", "%s")
    cur.execute(query, params or ())
    conn.commit()
    return cur


def _fetchone(conn, query, params=None):
    cur = _execute(conn, query, params)
    return cur.fetchone()


def _fetchall(conn, query, params=None):
    cur = _execute(conn, query, params)
    return cur.fetchall()


def init_db():
    with get_db() as conn:
        customers_sql = """
            CREATE TABLE IF NOT EXISTS customers (
                cnpj TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """
        _execute(conn, customers_sql)

        payments_sql = """
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                customer_cnpj TEXT NOT NULL,
                hwid TEXT NOT NULL,
                plano TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                asaas_customer_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(customer_cnpj) REFERENCES customers(cnpj)
            );
        """
        _execute(conn, payments_sql)

        id_type = "SERIAL" if USING_POSTGRES else "INTEGER"
        licenses_sql = f"""
            CREATE TABLE IF NOT EXISTS licenses (
                id {id_type} PRIMARY KEY,
                payment_id TEXT NOT NULL,
                license_key TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(payment_id) REFERENCES payments(payment_id)
            );
        """
        _execute(conn, licenses_sql)

        logger.info("Banco de dados inicializado (%s)", "PostgreSQL" if USING_POSTGRES else "SQLite")


def get_customer(cnpj):
    with get_db() as conn:
        row = _fetchone(conn, "SELECT customer_id FROM customers WHERE cnpj = ?", (cnpj,))
        return row["customer_id"] if row else None


def save_customer(cnpj, customer_id):
    import datetime
    with get_db() as conn:
        if USING_POSTGRES:
            _execute(conn,
                "INSERT INTO customers (cnpj, customer_id, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT (cnpj) DO UPDATE SET customer_id = EXCLUDED.customer_id, created_at = EXCLUDED.created_at",
                (cnpj, customer_id, datetime.datetime.utcnow().isoformat())
            )
        else:
            _execute(conn,
                "INSERT OR REPLACE INTO customers (cnpj, customer_id, created_at) VALUES (?, ?, ?)",
                (cnpj, customer_id, datetime.datetime.utcnow().isoformat())
            )


def save_payment(payment_id, cnpj, hwid, plano, customer_id):
    import datetime
    with get_db() as conn:
        if USING_POSTGRES:
            _execute(conn,
                "INSERT INTO payments (payment_id, customer_cnpj, hwid, plano, status, asaas_customer_id, created_at) "
                "VALUES (?, ?, ?, ?, 'PENDING', ?, ?) "
                "ON CONFLICT (payment_id) DO UPDATE SET "
                "customer_cnpj = EXCLUDED.customer_cnpj, hwid = EXCLUDED.hwid, "
                "plano = EXCLUDED.plano, status = EXCLUDED.status, "
                "asaas_customer_id = EXCLUDED.asaas_customer_id, created_at = EXCLUDED.created_at",
                (payment_id, cnpj, hwid, plano, customer_id, datetime.datetime.utcnow().isoformat())
            )
        else:
            _execute(conn,
                "INSERT OR REPLACE INTO payments (payment_id, customer_cnpj, hwid, plano, status, asaas_customer_id, created_at) "
                "VALUES (?, ?, ?, ?, 'PENDING', ?, ?)",
                (payment_id, cnpj, hwid, plano, customer_id, datetime.datetime.utcnow().isoformat())
            )


def update_payment_status(payment_id, status):
    with get_db() as conn:
        _execute(conn, "UPDATE payments SET status = ? WHERE payment_id = ?", (status, payment_id))


def get_payment(payment_id):
    with get_db() as conn:
        return _fetchone(conn, "SELECT * FROM payments WHERE payment_id = ?", (payment_id,))


def get_payment_by_cnpj_hwid(cnpj, hwid):
    with get_db() as conn:
        return _fetchone(conn,
            "SELECT * FROM payments WHERE customer_cnpj = ? AND hwid = ? ORDER BY created_at DESC LIMIT 1",
            (cnpj, hwid)
        )


def insert_license(payment_id, license_key, expires_at):
    import datetime
    with get_db() as conn:
        _execute(conn,
            "INSERT INTO licenses (payment_id, license_key, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (payment_id, license_key, expires_at, datetime.datetime.utcnow().isoformat())
        )


def get_license_by_payment(payment_id):
    with get_db() as conn:
        return _fetchone(conn,
            "SELECT * FROM licenses WHERE payment_id = ? ORDER BY id DESC LIMIT 1",
            (payment_id,)
        )


def is_license_valid(license_record):
    if not license_record:
        return False
    import datetime
    expires_at = datetime.datetime.fromisoformat(license_record["expires_at"])
    return datetime.datetime.utcnow() < expires_at


def list_hwids(cnpj):
    with get_db() as conn:
        rows = _fetchall(conn,
            "SELECT DISTINCT hwid FROM payments WHERE customer_cnpj = ? ORDER BY created_at DESC",
            (cnpj,)
        )
        return [row["hwid"] for row in rows]
