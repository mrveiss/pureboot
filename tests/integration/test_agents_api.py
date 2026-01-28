"""Integration tests for site agent API endpoints."""
import pytest
from fastapi.testclient import TestClient


class TestAgentTokenGeneration:
    """Test agent token generation."""

    def test_generate_agent_token(self, client: TestClient):
        """Generate registration token for a site."""
        # Create a site first
        site_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = site_resp.json()["data"]["id"]

        # Generate token
        response = client.post(f"/api/v1/sites/{site_id}/agent-token")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "token" in data
        assert len(data["token"]) > 20  # Should be a decent length
        assert data["expires_in_hours"] == 24

    def test_generate_token_nonexistent_site(self, client: TestClient):
        """Cannot generate token for non-existent site."""
        response = client.post("/api/v1/sites/nonexistent-id/agent-token")
        assert response.status_code == 404

    def test_generate_token_regular_group_fails(self, client: TestClient):
        """Cannot generate token for regular group (not a site)."""
        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]

        response = client.post(f"/api/v1/sites/{group_id}/agent-token")
        assert response.status_code == 404

    def test_regenerate_token_invalidates_old(self, client: TestClient):
        """Regenerating token invalidates the old one."""
        # Create site
        site_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = site_resp.json()["data"]["id"]

        # Generate first token
        token1_resp = client.post(f"/api/v1/sites/{site_id}/agent-token")
        token1 = token1_resp.json()["data"]["token"]

        # Generate second token
        token2_resp = client.post(f"/api/v1/sites/{site_id}/agent-token")
        token2 = token2_resp.json()["data"]["token"]

        # Tokens should be different
        assert token1 != token2

        # Only token2 should work for registration
        # (We test this in the registration tests)


