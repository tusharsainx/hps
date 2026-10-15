# Hospital Bulk Processing System

A high-performance, asynchronous bulk processing system built with **FastAPI** and **HTTPX** that integrates with the external **Hospital Directory API** (`https://hospital-directory.onrender.com`).

It reliably handles multipart CSV file uploads, validates data formats and constraints, manages unique batch tracking IDs, executes concurrent creation requests with bounded rate-limiting and exponential backoff, and atomically activates batches.

---

## 🏗️ 1. Architecture & System Design

```mermaid
sequenceDiagram
    autonumber
    actor Client as Client / UI Dashboard
    participant API as FastAPI Ingestion Layer
    participant Val as CSV Validator Service
    participant Store as Batch State Repository
    participant Engine as Async Bulk Processor
    participant Upstream as Hospital Directory API (Render)

    Client->>API: POST /hospitals/bulk (CSV File)
    API->>Val: Validate CSV (Headers, Data Types, Max 20 Rows)
    alt Validation Failure
        Val-->>API: CsvValidationException (Row-level errors)
        API-->>Client: 422 Unprocessable Entity
    end
    Val-->>API: Validated Hospital Records
    API->>Store: Initialize Batch (UUID, Status: PROCESSING)
    API->>Engine: Dispatch Ingestion Tasks

    par Concurrent Upstream Calls (asyncio.Semaphore = 10)
        loop For each Hospital Record
            Engine->>Upstream: POST /hospitals/ (with creation_batch_id)
            alt Request Successful
                Upstream-->>Engine: 200 OK (id, active: false)
                Engine->>Store: Update Row Status (CREATED)
            else Transient Error (5xx / Timeout)
                Engine->>Engine: Retry with Exponential Backoff (up to 3x)
                Engine->>Store: Update Row Status (FAILED)
            end
        end
    end

    alt All Hospitals Created Successfully
        Engine->>Upstream: PATCH /hospitals/batch/{batch_id}/activate
        Upstream-->>Engine: 200 OK (activated_count)
        Engine->>Store: Mark Batch ACTIVATED (status: created_and_activated)
        API-->>Client: 200 OK (Full Batch Summary Response)
    else Any Row Failed
        Engine->>Store: Mark Batch PARTIALLY_FAILED
        API-->>Client: 200 OK (Response with failed_hospitals > 0, batch_activated: false)
    end
```

---

## 📐 2. Architecture & Design Principles

The codebase is built following clean architecture and **SOLID** design principles, keeping the system lightweight, thread-safe, and focused on the challenge requirements:

* **Separation of Concerns**: Ingestion, validation, upstream HTTP interaction, and state management are decoupled into dedicated service layers.
* **Thread-Safe In-Memory State**: `InMemoryBatchRepository` manages batch metadata, row items, and status transitions with a `threading.Lock` and bounded LRU eviction (configurable capacity) to prevent unbounded memory growth.
* **Dependency Injection**: Services (`BulkProcessor`, `HospitalClient`, `InMemoryBatchRepository`) are supplied via FastAPI dependency providers, enabling effortless unit testing and mocking.
* **Defensive Input Validation**: Streaming CSV parsing via `csv.DictReader` with strict column presence checking, whitespace normalization, BOM handling, and custom `CsvValidationException`.

---

## ⚡ 3. Key Performance & Resilience Features

1. **Bounded Concurrency**: Uses `asyncio.Semaphore(10)` to throttle outbound HTTP calls, preventing downstream 429 rate-limits while achieving **< 1.0s processing time** for 20 records (a **~7x speedup** over naive sequential execution).
2. **HTTP Keep-Alive Connection Pooling**: Configured with `httpx.Limits(max_connections=50, max_keepalive_connections=20)` to reuse TLS/TCP handshakes across concurrent calls.
3. **Exponential Backoff with Full Jitter**: Resilient retry loop (`delay = base * 2^(attempt-1) + jitter`) for transient 502/503/504 errors and network drops. Does not waste retries on 4xx client errors.
4. **Atomic Batch Activation**: Calls `PATCH /hospitals/batch/{batch_id}/activate` strictly when all hospital records in the batch have been verified and created. If any record fails, the batch remains unactivated.
5. **No 413 Payload Too Large Errors**: Uploaded CSV files are inspected directly by the application validator, enforcing the 20-row limit and header schema with standard `400`/`422` validation diagnostics.

