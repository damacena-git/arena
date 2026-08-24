# Decisões técnicas — Sofia

## Stack inicial

| Camada | Decisão |
|---|---|
| Backend | Python + FastAPI |
| Worker | Python separado, consumindo Redis |
| Frontend | React + Vite |
| Banco | PostgreSQL + pgvector |
| Filas e agendamento | Redis |
| Arquivos | Minio |
| Entrada HTTPS | Traefik |
| IA | Adaptador comum para Groq e OpenRouter |
| Integração WhatsApp | Evolution API |

## Organização local sugerida

```text
sofia/
├── apps/
│   ├── api/       # FastAPI, webhooks, autenticação e casos de uso
│   ├── worker/    # jobs, retries e integrações assíncronas
│   └── web/       # React/Vite
├── packages/
│   ├── domain/    # entidades, políticas e contratos
│   └── clients/   # clientes ClickUp, Notion, Google, Fathom e IA
├── infra/
│   ├── docker-compose.yml
│   └── traefik/
├── migrations/
├── .env.example
└── README.md
```

A implementação pode começar como um monorepo e um monólito modular; a separação em `api`, `worker`, `domain` e `clients` evita acoplamento sem introduzir microserviços prematuramente.

## URLs por ambiente

### Local

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- Documentação: `http://localhost:8000/docs`
- Webhooks: `http://localhost:8000/webhooks/*`

Em desenvolvimento, o Vite deve usar proxy para `/api`, e o browser nunca deve chamar `localhost` de outro serviço por URL fixa. Para testar webhooks localmente, usar um túnel HTTPS temporário ou configurar a Evolution API para alcançar a máquina de desenvolvimento.

### Produção

- Chat: `https://sofia.2ads.com.br`
- API: `https://api.sofia.2ads.com.br`
- Webhooks: `https://hooks.sofia.2ads.com.br`

O Traefik deve rotear os três hosts para os serviços corretos e emitir/renovar certificados. As URLs de OAuth e webhooks devem ser configuráveis, nunca codificadas no código.

## Contratos importantes

### Mensagem recebida

Normalizar mensagens da Evolution API e do chat web para um evento interno comum contendo:

- `source`: `whatsapp` ou `web`;
- `external_message_id`;
- `conversation_id`;
- `sender_id`;
- `text` e anexos opcionais;
- `received_at` com timezone;
- payload original armazenado de forma controlada para diagnóstico.

### Ferramentas da IA

A IA não chama APIs externas diretamente. Ela produz uma chamada de ferramenta tipada; o backend valida, aplica autorização e confirmação, e o worker executa. Toda ferramenta deve declarar:

- nome e finalidade;
- parâmetros e validação;
- nível de risco;
- necessidade de confirmação;
- estratégia de idempotência;
- resultado sanitizado para o modelo e para o usuário.

## Primeiros módulos da Fase 1

1. configuração por ambiente e health checks;
2. schema inicial Postgres e migrations;
3. webhook normalizado da Evolution API;
4. persistência de conversas e mensagens;
5. endpoint de chat web;
6. adaptador Groq/OpenRouter com resposta textual;
7. fila Redis e worker mínimo;
8. confirmação e auditoria antes das integrações externas.

## Nota sobre monitoramento do WhatsApp

A intenção é analisar todas as conversas, mas a aplicação deve possuir desde o primeiro desenho:

- configuração explícita de conversas monitoradas;
- botão/comando global de pausa;
- retenção e exclusão por conversa;
- trilha de auditoria;
- tratamento especial para grupos e dados de terceiros.

Isso evita que uma configuração inicial ampla se transforme em coleta sem controle.
