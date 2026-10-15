# Enterprise Scaling Architecture Guide (Ports & Adapters)

## 1. Architectural Philosophy: Ports & Adapters (Hexagonal Architecture)

The Hospital Bulk Processing System is built around **loose coupling** and **dependency inversion**. The core ingestion workflow, CSV validator, and API endpoints **never talk directly to concrete infrastructure implementations**. Instead, they interact with clean abstract interfaces (**Ports**).

By swapping the underlying **Adapters** via environment configuration, the application scales from single-node Standard Scale to a multi-replica, distributed Enterprise Scale with **zero code modifications**.

```mermaid
graph TD
    subgraph "Core Domain & Application Layer"
        BulkRoute[FastAPI /hospitals/bulk]
        Processor[BulkProcessor]
        Client[HospitalClient]
    end

    subgraph "Port: State Storage (BaseBatchRepository)"
        Processor --> RepoPort[BaseBatchRepository]
        RepoPort -.->|Standard Scale| MemAdapter[InMemoryBatchRepository]
        RepoPort -.->|Enterprise Scale| SqliteAdapter[PersistentSqliteBatchRepository]
        RepoPort -.->|Enterprise Scale| RedisAdapter[Postgres / Redis BatchRepository]
    end

    subgraph "Port: Real-Time Pub/Sub (BaseProgressBroadcaster)"
        Processor --> PubSubPort[BaseProgressBroadcaster]
        PubSubPort -.->|Standard Scale| LocalWS[InMemoryProgressBroadcaster]
        PubSubPort -.->|Enterprise Scale| ClusterWS[DistributedPubSubBroadcaster - Redis]
    end

    subgraph "Port: Rate Limiter (BaseRateLimiter)"
        Processor --> RatePort[BaseRateLimiter]
        RatePort -.->|Standard Scale| TokenBucket[TokenBucketRateLimiter]
        RatePort -.->|Enterprise Scale| DistributedLimiter[Redis Cluster Rate Limiter]
    end
```

---

## 2. Pluggable Ports & Adapters Matrix

| Architectural Port | Standard Scale Adapter | Enterprise Scale Adapter | How to Switch (Zero Code Changes) |
| :--- | :--- | :--- | :--- |
| **State Storage Port**<br>`BaseBatchRepository` | `InMemoryBatchRepository`<br>(Thread-safe, LRU cache) | `PersistentSqliteBatchRepository`<br>or PostgreSQL/Redis | Set `STORAGE_BACKEND=database`<br>and `DATABASE_URL=sqlite:///./batches.db` (or postgres) |
| **Pub/Sub Port**<br>`BaseProgressBroadcaster` | `InMemoryProgressBroadcaster`<br>(Local instance WebSockets) | `DistributedPubSubBroadcaster`<br>(Redis Pub/Sub topic) | Set `DISTRIBUTED_PUBSUB_ENABLED=true`<br>and `REDIS_URL=redis://...` |
| **Rate Limiter Port**<br>`BaseRateLimiter` | `TokenBucketRateLimiter`<br>(Local memory token bucket) | Distributed Redis Token Bucket | Configured via `GLOBAL_RATE_LIMIT_RPS=50` |
| **Task Queue Port**<br>`Execution Engine` | In-process `asyncio.Semaphore` | Distributed Task Queue (Celery / ARQ / Temporal) | Configured via `EXECUTION_ENGINE=distributed` |

---

## 3. Distributed Enterprise Deployment Topology

When scaled horizontally across multiple cloud compute nodes (e.g. AWS ECS, Kubernetes, GCP Cloud Run):

```mermaid
graph LR
    LB[Load Balancer / Ingress] --> Web1[FastAPI Web Node 1]
    LB --> Web2[FastAPI Web Node 2]
    LB --> WebN[FastAPI Web Node N]

    Web1 -->|State & Job Queue| Broker[(Redis / PostgreSQL Cluster)]
    Web2 -->|State & Job Queue| Broker
    WebN -->|State & Job Queue| Broker

    Broker --> Worker1[Background Worker 1]
    Broker --> Worker2[Background Worker 2]

    Worker1 -->|Outbound Bounded Concurrency| ExtAPI[Hospital Directory API]
    Worker2 -->|Outbound Bounded Concurrency| ExtAPI

    Broker -.->|PubSub Progress Events| Web1
    Broker -.->|PubSub Progress Events| Web2
```

### Why this design minimizes changes:
1. **No API Route Modifications**: `POST /hospitals/bulk`, `POST /hospitals/bulk/validate`, and `POST /hospitals/bulk/{batch_id}/resume` remain identical.
2. **WebSocket Continuity**: Because `BaseProgressBroadcaster` relays events through Redis, a client connected via WebSocket to `Web Node 1` receives updates even if the batch was processed on `Worker Node 2`.
3. **Upstream Directory Protection**: The `BaseRateLimiter` ensures that 50 worker containers coordinate and never exceed the maximum RPS of the upstream Render API.
4. **Zero-Loss Resilience**: In the event of a worker crash or node eviction, the durable `PersistentSqliteBatchRepository` / PostgreSQL preserves the batch state so the client can resume via `POST /hospitals/bulk/{batch_id}/resume` seamlessly.
