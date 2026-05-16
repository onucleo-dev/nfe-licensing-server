import os
import datetime
import logging
from flask import Flask, request, jsonify, render_template, redirect
from keygen_nfe import generate_key
import requests
from db import (
    init_db, get_customer, save_customer, save_payment,
    update_payment_status, get_payment, get_payment_by_cnpj_hwid,
    insert_license, get_license_by_payment, is_license_valid, list_hwids
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

ASAAS_API_KEY = os.getenv("ASAAS_API_KEY")
if not ASAAS_API_KEY:
    raise RuntimeError("ASAAS_API_KEY is required")

ASAAS_URL = os.getenv("ASAAS_URL", "https://sandbox.asaas.com/api/v3")
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


def find_or_create_customer(cnpj):
    existing = get_customer(cnpj)
    if existing:
        return existing

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


# =========================
# ROTAS
# =========================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/download")
def download():
    return redirect("https://github.com/onucleo-dev/nfe-licensing-server/releases/latest/download/NFE_Reader.exe")

@app.route("/manual")
def manual():
    return redirect("/static/MANUAL_DO_USUARIO.pdf")


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

    record = get_payment_by_cnpj_hwid(cnpj, hwid)
    if not record:
        return jsonify({"erro": "Nenhum pagamento encontrado para este CNPJ/HWID"}), 404

    if record["status"] != "PAID":
        return jsonify({"erro": "Pagamento não foi confirmado"}), 402

    license_record = get_license_by_payment(record["payment_id"])
    if not license_record:
        return jsonify({"erro": "Licença não foi gerada ainda"}), 404

    if not is_license_valid(license_record):
        return jsonify({"erro": "Licença expirada"}), 410

    return jsonify({
        "license_key": license_record["license_key"],
        "expires_at": license_record["expires_at"],
        "plano": record["plano"],
        "payment_id": record["payment_id"]
    }), 200


@app.route("/simular-pagamento/<payment_id>", methods=["POST"])
def simular_pagamento(payment_id):
    record = get_payment(payment_id)
    if not record:
        return jsonify({"erro": "Pagamento não encontrado"}), 404

    if record["status"] == "PAID":
        return jsonify({"status": "já processado"}), 200

    try:
        dias = PLANS.get(record["plano"], {}).get("dias", 0)
        chave = generate_key(record["customer_cnpj"], record["hwid"], dias)
        expires_at = (datetime.datetime.utcnow() + datetime.timedelta(days=dias)).strftime("%Y-%m-%d")

        insert_license(payment_id, chave, expires_at)
        update_payment_status(payment_id, "PAID")

        logger.info("Pagamento simulado para %s: %s", payment_id, chave)
        return jsonify({"status": "ok", "license_key": chave, "expires_at": expires_at}), 200
    except Exception as e:
        logger.exception("Falha ao simular pagamento")
        return jsonify({"erro": "Falha interna"}), 500


@app.route("/hwids")
def list_hwids():
    cnpj = request.args.get("cnpj")
    if not cnpj:
        return jsonify({"erro": "cnpj é obrigatório"}), 400
    return jsonify({"hwids": list_hwids(cnpj)})


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
