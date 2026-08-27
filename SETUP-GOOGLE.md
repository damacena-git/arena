# Correção rápida: redirect_uri_mismatch (Google OAuth)

Erro encontrado: `400 redirect_uri_mismatch`.

Causa: a URI de redirecionamento usada pela aplicação não está autorizada no Google Cloud Console.

## 1) Verificar a URI atual
No arquivo `.env`, confira o valor de `GOOGLE_REDIRECT_URI`:
```
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/integrations/google/callback
```
Copie exatamente esse valor.

## 2) Registrar no Google Cloud Console
1. Abra https://console.cloud.google.com/apis/credentials
2. Selecione o **OAuth 2.0 Client ID** usado pelo projeto.
3. Em **Authorized redirect URIs**, clique em **Add URI**.
4. Cole:
   ```
   http://localhost:8000/api/v1/integrations/google/callback
   ```
5. Clique em **Save**.

## 3) Testar novamente
Reinicie a API e acesse:
```
GET http://localhost:8000/api/v1/integrations/google/start
```

## 4) Produção
Quando for para produção, adicione também a URI de produção:
```
https://sofia.2ads.com.br/api/v1/integrations/google/callback
```