# nfe-licensing-server

Sistema de licenciamento automático para NFE Reader (Flask + Asaas + SQLite + webhook).

## Pré-requisitos

- Python 3.8+
- Dependências: `pip install -r requirements.txt`
- Copie `.env.example` para `.env` e configure as variáveis obrigatórias
- Variáveis de ambiente obrigatórias:
  - `ASAAS_API_KEY` (chave da API Asaas)
- Variáveis opcionais:
  - `SECRET_WORD` (padrão seguro se não definido)
  - `ASAAS_URL` (padrão: sandbox)
  - `DATABASE_PATH` (padrão: `nfe_licensing.db`)
  - `WEBHOOK_TOKEN` (proteção webhook)
  - `LICENSE_CALLBACK_URL` (entrega automática)
  - `PORT` (padrão: 5000)

## Endpoints

- `GET /` - formulário frontend em `templates/index.html`
- `POST /criar-pagamento` - cria cliente Asaas, cobrança PIX e retorna QR/Payload
- `POST /webhook` - processa evento `PAYMENT_RECEIVED`, gera licença e salva
- `GET /status/<payment_id>` - consulta status + key de pagamento
- `GET /consulta-licenca?cnpj=<cnpj>&hwid=<hwid>` - consulta última licença vinculada
- `POST /obter-licenca` - API para cliente desktop: valida CNPJ/HWID, status PAID e validade da licença
- `GET /teste-asaas` - checa conexão com Asaas

## Fluxo

1. Cliente envia CPF/CNPJ, HWID e plano
2. Backend cria cliente (ou reusa) + cobrança PIX Asaas
3. Retorna dados do PIX pro frontend
4. Asaas notifica `/webhook` com `PAYMENT_RECEIVED`
5. Backend cria chave com `keygen_nfe.generate_key` e persiste
6. /consulta-licenca retorna chave e validade

## Como rodar local

1. **Instalar dependências**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configurar ambiente**:
   ```bash
   cp .env.example .env
   # Edite .env com suas chaves
   ```

3. **Executar**:
   ```bash
   python app.py
   ```

4. **Acessar**: `http://localhost:5000`

## Render Deploy

- Configure o `Procfile` para usar `gunicorn app:app`.
- Adicione as variáveis de ambiente listadas acima no painel Render.
- Aponte webhook Asaas para `https://<app>.onrender.com/webhook` e token se configurar.

## Testes de webhook (sandbox)

1. Criar pagamento e pegar `payment_id` da resposta.
2. Simular webhook via `curl` / `test.http`:

```bash
curl -X POST https://<seu_url>/webhook \
  -H "Content-Type: application/json" \
  -H "X-Hook-Token: <WEBHOOK_TOKEN>" \
  -d '{"event": "PAYMENT_RECEIVED", "payment": {"id": "<payment_id>"}}'
```

## Notas

- `payments` não perde dados após reiniciar porque salva em SQLite.
- Recomendado migrar para PostgreSQL no ambiente de produção.
- Verificar `ASAAS_URL` para mudar de sandbox para produção antes de ir ao ar.

## Como usar /obter-licenca (cliente desktop)

O endpoint `POST /obter-licenca` é projetado para o software NFE Reader verificar automaticamente se há uma licença válida.

**Request:**
```json
{
  "cnpj": "12345678000199",
  "hwid": "ABC-123-XYZ"
}
```

**Response (sucesso):**
```json
{
  "license_key": "NFE-12345678000199-2026-12-31-AB12CD34",
  "expires_at": "2026-12-31",
  "plano": "anual",
  "payment_id": "pay_123456789"
}
```

**Erros possíveis:**
- 400: CNPJ/HWID ausentes
- 404: Nenhum pagamento encontrado
- 402: Pagamento não confirmado
- 404: Licença não gerada
- 410: Licença expirada

**Exemplo de uso no Python (cliente):**
```python
import requests

response = requests.post("https://<seu_url>/obter-licenca", json={
    "cnpj": "12345678000199",
    "hwid": "ABC-123-XYZ"
})

if response.status_code == 200:
    data = response.json()
    print(f"Licença válida até {data['expires_at']}")
else:
    print("Licença inválida ou expirada")
```
