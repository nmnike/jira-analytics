.PHONY: install dev run test lint migrate clean

# Install dependencies
install:
	pip install -r requirements.txt

# Development setup
dev: install
	cp -n .env.example .env || true
	mkdir -p data exports

# Run the application
run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
test:
	pytest tests/ -v

# Run linter
lint:
	ruff check app/ tests/
	mypy app/

# Format code
format:
	ruff format app/ tests/

# Create new migration
migration:
	alembic revision --autogenerate -m "$(msg)"

# Apply migrations
migrate:
	alembic upgrade head

# Downgrade one migration
downgrade:
	alembic downgrade -1

# Show migration history
history:
	alembic history

# Clean up
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf data/*.db

# Full reset (clean + migrate)
reset: clean migrate

# Help
help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make dev        - Development setup"
	@echo "  make run        - Run the application"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linter"
	@echo "  make format     - Format code"
	@echo "  make migrate    - Apply migrations"
	@echo "  make migration msg='description' - Create new migration"
	@echo "  make clean      - Clean up cache files"
	@echo "  make reset      - Clean and migrate"
