from flask import Flask, request, jsonify, render_template
from keygen_nfe import generate_key
import requests
import datetime

app = Flask(__name__)

# =========================
# CONFIG ASAAS (SANDBOX)
# =========================

ASAAS_API_KEY = "SUA_API_KEY_AQUI"
ASAAS_URL = "https://sandbox.asaas.com/api/v3"

HEADERS = {
    "access_token": ASAAS_API_KEY,
    "Content-Type": "application/json"
}

# =========================
# PLANOS
# =========================

PLANS = {
    "mensal": {"dias": 30, "valor": 29.90},
    "trimestral": {"dias": 90, "valor": 79.90},
    "anual": {"dias": 365, "valor": 199.90},
    "vitalicio": {"dias": 36500, "valor": 499.90}
}

# =========================
# ROTAS
# =========================

@app.route("/")
def home():
    return render_template("index.html")

# =========================
# CRIAR PAGAMENTO REAL (ASAAS)
# =========================

@app.route("/criar-pagamento", methods=["POST"])
def criar_pagamento():
    data = request.json

    cnpj = data.get("cnpj")
    hwid = data.get("hwid")
    plano = data.get("plano")

    if not cnpj or not hwid or not plano:
        return jsonify({"erro": "Dados incompletos"}), 400

    if plano not in PLANS:
        return jsonify({"erro": "Plano inválido"}), 400

    plano_info = PLANS[plano]

    # =========================
    # 1. CRIAR CLIENTE
    # =========================

    cliente_payload = {
        "name": f"Cliente {cnpj}",
        "cpfCnpj": cnpj
    }

    cliente_resp = requests.post(
        f"{ASAAS_URL}/customers",
        json=cliente_payload,
        headers=HEADERS
    )

    cliente_data = cliente_resp.json()

    if "errors" in cliente_data:
        return jsonify(cliente_data), 400

    customer_id = cliente_data["id"]

    # =========================
    # 2. CRIAR COBRANÇA PIX
    # =========================

    hoje = datetime.date.today()
    vencimento = hoje + datetime.timedelta(days=1)

    cobranca_payload = {
        "customer": customer_id,
        "billingType": "PIX",
        "value": plano_info["valor"],
        "dueDate": vencimento.strftime("%Y-%m-%d"),
        "description": f"NFE Reader - Plano {plano}"
    }

    cobranca_resp = requests.post(
        f"{ASAAS_URL}/payments",
        json=cobranca_payload,
        headers=HEADERS
    )

    cobranca_data = cobranca_resp.json()

    if "errors" in cobranca_data:
        return jsonify(cobranca_data), 400

    payment_id = cobranca_data["id"]

    # =========================
    # 3. OBTER PIX (QR CODE)
    # =========================

    pix_resp = requests.get(
        f"{ASAAS_URL}/payments/{payment_id}/pixQrCode",
        headers=HEADERS
    )

    pix_data = pix_resp.json()

    return jsonify({
        "payment_id": payment_id,
        "valor": plano_info["valor"],
        "pix_copia_cola": pix_data.get("payload"),
        "qr_code_base64": pix_data.get("encodedImage")
    })


# =========================
# WEBHOOK (PRÓXIMO PASSO)
# =========================

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("Webhook recebido:", data)
    return "", 200


# =========================
# TESTE ASAAS
# =========================

@app.route("/teste-asaas")
def teste_asaas():
    response = requests.get(
        f"{ASAAS_URL}/customers",
        headers=HEADERS
    )
    return response.json()


# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run()