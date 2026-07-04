# DocuMind PostgreSQL Development Setup

This package contains:

- `docker-compose.yml` - PostgreSQL + PgBouncer, no pgAdmin.
- `.env.example` - example environment variables.
- `schema.sql` - final PostgreSQL schema.
- `scripts/apply_schema.sh` - applies `schema.sql`.
- `scripts/drop_public_schema.sh` - deletes everything inside the `public` schema.
- `scripts/reset_schema.sh` - drops the public schema and applies `schema.sql` again.
- `.github/workflows/postgres-schema-ci.yml` - GitHub Actions workflow that validates the schema.

## Local usage

```bash
cp .env.example .env
# edit .env and set strong passwords

docker compose up -d

sudo apt update
sudo apt install -y postgresql-client

bash scripts/apply_schema.sh
```

## Reset during development

```bash
bash scripts/reset_schema.sh
```

You must type `RESET` to confirm.


## Connect in terminal
```bash
set -a
source .env
set +a

psql "postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${PG_PORT}/${POSTGRES_DB}"
```

## Runtime app connection

For your backend app, connect through PgBouncer:

```text
Host: localhost
Port: 6433
Database: documind_postgresql
User: documind
Password: from .env
```

For schema/migrations, connect directly to PostgreSQL:

```text
Host: localhost
Port: 5433
Database: documind_postgresql
User: documind
Password: from .env
```
