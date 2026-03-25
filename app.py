from flask import Flask, request, jsonify, render_template
from keygen_nfe import generate_key
import uuid
import requests

# =========================
# CONFIG ASAAS (SANDBOX)
# =========================

ASAAS_API_KEY = ""
ASAAS_URL = "https://sandbox.asaas.com/api/v3"

app = Flask(__name__)

# =========================
# CONFIGURAÇÕES
# =========================

PLANS = {
    "mensal": 30,
    "trimestral": 90,
    "anual": 365,
    "vitalicio": 36500
}

VALORES = {
    "mensal": 29.90,
    "trimestral": 79.90,
    "anual": 199.90,
    "vitalicio": 499.90
}

# MAPEAMENTO DE PAGAMENTOS
PAYMENTS = {}

# =========================
# FUNÇÕES ASAAS
# =========================

def criar_cliente_asaas(cnpj):
    headers = {
        "access_token": ASAAS_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "name": f"Cliente {cnpj}",
        "cpfCnpj": cnpj
    }

    response = requests.post(
        f"{ASAAS_URL}/customers",
        json=data,
        headers=headers
    )

    return response.json()


def criar_cobranca_pix(customer_id, valor):
    headers = {
        "access_token": ASAAS_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "customer": customer_id,
        "billingType": "PIX",
        "value": valor,
        "dueDate": "2026-12-31"
    }

    response = requests.post(
        f"{ASAAS_URL}/payments",
        json=data,
        headers=headers
    )

    return response.json()


def obter_qr_code(payment_id):
    headers = {
        "access_token": ASAAS_API_KEY
    }

    response = requests.get(
        f"{ASAAS_URL}/payments/{payment_id}/pixQrCode",
        headers=headers
    )

    return response.json()

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

    valor = VALORES.get(plano)

    cliente = criar_cliente_asaas(cnpj)
    customer_id = cliente.get("id")

    cobranca = criar_cobranca_pix(customer_id, valor)
    payment_id = cobranca.get("id")

    # 🔥 SALVA PARA USAR NO WEBHOOK
    PAYMENTS[payment_id] = {
        "cnpj": cnpj,
        "hwid": hwid,
        "plano": plano,
        "status": "pendente"
    }

    qr = obter_qr_code(payment_id)

    return jsonify({
        "payment_id": payment_id,
        "valor": valor,
        "qr_code": qr.get("encodedImage"),
        "pix_copia_cola": qr.get("payload")
    })

# =========================
# WEBHOOK (AQUI ESTÁ O PODER)
# =========================

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    evento = data.get("event")
    pagamento = data.get("payment")

    if not pagamento:
        return jsonify({"status": "ignorado"})

    payment_id = pagamento.get("id")

    # 🔥 SOMENTE QUANDO PAGO
    if evento == "PAYMENT_RECEIVED":
        info = PAYMENTS.get(payment_id)

        if not info:
            return jsonify({"status": "pagamento não encontrado"})

        dias = PLANS.get(info["plano"])

        chave = generate_key(
            info["cnpj"],
            info["hwid"],
            dias
        )

        # Aqui você pode salvar, enviar email, etc
        print("🔥 PAGAMENTO CONFIRMADO")
        print("🔑 CHAVE GERADA:", chave)

        info["status"] = "pago"
        info["chave"] = chave

    return jsonify({"status": "ok"})

# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run    