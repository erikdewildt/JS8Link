set dotenv-load := true

dev:
    @python3 scripts/dev.py

db-upgrade:
    cd backend && uv run alembic upgrade head

db-downgrade:
    cd backend && uv run alembic downgrade -1

db-revision message:
    cd backend && uv run alembic revision --autogenerate -m "{{message}}"

db-current:
    cd backend && uv run alembic current

db-history:
    cd backend && uv run alembic history

backend-lint:
    cd backend && uv run ruff check . && uv run pyright src/

backend-tests:
    cd backend && uv run pytest --cov=js8link --cov-report=term-missing --cov-report=html

backend-test: backend-lint backend-tests

frontend-lint:
    cd frontend && npm run lint && npm run format:check && npm run typecheck

frontend-build:
    cd frontend && npm run build

package:
    uv run --project backend python scripts/build-executable.py

package-fast:
    uv run --project backend python scripts/build-executable.py --skip-frontend-install

frontend-check: frontend-lint frontend-build

version-check:
    python3 scripts/version.py check

version-set version:
    python3 scripts/version.py set "{{version}}"

backend-test-fast:
    cd backend && uv run ruff check . && uv run pyright src/ && uv run pytest --cov=js8link --cov-report=term

frontend-tests:
    cd frontend && npm run test:unit

frontend-unit: frontend-tests

frontend-e2e:
    cd frontend && npm run test:e2e

check: version-check backend-lint frontend-lint
    @echo "✓ All checks passed"

test: version-check backend-tests frontend-tests frontend-e2e
    @echo "✓ All tests passed"
