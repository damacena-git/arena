# Checklist para subir os serviços

## 1) Backend
- Configure `.env` com as chaves necessárias.
- Instale dependências do projeto se for a primeira vez local.
- Inicie a API.
- Confirme `/health` e `/api/v1/config`.
- Confirme `/api/v1/integrations/clickup/status`.
- Teste `/api/v1/integrations/clickup/lists` e `/api/v1/integrations/clickup/tasks`.

## 2) Frontend
- Instale dependências: `npm run install:web`.
- Rode o app: `npm run dev`.
- Acesse o painel e navegue por chat, tarefas ClickUp e configuração.
- Se for build local: `npm run build` e `npm run preview`.

## 3) Validação rápida
- Crie uma tarefa pelo painel ClickUp.
- Envie uma mensagem de texto no chat.
- Envie um áudio pequeno para validar transcrição e áudio (fora do MVP de produção).

## 4) Deploy quando disponível
- Garanta que as variáveis de ambiente estão injetadas no ambiente/aplicação.
- Verifique CORS e DNS conforme o ambiente (apontando para domínio configurado, ex: `sofia.2ads.com.br`).
- Confirme HTTPS e Traefik, antes de expor webhooks para Evoluction API e Fathom.