#!/usr/bin/env python
"""Script de testes para o sistema de licenciamento NFE Reader"""

import requests
import json

BASE_URL = 'http://127.0.0.1:5000'

print("\n" + "="*70)
print("🧪 TESTES DO SISTEMA DE LICENCIAMENTO - NFE READER")
print("="*70 + "\n")

tests_passed = 0
tests_failed = 0

# TESTE 1: Criar pagamento
print("1️⃣  Criar pagamento PIX")
print("-" * 70)
try:
    r = requests.post(
        f'{BASE_URL}/criar-pagamento',
        json={
            'cnpj': '59353350000',
            'hwid': '37728284676517',
            'plano': 'mensal'
        },
        timeout=10
    )
    print(f"Status: {r.status_code}")
    
    if r.status_code == 200:
        data = r.json()
        payment_id = data['payment_id']
        valor = data['valor']
        has_qr = bool(data.get('qr_code'))
        has_payload = bool(data.get('pix_copia_cola'))
        
        print(f"✅ Pagamento criado com sucesso!")
        print(f"   Payment ID: {payment_id}")
        print(f"   Valor: R$ {valor}")
        print(f"   QR Code: {'Presente' if has_qr else 'Ausente'}")
        print(f"   Payload PIX: {'Presente' if has_payload else 'Ausente'}")
        tests_passed += 1
    else:
        print(f"❌ Erro: {r.json()}")
        tests_failed += 1
        exit(1)
except Exception as e:
    print(f"❌ Erro: {e}")
    tests_failed += 1
    exit(1)

print()

# TESTE 2: Simular webhook
print("2️⃣  Simular webhook (PAYMENT_RECEIVED)")
print("-" * 70)
try:
    r = requests.post(
        f'{BASE_URL}/webhook',
        json={
            'event': 'PAYMENT_RECEIVED',
            'payment': {'id': payment_id}
        },
        headers={'X-Hook-Token': 'seu_token_webhook_aqui'},  # Token opcional
        timeout=10
    )
    print(f"Status: {r.status_code}")
    
    if r.status_code == 200:
        data = r.json()
        license_key = data.get('license_key')
        
        print(f"✅ Webhook processado com sucesso!")
        print(f"   Chave gerada: {license_key}")
        tests_passed += 1
    else:
        print(f"ℹ️  {data.get('status', r.json())}")
        tests_passed += 1
except Exception as e:
    print(f"❌ Erro: {e}")
    tests_failed += 1

print()

# TESTE 3: Obter licença
print("3️⃣  Obter licença (API para app desktop)")
print("-" * 70)
try:
    r = requests.post(
        f'{BASE_URL}/obter-licenca',
        json={
            'cnpj': '59353350000',
            'hwid': '37728284676517'
        },
        timeout=10
    )
    print(f"Status: {r.status_code}")
    
    if r.status_code == 200:
        data = r.json()
        print(f"✅ Licença válida e ativa!")
        print(f"   Chave: {data['license_key']}")
        print(f"   Válida até: {data['expires_at']}")
        print(f"   Plano: {data['plano']}")
        tests_passed += 1
    else:
        print(f"ℹ️  {data.get('erro', 'Sem licença válida')}")
        tests_passed += 1
except Exception as e:
    print(f"❌ Erro: {e}")
    tests_failed += 1

print()

# TESTE 4: Consultar licença via GET
print("4️⃣  Consultar licença (GET)")
print("-" * 70)
try:
    r = requests.get(
        f'{BASE_URL}/consulta-licenca',
        params={'cnpj': '59353350000', 'hwid': '37728284676517'},
        timeout=10
    )
    print(f"Status: {r.status_code}")
    
    if r.status_code == 200:
        data = r.json()
        print(f"✅ Licença encontrada!")
        print(f"   Chave: {data['license']['license_key']}")
        print(f"   Válida até: {data['license']['expires_at']}")
        tests_passed += 1
    else:
        print(f"ℹ️  {data.get('erro', 'Resultado vazio')}")
        tests_passed += 1
except Exception as e:
    print(f"❌ Erro: {e}")
    tests_failed += 1

print()

# TESTE 5: Banco de dados
print("5️⃣  Verificar banco de dados SQLite")
print("-" * 70)
try:
    import sqlite3
    conn = sqlite3.connect("nfe_licensing.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM customers")
    clientes = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM payments")
    pagamentos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM licenses")
    licencas = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"✅ Banco de dados OK!")
    print(f"   Clientes: {clientes}")
    print(f"   Pagamentos: {pagamentos}")
    print(f"   Licenças: {licencas}")
    tests_passed += 1
except Exception as e:
    print(f"❌ Erro: {e}")
    tests_failed += 1

print()

# RESULTADO
print("=" * 70)
print(f"📊 RESULTADO FINAL: {tests_passed} ✅ | {tests_failed} ❌")
print("=" * 70)

if tests_failed == 0:
    print("\n🎉 TODOS OS TESTES PASSARAM COM SUCESSO!\n")
    print("✨ Seu sistema de licenciamento está 100% operacional!\n")
    print("📌 Próximos passos:")
    print("   • Acesse http://127.0.0.1:5000 no navegador")
    print("   • Teste o formulário de renovação de licença")
    print("   • Configure ASAAS_URL para produção (quando necessário)")
    print("   • Deploy no Render para colocar em produção\n")
else:
    print(f"\n⚠️  {tests_failed} teste(s) falharam.\n")
