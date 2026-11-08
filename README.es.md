# WhatsApp AI Agent

**Idiomas:** [English (principal)](README.md) | [Português](README.pt-BR.md) | Español

Asistente de atención ficticia con **Python, FastAPI, SQLAlchemy, Alembic, httpx y adaptador oficial de Meta WhatsApp Cloud API**. Incluye demostración local sin costo, catálogo de servicios, herramientas de lectura, solicitudes de citas con confirmación explícita, transferencia a un operador y adaptador LLM opcional.

**Importante:** el chat local **no está conectado a WhatsApp**. La integración oficial está implementada y probada mediante mocks, pero **no ha sido validada con una cuenta real**. El envío real permanece desactivado por defecto.

## Inicio rápido

Requiere Python 3.12+ (la CI también incluye 3.14):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn whatsapp_ai_agent.api:app --host 127.0.0.1 --port 8000
```

Abre **http://127.0.0.1:8000/demo** para la simulación o **/docs** para OpenAPI. En Windows: `.venv\\Scripts\\activate` y `copy .env.example .env`.

Prueba `services`, `hours`, `availability`, `book consultation YYYY-MM-DD 10:00`, `CONFIRM`, `NO`, `HUMAN` y `STOP`. Todos los servicios, precios, horarios y direcciones del catálogo son ficticios. Una cita se registra solo después de la confirmación explícita; una cancelación exige aprobación administrativa de un solo uso. Las citas bloquean todos los intervalos de su duración.

## Componentes

- Webhook oficial `GET/POST /webhooks/whatsapp`, validación del desafío, HMAC-SHA256 del cuerpo original, eventos y estados.
- Cliente oficial Graph API con httpx, timeouts controlados y envíos desactivados.
- Persistencia SQLAlchemy (SQLite o PostgreSQL) y migraciones Alembic.
- Herramientas `list_services`, `get_service_details`, `get_business_hours`, `get_business_information`, `search_faq` y disponibilidad demostrativa.
- Motor determinista gratuito; modelo compatible con tool calling opcional y **solo de lectura**.
- Transferencia humana, opt-out, límite de mensajes por contacto, autenticación simple para las APIs administrativas y registro de herramientas. El operador autenticado consulta `/admin/conversations/{id}`.
- Pruebas pytest y GitHub Actions en runners alojados, sin acceso a APIs de pago, más de 20 escenarios de evaluación.

## Integración opcional y política

Configura `WEBHOOK_VERIFY_TOKEN`, `META_APP_SECRET`, `META_ACCESS_TOKEN`, `META_PHONE_NUMBER_ID` y `META_GRAPH_VERSION`. Activa `ENABLE_REAL_SEND=true` **solo tras la autorización expresa** y la verificación de requisitos de Meta. No se crea una conexión externa ni se publica una aplicación automáticamente. No se incluyen plantillas aprobadas para mensajes fuera de la ventana de servicio.

## Validación

```bash
ruff check .
ruff format --check .
pytest -q
python -m evals.run
docker build -t whatsapp-ai-agent .
```

Para las operaciones administrativas, suministra `X-Admin-API-Key`. No incluyas datos reales en ejemplos.

**Limitaciones:** sin validación en vivo con Meta, sin cola saliente duradera, sin soporte de plantillas, sin panel completo del operador, sin rate limit distribuido, sin limpieza programada por retención (existe `/admin/purge-history` con autenticación) y sin evaluación jurídica de protección de datos. Las citas usan espacios ficticios únicos.

Más detalles: [arquitectura](docs/architecture.md), [seguridad](docs/security.md) y [decisiones](docs/decisions.md).

**Licencia:** [MIT](LICENSE), © 2026 Ramon Rodriguez.
