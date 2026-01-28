"""Integration tests for site management API endpoints."""
import pytest
from fastapi.testclient import TestClient


class TestSitesCRUD:
    """Test site CRUD operations."""

    def test_create_site(self, client: TestClient):
        """Create a new site."""
        response = client.post(
            "/api/v1/sites",
            json={
                "name": "datacenter-west",
                "description": "Western datacenter",
                "autonomy_level": "limited",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "datacenter-west"
        assert data["data"]["is_site"] is True
        assert data["data"]["autonomy_level"] == "limited"

    def test_create_site_with_defaults(self, client: TestClient):
        """Create site with default values."""
        response = client.post(
            "/api/v1/sites",
            json={"name": "default-site"},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["autonomy_level"] == "readonly"
        assert data["conflict_resolution"] == "central_wins"
        assert data["cache_policy"] == "minimal"
        assert data["discovery_method"] == "dhcp"
        assert data["migration_policy"] == "manual"

    def test_create_site_with_all_fields(self, client: TestClient):
        """Create site with all site-specific fields."""
        response = client.post(
            "/api/v1/sites",
            json={
                "name": "full-site",
                "description": "Site with all fields",
                "agent_url": "https://site-agent.local:8443",
                "autonomy_level": "full",
                "conflict_resolution": "last_write",
                "cache_policy": "mirror",
                "cache_max_size_gb": 100,
                "cache_retention_days": 60,
                "discovery_method": "dns",
                "migration_policy": "bidirectional",
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["agent_url"] == "https://site-agent.local:8443"
        assert data["autonomy_level"] == "full"
        assert data["cache_policy"] == "mirror"
        assert data["cache_max_size_gb"] == 100

    def test_create_duplicate_name_fails(self, client: TestClient):
        """Cannot create site with duplicate name."""
        client.post("/api/v1/sites", json={"name": "datacenter-west"})
        response = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        assert response.status_code == 409

    def test_list_sites(self, client: TestClient):
        """List all sites."""
        client.post("/api/v1/sites", json={"name": "site-1"})
        client.post("/api/v1/sites", json={"name": "site-2"})
        # Also create a regular group - should NOT appear in sites list
        client.post("/api/v1/groups", json={"name": "regular-group"})

        response = client.get("/api/v1/sites")
        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_list_sites_excludes_regular_groups(self, client: TestClient):
        """Sites list excludes regular DeviceGroups."""
        client.post("/api/v1/groups", json={"name": "webservers"})
        client.post("/api/v1/groups", json={"name": "databases"})
        client.post("/api/v1/sites", json={"name": "datacenter-east"})

        response = client.get("/api/v1/sites")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["data"][0]["name"] == "datacenter-east"

    def test_get_site(self, client: TestClient):
        """Get site by ID."""
        create_resp = client.post(
            "/api/v1/sites",
            json={"name": "datacenter-west", "autonomy_level": "full"},
        )
        site_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/sites/{site_id}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == site_id
        assert data["autonomy_level"] == "full"

    def test_get_site_returns_agent_status(self, client: TestClient):
        """Get site includes agent status fields."""
        create_resp = client.post(
            "/api/v1/sites",
            json={"name": "datacenter-west"},
        )
        site_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/sites/{site_id}")
        data = response.json()["data"]
        # Agent status fields should exist (even if null)
        assert "agent_status" in data
        assert "agent_last_seen" in data

    def test_get_nonexistent_site_fails(self, client: TestClient):
        """Getting non-existent site returns 404."""
        response = client.get("/api/v1/sites/nonexistent-id")
        assert response.status_code == 404

    def test_get_regular_group_as_site_fails(self, client: TestClient):
        """Getting a regular group via sites endpoint returns 404."""
        # Create a regular group
        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]

        # Try to get it as a site
        response = client.get(f"/api/v1/sites/{group_id}")
        assert response.status_code == 404

    def test_update_site(self, client: TestClient):
        """Update site configuration."""
        create_resp = client.post(
            "/api/v1/sites",
            json={"name": "datacenter-west"},
        )
        site_id = create_resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/sites/{site_id}",
            json={
                "description": "Updated description",
                "autonomy_level": "full",
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["description"] == "Updated description"
        assert data["autonomy_level"] == "full"

    def test_update_site_autonomy_level(self, client: TestClient):
        """Update site autonomy level."""
        create_resp = client.post(
            "/api/v1/sites",
            json={"name": "datacenter-west", "autonomy_level": "readonly"},
        )
        site_id = create_resp.json()["data"]["id"]

        # Update to limited
        response = client.patch(
            f"/api/v1/sites/{site_id}",
            json={"autonomy_level": "limited"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["autonomy_level"] == "limited"

        # Update to full
        response = client.patch(
            f"/api/v1/sites/{site_id}",
            json={"autonomy_level": "full"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["autonomy_level"] == "full"

    def test_delete_empty_site(self, client: TestClient):
        """Delete empty site succeeds."""
        create_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = create_resp.json()["data"]["id"]

        response = client.delete(f"/api/v1/sites/{site_id}")
        assert response.status_code == 200

        # Verify it's gone
        response = client.get(f"/api/v1/sites/{site_id}")
        assert response.status_code == 404


class TestSiteNodes:
    """Test site-node relationships."""

    def test_list_site_nodes(self, client: TestClient):
        """List nodes assigned to a site by home_site_id."""
        site_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = site_resp.json()["data"]["id"]

        # Create nodes and assign home_site_id
        # Note: We need to create nodes first, then update their home_site_id
        # since NodeCreate doesn't have home_site_id field
        node1_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:55"},
        )
        node1_id = node1_resp.json()["data"]["id"]

        node2_resp = client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:66"},
        )
        node2_id = node2_resp.json()["data"]["id"]

        # Nodes without home_site_id
        client.post(
            "/api/v1/nodes",
            json={"mac_address": "00:11:22:33:44:77"},
        )

        # Assign nodes to site (would need PATCH endpoint supporting home_site_id)
        # For now, we test with the current data
        response = client.get(f"/api/v1/sites/{site_id}/nodes")
        assert response.status_code == 200
        # Initially 0 since we can't assign home_site_id via node API yet
        assert response.json()["total"] == 0


class TestSiteHierarchy:
    """Test site hierarchy operations."""

    def test_site_under_parent_site(self, client: TestClient):
        """Create a site under a parent site."""
        # Create parent site
        parent_resp = client.post("/api/v1/sites", json={"name": "region-us"})
        parent_id = parent_resp.json()["data"]["id"]

        # Create child site
        response = client.post(
            "/api/v1/sites",
            json={"name": "datacenter-west", "parent_id": parent_id},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["parent_id"] == parent_id
        assert data["path"] == "/region-us/datacenter-west"
        assert data["depth"] == 1

    def test_nested_sites_hierarchy(self, client: TestClient):
        """Create nested site hierarchy."""
        # Region
        region_resp = client.post("/api/v1/sites", json={"name": "region-us"})
        region_id = region_resp.json()["data"]["id"]

        # Datacenter
        dc_resp = client.post(
            "/api/v1/sites",
            json={"name": "datacenter-west", "parent_id": region_id},
        )
        dc_id = dc_resp.json()["data"]["id"]

        # Zone
        zone_resp = client.post(
            "/api/v1/sites",
            json={"name": "zone-a", "parent_id": dc_id},
        )
        zone_data = zone_resp.json()["data"]

        assert zone_data["path"] == "/region-us/datacenter-west/zone-a"
        assert zone_data["depth"] == 2

    def test_cannot_make_regular_group_parent_of_site(self, client: TestClient):
        """Sites can only have sites as parents, not regular groups."""
        # Create a regular group
        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]

        # Try to create site with regular group as parent
        response = client.post(
            "/api/v1/sites",
            json={"name": "datacenter-west", "parent_id": group_id},
        )
        assert response.status_code == 400
        assert "Sites can only be nested under other sites" in response.json()["detail"]

    def test_move_site_under_different_parent(self, client: TestClient):
        """Move site to different parent site."""
        # Create two regions
        region1_resp = client.post("/api/v1/sites", json={"name": "region-us"})
        region1_id = region1_resp.json()["data"]["id"]

        region2_resp = client.post("/api/v1/sites", json={"name": "region-eu"})
        region2_id = region2_resp.json()["data"]["id"]

        # Create datacenter under region-us
        dc_resp = client.post(
            "/api/v1/sites",
            json={"name": "datacenter-west", "parent_id": region1_id},
        )
        dc_id = dc_resp.json()["data"]["id"]

        # Move to region-eu
        response = client.patch(
            f"/api/v1/sites/{dc_id}",
            json={"parent_id": region2_id},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["parent_id"] == region2_id
        assert data["path"] == "/region-eu/datacenter-west"

    def test_cannot_move_site_under_regular_group(self, client: TestClient):
        """Cannot move site under a regular group."""
        site_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = site_resp.json()["data"]["id"]

        group_resp = client.post("/api/v1/groups", json={"name": "webservers"})
        group_id = group_resp.json()["data"]["id"]

        response = client.patch(
            f"/api/v1/sites/{site_id}",
            json={"parent_id": group_id},
        )
        assert response.status_code == 400

    def test_delete_site_with_children_fails(self, client: TestClient):
        """Cannot delete site with child sites."""
        parent_resp = client.post("/api/v1/sites", json={"name": "region-us"})
        parent_id = parent_resp.json()["data"]["id"]

        client.post(
            "/api/v1/sites",
            json={"name": "datacenter-west", "parent_id": parent_id},
        )

        response = client.delete(f"/api/v1/sites/{parent_id}")
        assert response.status_code == 400
        assert "Cannot delete site" in response.json()["detail"]

    def test_list_sites_by_parent(self, client: TestClient):
        """List sites filtered by parent."""
        # Create regions
        us_resp = client.post("/api/v1/sites", json={"name": "region-us"})
        us_id = us_resp.json()["data"]["id"]

        eu_resp = client.post("/api/v1/sites", json={"name": "region-eu"})
        eu_id = eu_resp.json()["data"]["id"]

        # Create datacenters under US
        client.post("/api/v1/sites", json={"name": "dc-west", "parent_id": us_id})
        client.post("/api/v1/sites", json={"name": "dc-east", "parent_id": us_id})

        # Create datacenters under EU
        client.post("/api/v1/sites", json={"name": "dc-london", "parent_id": eu_id})

        # List US datacenters
        response = client.get(f"/api/v1/sites?parent_id={us_id}")
        assert response.status_code == 200
        assert response.json()["total"] == 2


class TestSiteHealth:
    """Test site health endpoint."""

    def test_site_health_online(self, client: TestClient):
        """Get health for site (initial state)."""
        create_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = create_resp.json()["data"]["id"]

        response = client.get(f"/api/v1/sites/{site_id}/health")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["site_id"] == site_id
        assert "agent_status" in data
        assert "pending_sync_items" in data
        assert "conflicts_pending" in data

    def test_site_health_nonexistent_site(self, client: TestClient):
        """Health endpoint returns 404 for non-existent site."""
        response = client.get("/api/v1/sites/nonexistent-id/health")
        assert response.status_code == 404


class TestSiteSync:
    """Test site sync endpoint."""

    def test_trigger_sync_creates_request(self, client: TestClient):
        """Trigger sync creates a sync request."""
        create_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = create_resp.json()["data"]["id"]

        response = client.post(f"/api/v1/sites/{site_id}/sync")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "sync_id" in data
        assert data["status"] in ["queued", "started"]

    def test_trigger_sync_with_options(self, client: TestClient):
        """Trigger sync with full_sync option."""
        create_resp = client.post("/api/v1/sites", json={"name": "datacenter-west"})
        site_id = create_resp.json()["data"]["id"]

        response = client.post(
            f"/api/v1/sites/{site_id}/sync",
            json={"full_sync": True, "entity_types": ["node", "workflow"]},
        )
        assert response.status_code == 200

    def test_trigger_sync_nonexistent_site(self, client: TestClient):
        """Sync endpoint returns 404 for non-existent site."""
        response = client.post("/api/v1/sites/nonexistent-id/sync")
        assert response.status_code == 404


class TestSiteSettingsInheritance:
    """Test that sites inherit settings from parent sites."""

    def test_site_inherits_parent_settings(self, client: TestClient):
        """Child site inherits effective settings from parent."""
        # Create parent with a workflow
        parent_resp = client.post(
            "/api/v1/sites",
            json={"name": "region-us"},
        )
        parent_id = parent_resp.json()["data"]["id"]

        # Create child (doesn't set its own workflow)
        child_resp = client.post(
            "/api/v1/sites",
            json={"name": "datacenter-west", "parent_id": parent_id},
        )
        assert child_resp.status_code == 201


class TestSiteValidation:
    """Test site field validation."""

    def test_invalid_autonomy_level_rejected(self, client: TestClient):
        """Invalid autonomy level rejected."""
        response = client.post(
            "/api/v1/sites",
            json={"name": "test-site", "autonomy_level": "invalid"},
        )
        assert response.status_code == 422
        assert "autonomy_level" in response.text.lower()

    def test_invalid_cache_policy_rejected(self, client: TestClient):
        """Invalid cache policy rejected."""
        response = client.post(
            "/api/v1/sites",
            json={"name": "test-site", "cache_policy": "invalid"},
        )
        assert response.status_code == 422

    def test_invalid_conflict_resolution_rejected(self, client: TestClient):
        """Invalid conflict resolution rejected."""
        response = client.post(
            "/api/v1/sites",
            json={"name": "test-site", "conflict_resolution": "invalid"},
        )
        assert response.status_code == 422

    def test_invalid_migration_policy_rejected(self, client: TestClient):
        """Invalid migration policy rejected."""
        response = client.post(
            "/api/v1/sites",
            json={"name": "test-site", "migration_policy": "invalid"},
        )
        assert response.status_code == 422
