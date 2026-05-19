# Sanchar Mitra — Debit Service

This is a standalone backend service that processes wallet adjustments (debits) for Sanchar Mitra services via the Pyro API. Currently, it supports **FancySale**, with architecture in place to support **SimSwap** and **ESIM** in the future.

## Architecture & Data Flow

The service operates primarily via a background scheduler that executes the following loop:
1. **Fetch**: Reads eligible records from the Oracle database (e.g., `CAF_ADMIN.VANITYSALE_FRANCH_DATA` for FancySale) where `CAF_ENTRY_DONE IN ('N', 'QM', 'QB')`.
2. **Claim**: Marks the rows as `P` (Processing) atomically to prevent duplicate processing.
3. **Submit**: Calls the Pyro API (`/erp-stock-api/service-wallet-adjustment`) with the decrypted MPIN and transaction details.
4. **Writeback**: Updates the Oracle database with the result (`Y` for Success, `R` for Rejected).
5. **Audit Log**: Records the full transaction lifecycle to a PostgreSQL database (`debit_txn_log`) for monitoring and auditing.

## Prerequisites

- **Python 3.10+** (if running locally)
- **Docker & Docker Compose** (if running via containers)
- Access to the **Oracle Database** (for CAF tables)
- Access to the **PostgreSQL Database** (for audit logs)
- Valid credentials for the **Pyro API**

## Configuration

Configuration is managed via environment variables. Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

### Key Environment Variables:
- `PYRO_BASE_URL`: Base URL for the Pyro API.
- `ORACLE_*`: Credentials for the Oracle DB containing the CAF tables.
- `PG_*`: Credentials for the PostgreSQL DB for transaction logging.
- `FANCYSALE_*`: Service-specific credentials (API Key, Login ID, Password, Secret Key) and scheduler settings (`FANCYSALE_INTERVAL_MINUTES`, `FANCYSALE_BATCH_SIZE`).
- `ADMIN_API_KEY`: A secret string required to access the `/admin/*` endpoints.

## Running the Service

### Using Docker (Recommended for Production)

```bash
# Build and run in detached mode
docker-compose up -d --build

# For production (uses pre-built images):
docker-compose -f docker-compose-prod.yml up -d
```
*Note: The application exposes port `8010` by default.*

### Running Locally (Development)

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Start the server:
   ```bash
   uvicorn main:app --host 127.0.0.1 --port 8010
   ```

## API Endpoints

The service provides several REST endpoints for monitoring and administration.

### Health & Readiness
- `GET /health`: Basic health check. Returns `{"status": "ok"}`.
- `GET /ready`: Checks database connection pools (Oracle and Postgres) and scheduler status.

### Debit Status & Administration
*Note: All `/admin/*` endpoints require the `x-api-key` header to match your `ADMIN_API_KEY` environment variable.*

- `GET /debit/status`: Returns the current authentication token status for all debit services and their configuration settings.
- `POST /admin/trigger-debit/{service_type}`: Manually triggers a debit batch for a specific service (e.g., `FANCYSALE`).
- `POST /admin/reset-stuck-debit/{service_type}?stuck_minutes=10`: Emergency endpoint to reset records stuck in the `P` (Processing) state back to `N` so they can be retried.

## Scheduler Jobs

When `ENABLE_SCHEDULER=true`, the following background jobs run automatically:
- **Debit Batch Processing**: Runs every `FANCYSALE_INTERVAL_MINUTES` to process new transactions.
- **Stuck Record Cleanup**: Runs every 15 minutes to automatically reset any rows stuck in `P` state beyond the configured threshold (`FANCYSALE_STUCK_MINUTES`).
- **Daily Re-auth**: Runs at 00:10 daily to refresh Pyro authentication tokens for all enabled debit services.
