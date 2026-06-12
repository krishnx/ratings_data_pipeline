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
	pytest tests/integration/ -v

test-e2e:
	docker-compose -f docker-compose.test.yml up --abort-on-container-exit --exit-code-from api

test-perf:
	pytest tests/performance/unit/ --benchmark-only --benchmark-compare
	pytest tests/performance/test_query_plans.py -v
	locust -f tests/performance/locustfile.py --config=tests/performance/locust.conf

test: test-unit test-integration

install:
	python3.13 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip setuptools wheel
	. .venv/bin/activate && python -m pip install -r api/requirements.txt || true
