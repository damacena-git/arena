# Setup: integração ClickUp

## Pré-requisitos
- Conta no ClickUp (funciona com conta pessoal ou workspace).
- API Key do ClickUp.
- ID do workspace/team (para casos onde o primeiro workspace automático não for o desejado).

## 1) Gerar a API Key no ClickUp
1. Abra o ClickUp e clique na sua foto no canto inferior esquerdo.
2. Vá em **Apps**.
3. Clique em **API**.
4. Em **API Token**, clique em **Generate** e copie o token.

Guardar esse token: ele é exibido apenas uma vez.

## 2) Descobrir o Workspace/Team ID
- Forma rápida: acesse **Settings > Workspaces**, clique no workspace e confira o ID na URL ou na seção **Team Info**.

## 3) Configurar no .env
Edite o arquivo `.env` na raiz do projeto e adicione/atualize:

```env
CLICKUP_API_KEY=<seu token aqui>
CLICKUP_TEAM_ID=<id do workspace aqui>
```

Reinicie o backend depois de salvar.

## 4) Habilitar o acesso no backend
Os endpoints do ClickUp ficam disponíveis quando `CLICKUP_API_KEY` está preenchida. A interface web consulta `/api/v1/integrations/clickup/status` e mostra **Conectado** quando tudo certo.

## 5) Testar
### Via HTTP (local)
```bash
curl http://localhost:8000/api/v1/integrations/clickup/status
curl http://localhost:8000/api/v1/integrations/clickup/workspaces
curl http://localhost:8000/api/v1/integrations/clickup/lists
```

### Via painel web
Acesse o painel web, entre em **Tarefas** e confira listas/tarefas.