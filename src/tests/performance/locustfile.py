"""
Three user personas for load testing.
Run: locust -f tests/performance/locustfile.py --config=tests/performance/locust.conf
"""
import random

from locust import HttpUser, between, task


class AnalystUser(HttpUser):
    """Analyst — read-heavy, 60% of traffic."""
    weight = 6
    wait_time = between(0.5, 2)
    company_ids: list[int] = []

    def on_start(self):
        r = self.client.get("/companies")
        if r.status_code == 200:
            self.company_ids = [c["company_id"] for c in r.json()]

    @task(3)
    def list_companies(self):
        self.client.get("/companies")

    @task(3)
    def get_company(self):
        if self.company_ids:
            cid = random.choice(self.company_ids)
            self.client.get(f"/companies/{cid}")

    @task(2)
    def company_history(self):
        if self.company_ids:
            cid = random.choice(self.company_ids)
            self.client.get(f"/companies/{cid}/history")

    @task(2)
    def compare_companies(self):
        if len(self.company_ids) >= 2:
            ids = ",".join(str(c) for c in random.sample(self.company_ids, 2))
            self.client.get(f"/companies/compare?company_ids={ids}")


class BiToolUser(HttpUser):
    """BI Tool — bulk snapshot pulls, 30% of traffic."""
    weight = 3
    wait_time = between(1, 3)

    @task(5)
    def paginated_snapshots(self):
        self.client.get("/snapshots?page=1&page_size=100")

    @task(3)
    def sector_filter(self):
        sector = random.choice(["Automobiles & Parts", "Personal & Household Goods"])
        self.client.get(f"/snapshots?sector={sector}")

    @task(2)
    def latest_snapshots(self):
        self.client.get("/snapshots/latest")


class AuditUser(HttpUser):
    """Audit / Compliance — upload inspection, 10% of traffic."""
    weight = 1
    wait_time = between(2, 5)
    upload_ids: list[int] = []

    def on_start(self):
        r = self.client.get("/uploads")
        if r.status_code == 200:
            self.upload_ids = [u["id"] for u in r.json()]

    @task(3)
    def list_uploads(self):
        self.client.get("/uploads")

    @task(4)
    def upload_details(self):
        if self.upload_ids:
            uid = random.choice(self.upload_ids)
            self.client.get(f"/uploads/{uid}/details")

    @task(3)
    def download_file(self):
        if self.upload_ids:
            uid = random.choice(self.upload_ids)
            self.client.get(f"/uploads/{uid}/file")
