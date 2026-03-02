---
name: microservices
description: Microservices architecture with service discovery, messaging, and distributed patterns
version: 1.0.0
triggers:
  - microservices
  - micro services
  - service mesh
  - distributed
  - kafka
  - rabbitmq
  - grpc
  - kubernetes
  - docker compose
tags:
  - microservices
  - distributed
  - backend
  - kubernetes
  - multi-subsystem
composites:
  - backend-api
---

# Microservices Development

## Summary

Microservices architecture decomposes applications into independent services. Key challenges:

1. **Service boundaries** - What belongs in each service
2. **Communication** - Sync (HTTP/gRPC) vs async (messaging)
3. **Data consistency** - Distributed transactions, eventual consistency
4. **Observability** - Tracing, logging, metrics across services
5. **Deployment** - Independent deployability, versioning

**Project structure:**

```
microservices-app/
├── services/
│   ├── user-service/
│   │   ├── src/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   ├── order-service/
│   │   ├── src/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   └── notification-service/
│       ├── src/
│       ├── Dockerfile
│       └── pyproject.toml
├── shared/
│   ├── proto/              # gRPC definitions
│   └── events/             # Event schemas
├── infrastructure/
│   ├── docker-compose.yml
│   └── k8s/
├── gateway/                # API Gateway
└── docs/
    └── architecture.md
```

**Key principles:**
- Single responsibility per service
- Loose coupling, high cohesion
- Decentralized data management
- Design for failure

## Details

### Service Definition

**Basic service structure:**
```python
# services/user-service/src/main.py
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager

from .config import settings
from .database import init_db, close_db
from .routes import router
from .events import start_consumer, stop_consumer

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await start_consumer()
    yield
    # Shutdown
    await stop_consumer()
    await close_db()

app = FastAPI(
    title="User Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "user-service"}
```

**Service configuration:**
```python
# services/user-service/src/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    service_name: str = "user-service"
    database_url: str
    redis_url: str
    kafka_brokers: str = "kafka:9092"

    # Service discovery
    consul_host: str = "consul"
    consul_port: int = 8500

    # Other services
    order_service_url: str = "http://order-service:8000"

    class Config:
        env_file = ".env"

settings = Settings()
```

### Inter-Service Communication

**Synchronous (HTTP/REST):**
```python
# services/order-service/src/clients/user_client.py
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

class UserServiceClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=10.0)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def get_user(self, user_id: str) -> dict:
        response = await self.client.get(
            f"{self.base_url}/api/v1/users/{user_id}"
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()
```

**Synchronous (gRPC):**
```protobuf
// shared/proto/user.proto
syntax = "proto3";

package user;

service UserService {
    rpc GetUser(GetUserRequest) returns (User);
    rpc CreateUser(CreateUserRequest) returns (User);
}

message User {
    string id = 1;
    string email = 2;
    string name = 3;
}

message GetUserRequest {
    string user_id = 1;
}
```

**Asynchronous (Event-driven):**
```python
# services/user-service/src/events/publisher.py
from aiokafka import AIOKafkaProducer
import json

class EventPublisher:
    def __init__(self, brokers: str):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=brokers,
            value_serializer=lambda v: json.dumps(v).encode(),
        )

    async def publish(self, topic: str, event: dict):
        await self.producer.send_and_wait(topic, event)

    async def user_created(self, user: dict):
        await self.publish("user.created", {
            "event_type": "UserCreated",
            "data": user,
            "timestamp": datetime.utcnow().isoformat(),
        })
```

### Event Schemas

```python
# shared/events/user_events.py
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

@dataclass
class UserCreatedEvent:
    event_type: Literal["UserCreated"] = "UserCreated"
    user_id: str
    email: str
    name: str
    timestamp: datetime

@dataclass
class UserUpdatedEvent:
    event_type: Literal["UserUpdated"] = "UserUpdated"
    user_id: str
    changes: dict
    timestamp: datetime

# Event consumer
async def handle_user_created(event: UserCreatedEvent):
    # Notification service sends welcome email
    await send_welcome_email(event.email, event.name)
```

### Docker Compose Development

```yaml
# infrastructure/docker-compose.yml
version: '3.8'

services:
  user-service:
    build: ../services/user-service
    ports:
      - "8001:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@user-db:5432/users
      - KAFKA_BROKERS=kafka:9092
    depends_on:
      - user-db
      - kafka

  order-service:
    build: ../services/order-service
    ports:
      - "8002:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@order-db:5432/orders
      - USER_SERVICE_URL=http://user-service:8000
      - KAFKA_BROKERS=kafka:9092
    depends_on:
      - order-db
      - kafka
      - user-service

  notification-service:
    build: ../services/notification-service
    environment:
      - KAFKA_BROKERS=kafka:9092
      - SMTP_HOST=mailhog
    depends_on:
      - kafka
      - mailhog

  # Infrastructure
  user-db:
    image: postgres:15
    environment:
      POSTGRES_DB: users
      POSTGRES_PASSWORD: postgres

  order-db:
    image: postgres:15
    environment:
      POSTGRES_DB: orders
      POSTGRES_PASSWORD: postgres

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    environment:
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
    depends_on:
      - zookeeper

  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  mailhog:
    image: mailhog/mailhog
    ports:
      - "8025:8025"  # Web UI
```

