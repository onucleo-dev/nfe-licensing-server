# 🚀 Guia de Deploy - Render + Asaas

## Pré-requisitos

- Conta no [Render.com](https://render.com)
- Conta Asaas com API Key gerada
- Repositório GitHub configurado
- Procfile configurado ✅ (já está pronto)

---

## 📋 Passo 1: Preparar credenciais Asaas

### Obter chave API do Asaas

1. Acesse https://app.asaas.com (ou sandbox: https://app.sandbox.asaas.com)
2. Menu: **Configurações → Integrações → API**
3. Copie a **Chave de API** (começa com `$aact_` ou `$aask_`)

### URLs disponíveis

- **Sandbox** (Teste): `https://sandbox.asaas.com/api/v3`
- **Produção** (Real): `https://www.asaas.com/api/v3`

---

## 📋 Passo 2: Criar serviço no Render

1. Vá para [dashboard.render.com](https://dashboard.render.com)
2. Clique em **New → Web Service**
3. Selecione seu repositório GitHub: `nfe-licensing-server`
4. Configure:
   - **Name**: `nfe-licensing-server` (ou seu nome)
   - **Environment**: `Python`
   - **Region**: `São Paulo (South America)` (recomendado)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`

---

## 📋 Passo 3: Configurar variáveis de ambiente

No painel Render, vá em **Environment**:

### Variáveis obrigatórias

| Variável | Valor | Exemplo |
|----------|-------|---------|
| `ASAAS_API_KEY` | Chave da API Asaas | `$aask_XXXXXXXXX...` |
| `ASAAS_URL` | URL da API | `https://sandbox.asaas.com/api/v3` ou `https://www.asaas.com/api/v3` |
| `SECRET_WORD` | Palavra secreta para chaves | `seu_segredo_aqui` |

### Variáveis opcionais

| Variável | Valor | Padrão |
|----------|-------|--------|
| `WEBHOOK_TOKEN` | Token de autenticação webhook | (não definido = sem proteção) |
| `DATABASE_PATH` | Caminho do banco | `nfe_licensing.db` |
| `LICENSE_CALLBACK_URL` | URL para callback de licença | (não definido = sem callback) |
| `PORT` | Porta do servidor | `5000` |

---

## 📋 Passo 4: Escolher ambiente (Sandbox vs Produção)

### ✅ Para TESTES (Sandbox)

```
ASAAS_URL=https://sandbox.asaas.com/api/v3
ASAAS_API_KEY=$aask_[sandbox-key]
```

**Características:**
- Pagamentos simulados
- Sem cobrança real
- Perfeito para desenvolvimento

### 🚀 Para PRODUÇÃO (Real)

```
ASAAS_URL=https://www.asaas.com/api/v3
ASAAS_API_KEY=$aact_[production-key]
```

**Características:**
- Pagamentos reais via PIX
- Cobrança efetiva
- Só use após validar conta Asaas

---

## 📋 Passo 5: Deploy

### Opção A: Deploy automático (recomendado)

1. Qualquer push para `main` no GitHub dispara deploy automático
2. Veja logs em **Render Dashboard → Logs**

### Opção B: Deploy manual

1. No Render Dashboard, clique em **Manual Deploy**
2. Selecione: **Deploy latest commit**

---

## ✅ Verificar se tudo está funcionando

Após deploypronunciar:

```bash
# Teste no navegador
https://seu-app-name.onrender.com/

# Teste a API Asaas
https://seu-app-name.onrender.com/teste-asaas

# Crie um pagamento (curl)
curl -X POST https://seu-app-name.onrender.com/criar-pagamento \
  -H "Content-Type: application/json" \
  -d '{
    "cnpj": "59353350000",
    "hwid": "37728284676517",
    "plano": "mensal"
  }'
```

---

## 📊 URLs importantes

| Recurso | URL |
|---------|-----|
| **Seu app** | `https://seu-app-name.onrender.com` |
| **Webhook Asaas** | `https://seu-app-name.onrender.com/webhook` |
| **Status pagamento** | `https://seu-app-name.onrender.com/status/<payment_id>` |
| **Obter licença** | `https://seu-app-name.onrender.com/obter-licenca` (POST) |
| **Consultar licença** | `https://seu-app-name.onrender.com/consulta-licenca?cnpj=X&hwid=Y` |

---

## 🛠️ Solução de problemas

### Erro 401 no Asaas
- **Causa**: API Key inválida ou expirada
- **Solução**: Verifique `ASAAS_API_KEY` no Render

### Pagamentos não chegam
- **Causa**: URL de webhook não configurada no Asaas
- **Solução**: 
  1. No painel Asaas, vá em **Integrações → Webhooks**
  2. Adicione: `https://seu-app-name.onrender.com/webhook`
  3. Evento: `PAYMENT_RECEIVED`

### Servidor cai constantemente
- **Causa**: Banco de dados corrompido ou memória insuficiente
- **Solução**: 
  1. Verifique logs no Render
  2. Considere usar PostgreSQL ao invés de SQLite (para produção)

---

## 🔄 Próximas melhorias

- [ ] Migrar SQLite → PostgreSQL
- [ ] Adicionar e-mail de confirmação
- [ ] Painel administrativo
- [ ] Renovação automática de licenças
- [ ] Integração com Discord/Telegram

---

## 📞 Suporte

Qualquer dúvida, consulte o README.md do projeto!