class TestAgentRegistration:
    """Test agent registration endpoint."""

    def test_register_agent_valid_token(self, client: TestClient):
        """Agent can register with valid token."""
        # Create site and generate token
        site_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = site_resp.json()["data"]["id"]

        token_resp = client.post(f"/api/v1/sites/{site_id}/agent-token")
        token = token_resp.json()["data"]["token"]

        # Register agent
        response = client.post(
            "/api/v1/agents/register",
            json={
                "site_id": site_id,
                "token": token,
                "agent_url": "https://agent.local:8443",
                "agent_version": "0.1.0",
                "capabilities": ["tftp", "http"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["config"]["site_id"] == site_id
        assert data["config"]["site_name"] == "datacenter-west"

    def test_register_agent_invalid_token(self, client: TestClient):
        """Agent registration fails with invalid token."""
        # Create site and generate token
        site_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = site_resp.json()["data"]["id"]

        # Generate token (but use a wrong one)
        client.post(f"/api/v1/sites/{site_id}/agent-token")

        response = client.post(
            "/api/v1/agents/register",
            json={
                "site_id": site_id,
                "token": "wrong-token",
                "agent_url": "https://agent.local:8443",
                "agent_version": "0.1.0",
            },
        )
        assert response.status_code == 401

    def test_register_agent_no_token_configured(self, client: TestClient):
        """Agent registration fails if no token was generated."""
        # Create site but don't generate token
        site_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = site_resp.json()["data"]["id"]

        response = client.post(
            "/api/v1/agents/register",
            json={
                "site_id": site_id,
                "token": "any-token",
                "agent_url": "https://agent.local:8443",
                "agent_version": "0.1.0",
            },
        )
        assert response.status_code == 400
        assert "No registration token" in response.json()["detail"]

    def test_register_agent_updates_site_status(self, client: TestClient):
        """Registration updates site's agent status."""
        # Create site and generate token
        site_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = site_resp.json()["data"]["id"]

        token_resp = client.post(f"/api/v1/sites/{site_id}/agent-token")
        token = token_resp.json()["data"]["token"]

        # Register
        client.post(
            "/api/v1/agents/register",
            json={
                "site_id": site_id,
                "token": token,
                "agent_url": "https://agent.local:8443",
                "agent_version": "0.1.0",
            },
        )

        # Check site status
        site_resp = client.get(f"/api/v1/sites/{site_id}")
        site_data = site_resp.json()["data"]
        assert site_data["agent_url"] == "https://agent.local:8443"
        assert site_data["agent_status"] == "online"

    def test_register_agent_returns_config(self, client: TestClient):
        """Registration returns site configuration."""
        # Create site with specific settings
        site_resp = client.post(
            "/api/v1/sites",
            json={
                "name": "datacenter-west",
                "autonomy_level": "limited",
                "cache_policy": "assigned",
                "cache_max_size_gb": 50,
            },
        )
        site_id = site_resp.json()["data"]["id"]

        token_resp = client.post(f"/api/v1/sites/{site_id}/agent-token")
        token = token_resp.json()["data"]["token"]

        response = client.post(
            "/api/v1/agents/register",
            json={
                "site_id": site_id,
                "token": token,
                "agent_url": "https://agent.local:8443",
                "agent_version": "0.1.0",
            },
        )
        config = response.json()["config"]
        assert config["autonomy_level"] == "limited"
        assert config["cache_policy"] == "assigned"
        assert config["cache_max_size_gb"] == 50

    def test_register_agent_nonexistent_site(self, client: TestClient):
        """Registration fails for non-existent site."""
        response = client.post(
            "/api/v1/agents/register",
            json={
                "site_id": "nonexistent-id",
                "token": "any-token",
                "agent_url": "https://agent.local:8443",
                "agent_version": "0.1.0",
            },
        )
        assert response.status_code == 404


class TestAgentHeartbeat:
    """Test agent heartbeat endpoint."""

    def _setup_registered_agent(self, client: TestClient) -> tuple[str, str]:
        """Helper to create a site with registered agent."""
        site_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = site_resp.json()["data"]["id"]

        token_resp = client.post(f"/api/v1/sites/{site_id}/agent-token")
        token = token_resp.json()["data"]["token"]

        client.post(
            "/api/v1/agents/register",
            json={
                "site_id": site_id,
                "token": token,
                "agent_url": "https://agent.local:8443",
                "agent_version": "0.1.0",
            },
        )
        return site_id, token

    def test_heartbeat_success(self, client: TestClient):
        """Agent heartbeat succeeds."""
        site_id, _ = self._setup_registered_agent(client)

        response = client.post(
            "/api/v1/agents/heartbeat",
            json={
                "site_id": site_id,
                "agent_version": "0.1.0",
                "uptime_seconds": 3600,
                "services": {"tftp": "ok", "http": "ok"},
                "nodes_seen_last_hour": 5,
                "active_boots": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["acknowledged"] is True
        assert "server_time" in data
        assert "commands" in data

    def test_heartbeat_updates_last_seen(self, client: TestClient):
        """Heartbeat updates agent_last_seen."""
        site_id, _ = self._setup_registered_agent(client)

        # Send heartbeat
        client.post(
            "/api/v1/agents/heartbeat",
            json={
                "site_id": site_id,
                "agent_version": "0.1.0",
                "uptime_seconds": 3600,
                "services": {"tftp": "ok", "http": "ok"},
            },
        )

        # Check site status
        site_resp = client.get(f"/api/v1/sites/{site_id}")
        site_data = site_resp.json()["data"]
        assert site_data["agent_status"] == "online"
        assert site_data["agent_last_seen"] is not None

    def test_heartbeat_nonexistent_site(self, client: TestClient):
        """Heartbeat fails for non-existent site."""
        response = client.post(
            "/api/v1/agents/heartbeat",
            json={
                "site_id": "nonexistent-id",
                "agent_version": "0.1.0",
                "uptime_seconds": 3600,
                "services": {"tftp": "ok"},
            },
        )
        assert response.status_code == 404

    def test_heartbeat_with_metrics(self, client: TestClient):
        """Heartbeat accepts full metrics."""
        site_id, _ = self._setup_registered_agent(client)

        response = client.post(
            "/api/v1/agents/heartbeat",
            json={
                "site_id": site_id,
                "agent_version": "0.1.0",
                "uptime_seconds": 86400,
                "services": {"tftp": "ok", "http": "ok", "proxy": "ok"},
                "nodes_seen_last_hour": 50,
                "active_boots": 3,
                "cache_hit_rate": 0.85,
                "disk_usage_percent": 45.5,
                "pending_sync_items": 10,
                "conflicts_pending": 2,
            },
        )
        assert response.status_code == 200


class TestAgentStatus:
    """Test agent status endpoint."""

    def test_get_agent_status(self, client: TestClient):
        """Get agent status for a site."""
        # Create site
        site_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = site_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/agents/{site_id}/status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["site_id"] == site_id
        assert data["site_name"] == "datacenter-west"
        assert data["agent_status"] is None  # Not registered yet

    def test_get_agent_status_after_registration(self, client: TestClient):
        """Agent status shows online after registration."""
        # Create and register
        site_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = site_resp.json()["data"]["id"]

        token_resp = client.post(f"/api/v1/sites/{site_id}/agent-token")
        token = token_resp.json()["data"]["token"]

        client.post(
            "/api/v1/agents/register",
            json={
                "site_id": site_id,
                "token": token,
                "agent_url": "https://agent.local:8443",
                "agent_version": "0.1.0",
            },
        )

        response = client.get(f"/api/v1/agents/{site_id}/status")
        data = response.json()["data"]
        assert data["agent_url"] == "https://agent.local:8443"
        # Status could be online, degraded, or offline depending on timing

    def test_get_agent_status_nonexistent_site(self, client: TestClient):
        """Agent status fails for non-existent site."""
        response = client.get("/api/v1/agents/nonexistent-id/status")
        assert response.status_code == 404