### API Gateway

```python
# gateway/main.py
from fastapi import FastAPI, Request
import httpx

app = FastAPI(title="API Gateway")

ROUTES = {
    "/users": "http://user-service:8000",
    "/orders": "http://order-service:8000",
}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str):
    # Find target service
    for prefix, service_url in ROUTES.items():
        if path.startswith(prefix.lstrip("/")):
            target = f"{service_url}/{path}"
            break
    else:
        return {"error": "Route not found"}, 404

    # Forward request
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=target,
            headers=dict(request.headers),
            content=await request.body(),
        )

    return response.json()
```

## Advanced

### Distributed Tracing

```python
# shared/tracing.py
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def setup_tracing(service_name: str):
    provider = TracerProvider()
    processor = BatchSpanProcessor(JaegerExporter(
        agent_host_name="jaeger",
        agent_port=6831,
    ))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    return trace.get_tracer(service_name)

# Usage in service
tracer = setup_tracing("user-service")
FastAPIInstrumentor.instrument_app(app)

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    with tracer.start_as_current_span("get_user") as span:
        span.set_attribute("user_id", user_id)
        # ... fetch user
```

### Saga Pattern for Distributed Transactions

```python
# services/order-service/src/sagas/create_order.py
from dataclasses import dataclass
from typing import Callable, Awaitable

@dataclass
class SagaStep:
    name: str
    action: Callable[..., Awaitable]
    compensate: Callable[..., Awaitable]

class CreateOrderSaga:
    def __init__(self):
        self.steps = [
            SagaStep(
                name="reserve_inventory",
                action=self.reserve_inventory,
                compensate=self.release_inventory,
            ),
            SagaStep(
                name="charge_payment",
                action=self.charge_payment,
                compensate=self.refund_payment,
            ),
            SagaStep(
                name="create_order",
                action=self.create_order,
                compensate=self.cancel_order,
            ),
        ]

    async def execute(self, order_data: dict) -> dict:
        completed_steps = []

        try:
            for step in self.steps:
                await step.action(order_data)
                completed_steps.append(step)

            return {"status": "completed", "order": order_data}

        except Exception as e:
            # Compensate in reverse order
            for step in reversed(completed_steps):
                await step.compensate(order_data)

            return {"status": "failed", "error": str(e)}
```

### Service Mesh (Kubernetes)

```yaml
# infrastructure/k8s/user-service.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: user-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: user-service
  template:
    metadata:
      labels:
        app: user-service
    spec:
      containers:
        - name: user-service
          image: user-service:latest
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: user-service-secrets
                  key: database-url
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: user-service
spec:
  selector:
    app: user-service
  ports:
    - port: 8000
```

### Circuit Breaker

```python
# shared/resilience.py
from circuitbreaker import circuit

class CircuitOpenError(Exception):
    pass

@circuit(
    failure_threshold=5,
    recovery_timeout=30,
    expected_exception=Exception,
)
async def call_external_service(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=5.0)
        response.raise_for_status()
        return response.json()
```

## Agent Workflow

When working on microservices:

1. **Understand service boundaries**
   - Map service responsibilities
   - Identify shared contracts
   - Understand communication patterns

2. **Make changes with awareness of dependencies**
   - Update contracts/events first
   - Update producer services
   - Update consumer services
   - Update integration tests

3. **Validate cross-service behavior**
   - Run contract tests
   - Run integration tests with docker-compose
   - Verify event flows

```python
from reliable_ai.workspace import WorkspaceManager, ServiceMesh

# Agent workflow for microservices
workspace = WorkspaceManager(".")
mesh = ServiceMesh(workspace)

# 1. Understand service topology
topology = mesh.get_topology()
# Returns: services, dependencies, event flows

# 2. Plan changes across services
changes = mesh.plan_change("Add order cancellation")
# Returns: affected services, contracts, events

# 3. Execute with dependency order
for service, change in mesh.ordered_changes(changes):
    workspace.switch_context(service)
    # Make changes...
    mesh.validate_contracts(service)
```

## Resources

- [Microservices.io Patterns](https://microservices.io/patterns/)
- [Docker Compose Docs](https://docs.docker.com/compose/)
- [Kubernetes Docs](https://kubernetes.io/docs/)
- [Apache Kafka](https://kafka.apache.org/documentation/)
- [OpenTelemetry](https://opentelemetry.io/docs/)
