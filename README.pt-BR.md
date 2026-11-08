# WhatsApp AI Agent

**Idiomas:** [English (principal)](README.md) | Português | [Español](README.es.md)

Agente demonstrativo de atendimento por mensagens, construído com **Python, FastAPI, SQLAlchemy, Alembic, httpx e Meta WhatsApp Cloud API**. Inclui simulação local gratuita, catálogo fictício, consultas de serviços, ferramentas de leitura, agendamento com confirmação explícita, encaminhamento humano e adaptador opcional de LLM.

**Atenção:** a tela local **não é WhatsApp real**. A integração Meta foi implementada e coberta por mocks, mas **não validada com credenciais reais**. Nenhuma mensagem real é enviada por padrão.

## Executar

Requer Python 3.12+ (testes de CI também incluem 3.14):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn whatsapp_ai_agent.api:app --host 127.0.0.1 --port 8000
```

Acesse **http://127.0.0.1:8000/demo** (simulação) e **/docs** (OpenAPI). No Windows, use `.venv\\Scripts\\activate` e `copy .env.example .env`.

Exemplos: `services`, `hours`, `availability`, `book consultation AAAA-MM-DD 10:00`, `CONFIRM`, `NO`, `HUMAN`, `STOP`. Serviços, endereço, preços e disponibilidade são inteiramente fictícios. A confirmação só registra o agendamento demonstrativo após resposta explícita. Cancelamentos exigem encaminhamento humano e autorização administrativa de uso único. Os agendamentos bloqueiam todos os intervalos cobertos pela duração do serviço.

## Arquitetura e funções

- Webhook oficial `GET/POST /webhooks/whatsapp`: desafio de validação, HMAC-SHA256 sobre bytes originais, payloads, mensagens e status.
- Cliente httpx para Graph API, com envio real bloqueado, controle de timeout e janela de atendimento.
- Contatos pseudonimizados, conversas, mensagens, serviços, agendamentos, handoff e auditoria no SQLAlchemy.
- `list_services`, `get_service_details`, `get_business_hours`, `get_business_information`, `search_faq` e disponibilidade fictícia.
- Adaptador de LLM compatível com tool calling, limitado a ferramentas de leitura. Modo determinístico sem custos é o padrão.
- APIs administrativas protegidas por chave; a tela de demonstração só é disponibilizada no modo local. O operador autenticado consulta `/admin/conversations/{id}`.
- GitHub Actions com pytest, Ruff, migrações, empacotamento e build Docker, sem APIs pagas nem mensagens reais.
- Mais de 20 cenários fictícios de avaliação em `evals/scenarios.json`.

## Integração Meta opcional

Configure as variáveis `WEBHOOK_VERIFY_TOKEN`, `META_APP_SECRET`, `META_ACCESS_TOKEN`, `META_PHONE_NUMBER_ID` e a versão compatível `META_GRAPH_VERSION`. Apenas com autorização e verificação das políticas, altere `ENABLE_REAL_SEND=true`. Hospedagem HTTPS, assinatura da conta e configuração da Meta não são realizadas automaticamente. Fora da janela de atendimento, não há suporte de templates nesta versão.

## Testes

```bash
ruff check .
ruff format --check .
pytest -q
python -m evals.run
docker build -t whatsapp-ai-agent .
```

A chave administrativa é enviada no cabeçalho `X-Admin-API-Key` para `/demo/reset`, `/admin/handoffs`, `/admin/handoffs/{id}/resume` e `/admin/appointments`. Não exponha a chave nem use dados pessoais em demonstrações.

**Limitações:** ainda não validado com a API real; sem filas duráveis de saída, templates, interface profissional de operadores, rate limit distribuído, agendamento automático de limpeza por retenção (existe rota administrativa `/admin/purge-history`) ou revisão jurídica LGPD. O agendamento é fictício, de slot único; não é uma agenda comercial. Leia [arquitetura](docs/architecture.md) e [segurança](docs/security.md).

**Licença:** [MIT](LICENSE), © 2026 Ramon Rodriguez.
