"""
Script para migrar dados do SQLite local para PostgreSQL no Render.

Uso:
    python scripts/migrar_sqlite_para_postgres.py

Pré-requisitos:
    - DATABASE_URL configurada no ambiente (ou no .env)
    - nfe_licensing.db com dados existentes
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERRO: Configure DATABASE_URL no .env ou nas variáveis de ambiente")
    sys.exit(1)

import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

SQLITE_PATH = os.getenv("DATABASE_PATH", "nfe_licensing.db")

def conectar_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def conectar_pg():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def migrar_tabela(nome, colunas, insert_sql, on_conflict=""):
    print(f"\nMigrando {nome}...")
    src = conectar_sqlite()
    rows = src.execute(f"SELECT * FROM {nome}").fetchall()
    src.close()
    if not rows:
        print(f"  Nenhum registro em {nome}")
        return 0

    dst = conectar_pg()
    cur = dst.cursor()
    count = 0
    for row in rows:
        vals = tuple(str(row[c]) if row[c] is not None else None for c in colunas)
        try:
            cur.execute(insert_sql, vals)
            count += 1
        except Exception as e:
            print(f"  Erro ao inserir: {e}")
    dst.commit()
    dst.close()
    print(f"  {count}/{len(rows)} registros migrados em {nome}")
    return count


def main():
    if not os.path.exists(SQLITE_PATH):
        print(f"Arquivo SQLite não encontrado: {SQLITE_PATH}")
        sys.exit(1)

    print("=" * 60)
    print("Migração SQLite → PostgreSQL")
    print("=" * 60)

    clientes_cols = ["cnpj", "customer_id", "created_at"]
    clientes_sql = "INSERT INTO customers (cnpj, customer_id, created_at) VALUES (%s, %s, %s)"
    total = migrar_tabela("customers", clientes_cols, clientes_sql)

    pag_cols = ["payment_id", "customer_cnpj", "hwid", "plano", "status", "asaas_customer_id", "created_at"]
    pag_sql = "INSERT INTO payments (payment_id, customer_cnpj, hwid, plano, status, asaas_customer_id, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
    total += migrar_tabela("payments", pag_cols, pag_sql)

    lic_cols = ["payment_id", "license_key", "expires_at", "created_at"]
    lic_sql = "INSERT INTO licenses (payment_id, license_key, expires_at, created_at) VALUES (%s, %s, %s, %s)"
    total += migrar_tabela("licenses", lic_cols, lic_sql)

    print("\n" + "=" * 60)
    print(f"Migração concluída! {total} registros transferidos.")
    print("=" * 60)


if __name__ == "__main__":
    main()
