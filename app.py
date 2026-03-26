import os
import sqlite3
import datetime
import logging
from flask import Flask, request, jsonify, render_template
from keygen_nfe import generate_key
import requests

# Carregar variáveis de ambiente do .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv não instalado, usar variáveis do sistema
    pass

app = Flask(__name__)

# =========================
# CONFIG
# =========================

ASAAS_API_KEY = os.getenv("ASAAS_API_KEY")
if not ASAAS_API_KEY:
    raise RuntimeError("ASAAS_API_KEY is required")

ASAAS_URL = os.getenv("ASAAS_URL", "https://sandbox.asaas.com/api/v3")
DATABASE_PATH = os.getenv("DATABASE_PATH", "nfe_licensing.db")
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN")

HEADERS = {
    "access_token": ASAAS_API_KEY,
    "Content-Type": "application/json"
}

PLANS = {
    "mensal": {"dias": 30, "valor": 29.90},
    "trimestral": {"dias": 90, "valor": 79.90},
    "anual": {"dias": 365, "valor": 199.90},
    "vitalicio": {"dias": 36500, "valor": 499.90}
}

# =========================
# LOGGING
# =========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# DB
# =========================

def get_db():
    conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                cnpj TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
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
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id TEXT NOT NULL,
                license_key TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(payment_id) REFERENCES payments(payment_id)
            );
            """
        )


init_db()

# =========================
# HELPER ASAAS
# =========================

def asaas_request(method, path, **kwargs):
    url = f"{ASAAS_URL}{path}"
    headers = kwargs.pop("headers", {})
    merged_headers = {**HEADERS, **headers}
    try:
        response = requests.request(method, url, headers=merged_headers, timeout=15, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error("Asaas request failed: %s %s -> %s", method, url, e)
        raise


def get_customer(cnpj):
    with get_db() as conn:
        row = conn.execute("SELECT customer_id FROM customers WHERE cnpj = ?", (cnpj,)).fetchone()
        return row["customer_id"] if row else None


def save_customer(cnpj, customer_id):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO customers (cnpj, customer_id, created_at) VALUES (?, ?, ?)",
            (cnpj, customer_id, datetime.datetime.utcnow().isoformat())
        )


def find_or_create_customer(cnpj):
    existing = get_customer(cnpj)
    if existing:
        return existing

    # busca no Asaas sandbox/prod
    try:
        customers_data = asaas_request("GET", f"/customers?cpfCnpj={cnpj}")
        if isinstance(customers_data, list) and customers_data:
            customer_id = customers_data[0].get("id")
            if customer_id:
                save_customer(cnpj, customer_id)
                return customer_id
    except Exception:
        logger.info("Não foi possível buscar cliente existente no Asaas, criando novo")

    payload = {"name": f"Cliente {cnpj}", "cpfCnpj": cnpj}
    created = asaas_request("POST", "/customers", json=payload)
    customer_id = created.get("id")
    if not customer_id:
        raise RuntimeError("Erro ao criar cliente no Asaas")

    save_customer(cnpj, customer_id)
    return customer_id


def save_payment(payment_id, cnpj, hwid, plano, customer_id):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO payments (payment_id, customer_cnpj, hwid, plano, status, asaas_customer_id, created_at) VALUES (?, ?, ?, ?, 'PENDING', ?, ?)",
            (payment_id, cnpj, hwid, plano, customer_id, datetime.datetime.utcnow().isoformat())
        )


def update_payment_status(payment_id, status):
    with get_db() as conn:
        conn.execute(
            "UPDATE payments SET status = ? WHERE payment_id = ?", (status, payment_id)
        )


def get_payment(payment_id):
    with get_db() as conn:
        return conn.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,)).fetchone()


def get_payment_by_cnpj_hwid(cnpj, hwid):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM payments WHERE customer_cnpj = ? AND hwid = ? ORDER BY created_at DESC LIMIT 1",
            (cnpj, hwid)
        ).fetchone()


def insert_license(payment_id, license_key, expires_at):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO licenses (payment_id, license_key, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (payment_id, license_key, expires_at, datetime.datetime.utcnow().isoformat())
        )


def get_license_by_payment(payment_id):
    with get_db() as conn:
        return conn.execute("SELECT * FROM licenses WHERE payment_id = ? ORDER BY id DESC LIMIT 1", (payment_id,)).fetchone()


def is_license_valid(license_record):
    if not license_record:
        return False
    expires_at = datetime.datetime.fromisoformat(license_record["expires_at"])
    return datetime.datetime.utcnow() < expires_at


# =========================
# ROTAS
# =========================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/criar-pagamento", methods=["POST"])
def criar_pagamento():
    data = request.json or {}
    cnpj = data.get("cnpj")
    hwid = data.get("hwid")
    plano = data.get("plano")

    if not cnpj or not hwid or not plano:
        return jsonify({"erro": "Dados incompletos"}), 400

    if plano not in PLANS:
        return jsonify({"erro": "Plano inválido"}), 400

    plano_info = PLANS[plano]

    try:
        customer_id = find_or_create_customer(cnpj)

        vencimento = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        cobranca_payload = {
            "customer": customer_id,
            "billingType": "PIX",
            "value": plano_info["valor"],
            "dueDate": vencimento,
            "description": f"NFE Reader - {plano}"
        }
        cobranca_data = asaas_request("POST", "/payments", json=cobranca_payload)

        payment_id = cobranca_data.get("id")
        if not payment_id:
            return jsonify({"erro": "Erro ao criar cobrança"}), 500

        save_payment(payment_id, cnpj, hwid, plano, customer_id)

        pix_data = asaas_request("GET", f"/payments/{payment_id}/pixQrCode")
        return jsonify({
            "payment_id": payment_id,
            "valor": plano_info["valor"],
            "pix_copia_cola": pix_data.get("payload"),
            "qr_code": pix_data.get("encodedImage")
        })

    except requests.exceptions.HTTPError as e:
        logger.error("HTTPError criar_pagamento: %s", e)
        return jsonify({"erro": "Comunicação com Asaas falhou", "detalhes": str(e)}), 502
    except Exception as e:
        logger.exception("Erro inesperado criar_pagamento")
        return jsonify({"erro": "Erro interno", "detalhes": str(e)}), 500


@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_TOKEN:
        token_header = request.headers.get("X-Hook-Token")
        if token_header != WEBHOOK_TOKEN:
            logger.warning("Webhook recebido com token inválido: %s", token_header)
            return jsonify({"erro": "Token inválido"}), 401

    payload = request.json or {}
    logger.info("Webhook recebido: %s", payload)

    if payload.get("event") != "PAYMENT_RECEIVED":
        return jsonify({"status": "evento ignorado"}), 200

    payment = payload.get("payment", {})
    payment_id = payment.get("id")
    if not payment_id:
        return jsonify({"erro": "payment_id não fornecido"}), 400

    record = get_payment(payment_id)
    if not record:
        logger.warning("Pagamento não encontrado: %s", payment_id)
        return jsonify({"erro": "Pagamento não encontrado"}), 404

    if record["status"] == "PAID":
        return jsonify({"status": "já processado"}), 200

    try:
        dias = PLANS.get(record["plano"], {}).get("dias", 0)
        chave = generate_key(record["customer_cnpj"], record["hwid"], dias)
        expires_at = (datetime.datetime.utcnow() + datetime.timedelta(days=dias)).strftime("%Y-%m-%d")

        insert_license(payment_id, chave, expires_at)
        update_payment_status(payment_id, "PAID")

        logger.info("Chave gerada para %s: %s", payment_id, chave)

        # Automação de entrega de chave: callback configurável
        license_callback_url = os.getenv("LICENSE_CALLBACK_URL")
        if license_callback_url:
            callback_payload = {
                "payment_id": payment_id,
                "cnpj": record["customer_cnpj"],
                "hwid": record["hwid"],
                "plano": record["plano"],
                "license_key": chave,
                "expires_at": expires_at
            }
            try:
                requests.post(license_callback_url, json=callback_payload, timeout=10)
            except requests.exceptions.RequestException as e:
                logger.warning("Falha no callback de entrega: %s", e)

        return jsonify({"status": "ok", "license_key": chave}), 200

    except Exception as e:
        logger.exception("Falha ao processar webhook")
        return jsonify({"erro": "Falha interna"}), 500


@app.route("/status/<payment_id>")
def status_pago(payment_id):
    record = get_payment(payment_id)
    if not record:
        return jsonify({"erro": "Pagamento não encontrado"}), 404

    license_record = get_license_by_payment(payment_id)
    return jsonify({
        "payment": {
            "id": record["payment_id"],
            "cnpj": record["customer_cnpj"],
            "hwid": record["hwid"],
            "plano": record["plano"],
            "status": record["status"]
        },
        "license": {
            "license_key": license_record["license_key"] if license_record else None,
            "expires_at": license_record["expires_at"] if license_record else None
        }
    })


@app.route("/consulta-licenca")
def consulta_licenca():
    cnpj = request.args.get("cnpj")
    hwid = request.args.get("hwid")
    if not cnpj or not hwid:
        return jsonify({"erro": "cnpj e hwid são obrigatórios"}), 400

    record = get_payment_by_cnpj_hwid(cnpj, hwid)
    if not record:
        return jsonify({"erro": "Nenhum pagamento encontrado"}), 404

    license_record = get_license_by_payment(record["payment_id"])
    return jsonify({
        "payment": {
            "id": record["payment_id"],
            "cnpj": record["customer_cnpj"],
            "hwid": record["hwid"],
            "plano": record["plano"],
            "status": record["status"]
        },
        "license": {
            "license_key": license_record["license_key"] if license_record else None,
            "expires_at": license_record["expires_at"] if license_record else None
        }
    })


@app.route("/obter-licenca", methods=["POST"])
def obter_licenca():
    data = request.json or {}
    cnpj = data.get("cnpj")
    hwid = data.get("hwid")

    if not cnpj or not hwid:
        return jsonify({"erro": "cnpj e hwid são obrigatórios"}), 400

    # Busca último pagamento para este CNPJ/HWID
    record = get_payment_by_cnpj_hwid(cnpj, hwid)
    if not record:
        return jsonify({"erro": "Nenhum pagamento encontrado para este CNPJ/HWID"}), 404

    if record["status"] != "PAID":
        return jsonify({"erro": "Pagamento não foi confirmado"}), 402  # Payment Required

    # Busca licença associada
    license_record = get_license_by_payment(record["payment_id"])
    if not license_record:
        return jsonify({"erro": "Licença não foi gerada ainda"}), 404

    # Verifica se não expirou
    if not is_license_valid(license_record):
        return jsonify({"erro": "Licença expirada"}), 410  # Gone

    return jsonify({
        "license_key": license_record["license_key"],
        "expires_at": license_record["expires_at"],
        "plano": record["plano"],
        "payment_id": record["payment_id"]
    }), 200


@app.route("/teste-asaas")
def teste_asaas():
    try:
        result = asaas_request("GET", "/customers")
        return jsonify(result)
    except Exception as e:
        logger.error("teste_asaas falhou: %s", e)
        return jsonify({"erro": "falha na comunicação Asaas", "detalhes": str(e)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
