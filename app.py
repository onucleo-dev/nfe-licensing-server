from flask import Flask, request, jsonify, render_template
from keygen_nfe import generate_key
import requests
import datetime

app = Flask(__name__)

# =========================
# CONFIG ASAAS
# =========================

ASAAS_API_KEY = "$aact_hmlg_000MzkwODA2MWY2OGM3MWRlMDU2NWM3MzJlNzZmNGZhZGY6OjA0YzM3NGM1LWYxZWYtNDk2ZS1iM2Q5LTc2OTY4N2EzMDJhZDo6JGFhY2hfZWQwMzY1ZWYtYTc4OS00N2IzLThjYjItM2YwMmFiN2ZlYzkx"
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
# "BANCO" TEMPORÁRIO
# =========================

PAYMENTS = {}

# =========================
# ROTAS
# =========================

@app.route("/")
def home():
    return render_template("index.html")


# =========================
# CRIAR PAGAMENTO
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
    # CRIAR CLIENTE
    # =========================

    cliente_resp = requests.post(
        f"{ASAAS_URL}/customers",
        json={
            "name": f"Cliente {cnpj}",
            "cpfCnpj": cnpj
        },
        headers=HEADERS
    )

    cliente_data = cliente_resp.json()

    if "errors" in cliente_data:
        return jsonify(cliente_data), 400

    customer_id = cliente_data["id"]

    # =========================
    # CRIAR COBRANÇA
    # =========================

    vencimento = datetime.date.today() + datetime.timedelta(days=1)

    cobranca_resp = requests.post(
        f"{ASAAS_URL}/payments",
        json={
            "customer": customer_id,
            "billingType": "PIX",
            "value": plano_info["valor"],
            "dueDate": vencimento.strftime("%Y-%m-%d"),
            "description": f"NFE Reader - {plano}"
        },
        headers=HEADERS
    )

    cobranca_data = cobranca_resp.json()

    if "errors" in cobranca_data:
        return jsonify(cobranca_data), 400

    payment_id = cobranca_data["id"]

    # 🔥 SALVAR NO "BANCO"
    PAYMENTS[payment_id] = {
        "cnpj": cnpj,
        "hwid": hwid,
        "plano": plano
    }

    # =========================
    # OBTER PIX
    # =========================

    pix_resp = requests.get(
        f"{ASAAS_URL}/payments/{payment_id}/pixQrCode",
        headers=HEADERS
    )

    pix_data = pix_resp.json()

    return jsonify({
        "payment_id": payment_id,
        "valor": plano_info["valor"],
        "pix_copia_cola": pix_data.get("payload")
    })


# =========================
# WEBHOOK (AUTOMÁTICO)
# =========================

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    print("📩 Webhook recebido:", data)

    if data.get("event") == "PAYMENT_RECEIVED":
        payment = data.get("payment", {})
        payment_id = payment.get("id")

        if payment_id in PAYMENTS:
            info = PAYMENTS[payment_id]

            dias = PLANS[info["plano"]]["dias"]

            chave = generate_key(
                info["cnpj"],
                info["hwid"],
                dias
            )

            print("🔑 CHAVE GERADA:", chave)

            # Aqui depois você pode:
            # enviar email
            # salvar banco
            # enviar pro app

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