---

## 🎁 4. Optional Tasks & Bonus Features Implemented

* **Performance Optimization**: Bounded async execution, keep-alive pooling, and retry backoff.
* **Progress Tracking**: Real-time batch inspection and progress tracking via polling endpoint (`GET /hospitals/bulk/{batch_id}`) and listing endpoint (`GET /hospitals/bulk`).
* **Resume Capability**: `POST /hospitals/bulk/{batch_id}/resume` checks which records already exist upstream, skips completed records, retries failed ones, and activates the batch.
* **Standalone CSV Validation**: `POST /hospitals/bulk/validate` inspects syntax, column headers, empty fields, and row counts before executing bulk operations.
* **Batch Rollback**: `DELETE /hospitals/bulk/{batch_id}` cleans up batches from the upstream directory.
* **Dockerization**: Production-ready multi-stage `Dockerfile` and `docker-compose.yml`.
* **Interactive Web Dashboard**: Modern UI mounted at `/` for testing CSV uploads, polling progress bars, inspecting row states, and testing resumption.

---

## 📡 5. API Reference

### 1. Bulk Create Hospitals
* **Endpoint**: `POST /hospitals/bulk`
* **Content-Type**: `multipart/form-data`
* **Form Field**: `file` (CSV file with columns: `name,address,phone`)
* **Execution**: Asynchronous concurrent non-blocking execution by default (`asyncio.Semaphore(10)`)

#### Example Request:
```bash
curl -X POST "http://localhost:8000/hospitals/bulk" \
  -F "file=@sample_data/valid_hospitals_5.csv"
```

#### Example Response (200 OK):
```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_hospitals": 5,
  "processed_hospitals": 5,
  "failed_hospitals": 0,
  "processing_time_seconds": 1.25,
  "batch_activated": true,
  "hospitals": [
    {
      "row": 1,
      "hospital_id": 101,
      "name": "St. Jude Children's Research Hospital",
      "status": "created_and_activated",
      "error": null
    },
    {
      "row": 2,
      "hospital_id": 102,
      "name": "Mayo Clinic Hospital",
      "status": "created_and_activated",
      "error": null
    }
  ]
}
```

---

### 2. Pre-Validate CSV (Bonus)
* **Endpoint**: `POST /hospitals/bulk/validate`
* **Content-Type**: `multipart/form-data`

```bash
curl -X POST "http://localhost:8000/hospitals/bulk/validate" \
  -F "file=@sample_data/invalid_exceed_limit_25.csv"
```

#### Example Response:
```json
{
  "valid": false,
  "total_rows": 25,
  "errors": [
    {
      "row": null,
      "column": null,
      "message": "CSV contains 25 hospital rows, which exceeds the maximum allowed limit of 20 hospitals per batch."
    }
  ],
  "message": "Validation failed with 1 error(s)."
}
```

---

### 3. Resume Failed Batch (Bonus)
* **Endpoint**: `POST /hospitals/bulk/{batch_id}/resume`

```bash
curl -X POST "http://localhost:8000/hospitals/bulk/550e8400-e29b-41d4-a716-446655440000/resume"
```

---

### 4. Poll Batch Progress & Status
* **Endpoint**: `GET /hospitals/bulk/{batch_id}`

```bash
curl "http://localhost:8000/hospitals/bulk/550e8400-e29b-41d4-a716-446655440000"
```

---

### 5. List Historical Batches
* **Endpoint**: `GET /hospitals/bulk`

```bash
curl "http://localhost:8000/hospitals/bulk"
```

---

## 🚀 6. Getting Started

### Local Development Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd paribus-hps

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start local development server
uvicorn app.main:app --reload --port 8000
```

Access the interactive dashboard at **`http://localhost:8000`** and Swagger OpenAPI documentation at **`http://localhost:8000/docs`**.

---

### Docker & Docker Compose

Run the entire application in a container with a single command:

```bash
# Using Docker Compose
docker compose up --build

# Or build and run standalone Docker container
docker build -t paribus-hps .
docker run -p 8000:8000 -e PORT=8000 paribus-hps
```

