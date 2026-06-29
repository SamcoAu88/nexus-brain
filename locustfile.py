"""
Locust Load Testing Script for Nexus-Brain API
Run with: locust -f locustfile.py --host=http://localhost:8000
"""

from locust import HttpUser, task, between, constant
import random
import string


class NexusBrainUser(HttpUser):
    """Simulates a Nexus-Brain API user."""

    # Wait between 1-5 seconds between tasks
    wait_time = between(1, 5)

    # Shared auth token (set on start)
    auth_token = None

    def on_start(self):
        """Register and login on start."""
        username = f"loadtest_{random.randint(10000, 99999)}"

        # Signup
        self.client.post("/api/auth/signup", json={
            "username": username,
            "password": "Test1234!",
        })

        # Login
        resp = self.client.post("/api/auth/login", json={
            "username": username,
            "password": "Test1234!",
        })
        if resp.ok:
            data = resp.json()
            self.auth_token = data.get("access_token")

    @task(3)
    def health_check(self):
        """Check system health (no auth required)."""
        self.client.get("/api/health")

    @task(2)
    def readiness_check(self):
        """Check system readiness."""
        self.client.get("/api/health/ready")

    @task(1)
    def liveness_check(self):
        """Check liveness."""
        self.client.get("/api/health/live")

    @task(2)
    def chat_with_agent(self):
        """Send a message to the agent."""
        if not self.auth_token:
            return

        messages = [
            "What is Nexus-Brain?",
            "Remember that I like pizza",
            "Hello!",
            "Can you search for python?",
            "Tell me about Brisbane",
            "What was the last thing we talked about?",
        ]

        self.client.post(
            "/api/agent/chat",
            json={"input": random.choice(messages)},
            headers={"Authorization": f"Bearer {self.auth_token}"},
        )

    @task(1)
    def agent_status(self):
        """Check agent status."""
        if not self.auth_token:
            return

        self.client.get(
            "/api/agent/status",
            headers={"Authorization": f"Bearer {self.auth_token}"},
        )

    @task(1)
    def create_collection(self):
        """Create a memory collection."""
        if not self.auth_token:
            return

        name = "".join(random.choices(string.ascii_lowercase, k=10))
        self.client.post(
            "/api/memory/collections",
            json={"name": name, "description": f"Load test collection: {name}"},
            headers={"Authorization": f"Bearer {self.auth_token}"},
        )

    @task(1)
    def list_collections(self):
        """List memory collections."""
        if not self.auth_token:
            return

        self.client.get(
            "/api/memory/collections",
            headers={"Authorization": f"Bearer {self.auth_token}"},
        )

    @task(1)
    def metrics_endpoint(self):
        """Scrape Prometheus metrics."""
        self.client.get("/api/metrics")


class AnonymousUser(HttpUser):
    """Simulates unauthenticated requests."""

    wait_time = constant(3)

    @task(3)
    def health(self):
        self.client.get("/api/health")

    @task(1)
    def root(self):
        self.client.get("/")

    @task(2)
    def docs(self):
        self.client.get("/docs")

    @task(1)
    def openapi(self):
        self.client.get("/openapi.json")
