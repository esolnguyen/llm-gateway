# llm-wrapper

Event-driven LLM and OCR provider integrations with Postgres-backed credential
management and automatic cost tracking.

## Architecture

```
          ┌────────────────────────────────────────┐
          │                src/                    │
          │                                        │
          │  shared/        ← db + event bus       │
          │                                        │
          │  providers/   ──── publishes ────┐     │
          │  ┌ credentials/                  │     │
          │  ┌ llm/ (+ backends)             ▼     │
          │  └ ocr/ (+ backends)        event bus  │
          │                                  │     │
          │  costs/       ←──── subscribes ──┘     │
          │  ┌ pricing/                            │
          │  ┌ handlers                            │
          │  └ repository                          │
          └────────────────────────────────────────┘
                             │
                             ▼
                         PostgreSQL
```

**Data flow**

1. `LLMService.call_llm(model_name, prompt)` looks up the credential for
   `model_name` from `model_credentials` (decrypted via `pgp_sym_decrypt`,
   cached in-process for 5 minutes).
2. The provider backend is invoked with the decrypted credential.
3. On success, an `LLMResponseEvent` is published to the event bus.
4. `costs.handlers.CostEventHandler` consumes the event, calculates cost via
   `model_pricing`, and persists a row to `cost_events`.

The default `InMemoryEventBus` is an asyncio fan-out — swap it for a
broker-backed bus (Redis Streams / SQS / EventBridge) by calling
`shared.events.bus.set_event_bus()` at startup without touching any caller.

## Layout

```
src/
├── shared/
│   ├── config.py          # Settings (DATABASE_URL, encryption key)
│   ├── db/                # Async SQLAlchemy engine/session, Base
│   └── events/            # EventBus interface + InMemoryEventBus, event types
├── providers/
│   ├── credentials/       # model_credentials table + repository (TTL cache)
│   ├── llm/
│   │   ├── service.py     # LLMService: credential → backend → emit event
│   │   ├── factory.py
│   │   └── backends/      # gemini, azure_openai
│   └── ocr/
│       ├── service.py     # OCRService
│       ├── factory.py
│       └── backends/      # Azure Document Intelligence
└── costs/
    ├── schema.py          # model_pricing, cost_events tables
    ├── pricing/           # PricingRepository + CostCalculator
    ├── handlers.py        # CostEventHandler
    ├── repository.py      # CostEventRepository
    └── bootstrap.py       # register_cost_handlers()
```

## Setup

1. **Provision Postgres** and apply the schema:

   ```bash
   psql "$DATABASE_URL" -f sql/init.sql
   ```

2. **Seed a credential** (encrypting at write time):

   ```sql
   INSERT INTO model_credentials (provider, model_name, api_key_enc)
   VALUES (
     'google',
     'gemini-2.0-flash',
     pgp_sym_encrypt('YOUR_GEMINI_API_KEY', 'same-key-as-CREDENTIAL_ENCRYPTION_KEY')
   );
   ```

3. **Seed pricing**:

   ```sql
   INSERT INTO model_pricing (model_name, capability, unit_type, price_per_unit, effective_from)
   VALUES
     ('gemini-2.0-flash', 'chat', 'input_tokens',  0.0000001, now()),
     ('gemini-2.0-flash', 'chat', 'output_tokens', 0.0000004, now());
   ```

4. **Configure environment** — copy `.env.example` to `.env` and fill in
   `DATABASE_URL` and `CREDENTIAL_ENCRYPTION_KEY`.

5. **Install**:

   ```bash
   pip install -e ".[dev]"
   ```

## Usage

```python
import asyncio

from costs import register_cost_handlers
from providers import LLMService, OrganisationInfo, UserInfo
from providers.models import AzureGenerateContentConfig


async def main() -> None:
    register_cost_handlers()  # wire costs into the event bus once at startup

    service = LLMService(
        module_name="MyModule",
        service_name="chat",
        user_info=UserInfo(id="u-1", email="a@b.com", status="active"),
        organisation_info=OrganisationInfo(
            id="org-1", name="Acme", status="active", type="enterprise"
        ),
    )

    response = await service.call_llm(
        model_name="gemini-2.0-flash",
        prompt="Summarise the key ideas in event-driven architectures.",
    )
    print(response.content)
    print(f"{response.input_tokens} in / {response.output_tokens} out")


asyncio.run(main())
```

The LLM call returns synchronously; cost calculation runs as a background
task on the bus, so a slow pricing DB never blocks the caller.

## Replacing the event bus

```python
from shared.events.bus import set_event_bus
from my_adapters.sqs_bus import SqsEventBus

set_event_bus(SqsEventBus(queue_url="..."))  # call before register_cost_handlers()
```

Any `EventBus` subclass that implements `publish(topic, event)` and
`subscribe(topic, handler)` will work.

## Development

```bash
pip install -e ".[dev]"
pytest
```