---

## 🧪 7. Running Tests

The test suite covers unit tests, mocked integration tests, and live upstream tests:

```bash
# Run all unit and mock integration tests
pytest -v

# Run with test coverage report
pytest --cov=app --cov-report=term-missing

# Run live integration test against the deployed Render Hospital Directory API
pytest -v -m live
```

---

## 🌐 8. Deployment to Render

The repository includes a ready-to-use [`render.yaml`](render.yaml) blueprint:

1. Push your repository to GitHub or GitLab.
2. In the Render Dashboard, click **New +** → **Blueprint**.
3. Select your repository. Render will automatically detect `render.yaml` and configure:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health check path: `/health`
4. Click **Deploy**. Your service will be live in ~2 minutes!

---

## 🚀 9. Future Production Scaling Architecture (Enterprise & Big Data Scale)

For enterprise scale, multi-gigabyte CSV files (millions of records), or high-concurrency multi-tenant workloads, the architecture evolves from direct multipart ingestion to a **decoupled, event-driven cloud pipeline**:

```mermaid
sequenceDiagram
    autonumber
    actor Client as Client / Web App
    participant API as FastAPI Gateway
    participant S3 as Amazon S3 / Cloud Storage
    participant Queue as SQS Queue / EventBridge
    participant Workers as Distributed Worker Fleet (Celery / ECS)
    participant Upstream as External Hospital Directory API
    participant DB as Persistent State Store (Postgres / Redis)

    Client->>API: 1. Request Upload URL (POST /hospitals/bulk/upload-url)
    API-->>Client: 2. Return S3 Pre-signed URL + batch_id
    Client->>S3: 3. Direct Upload CSV via Pre-signed URL (bypasses API server)
    S3->>Queue: 4. Emit s3:ObjectCreated Event
    Queue->>Workers: 5. Worker consumes event (bucket, object_key, batch_id)
    Workers->>S3: 6. Stream CSV chunk-by-chunk (generator / chunked parsing)
    Workers->>DB: 7. Validate & persist batch state (status: PROCESSING)
    Workers->>Upstream: 8. Execute concurrent creation with distributed rate-limiting
    alt All rows created
        Workers->>Upstream: 9. Atomic PATCH /hospitals/batch/{batch_id}/activate
        Workers->>DB: 10. Update status: ACTIVATED
    else Partial failure
        Workers->>DB: 10. Update status: PARTIALLY_FAILED (allows resume)
    end
    Client->>API: 11. Poll status: GET /hospitals/bulk/{batch_id}
    API->>DB: 12. Read batch progress
    API-->>Client: 13. Progress summary & row items
```

### Key Architectural Pillars for Scale:

1. **Direct-to-S3 Upload via Pre-signed URLs**:
   - Instead of routing massive CSV payloads through the FastAPI application server (which exhausts server memory and ties up HTTP worker threads), the client requests a short-lived **Pre-signed PUT/POST URL** from the backend.
   - The file streams directly from the client's browser/CLI to **Amazon S3** (or Google Cloud Storage / Azure Blob Storage).

2. **Event-Driven Decoupling (`s3:ObjectCreated`)**:
   - Once the upload completes, S3 automatically triggers an **`s3:ObjectCreated`** event notification.
   - The event routes into an **Amazon SQS** queue (or AWS EventBridge / Apache Kafka topic), completely decoupling file ingestion from processing.

3. **Autonomous Worker Fleet & Memory-Efficient Streaming**:
   - Background worker processes (e.g., Celery, ARQ, Temporal, or AWS ECS/Fargate tasks) consume tasks from the queue.
   - Workers download and stream the CSV **chunk-by-chunk** using generator-based chunked readers (or Polars/PyArrow streaming), processing files of arbitrary size with constant, low RAM usage (`O(1)` memory).

4. **Durable Persistence & Distributed Throttling**:
   - Batch progress and row states are written to a durable database (**PostgreSQL / DynamoDB**).
   - Upstream API rate limits are enforced across multi-node worker clusters using a **distributed Redis token-bucket rate limiter** to prevent downstream 429 errors.

