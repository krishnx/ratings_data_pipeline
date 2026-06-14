.PHONY: lint format test-unit test-integration test-e2e test-perf test ci

lint:
	flake8 api/ tests/
	mypy api/

format:
	black api/ tests/
	isort api/ tests/

test-unit:
	pytest tests/unit/ -v --cov=api --cov-report=term-missing

test-integration:
	docker compose -f docker-compose.test.yml up -d postgres
	until docker compose -f docker-compose.test.yml exec -T postgres pg_isready -U ratings; do sleep 1; done
	TEST_DATABASE_URL="postgresql+psycopg://ratings:ratings@localhost:5432/ratings_test" \
	  pytest tests/integration/ -v

test-e2e:
	docker compose -f docker-compose.test.yml up --abort-on-container-exit --exit-code-from api

test-perf:
	pytest tests/performance/unit/ --benchmark-only --benchmark-compare
	pytest tests/performance/test_query_plans.py -v
	locust -f tests/performance/locustfile.py --config=tests/performance/locust.conf

test: test-unit test-integration

install:
	python3.13 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip setuptools wheel
	. .venv/bin/activate && python -m pip install -r api/requirements.txt || true
