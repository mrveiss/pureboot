"""Integration tests for template API."""
import pytest


class TestTemplateVersions:
    """Test template version endpoints."""

    def test_create_first_version(self, client, test_db):
        """POST /templates/{id}/versions creates v1.0 for new template."""
        from src.db.models import Template
        template = Template(name="test-kickstart", type="kickstart")
        test_db.add(template)
        test_db.flush()

        response = client.post(
            f"/api/v1/templates/{template.id}/versions",
            json={"content": "# kickstart config", "commit_message": "Initial version"},
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["major"] == 1
        assert data["minor"] == 0
        assert data["version_string"] == "v1.0"

    def test_create_minor_version(self, client, test_db):
        """POST /templates/{id}/versions?bump=minor increments minor version."""
        from src.db.models import Template, TemplateVersion
        template = Template(name="test-kickstart", type="kickstart")
        test_db.add(template)
        test_db.flush()

        v1 = TemplateVersion(
            template_id=template.id, major=1, minor=0,
            content="v1.0", content_hash="hash1"
        )
        test_db.add(v1)
        test_db.flush()
        template.current_version_id = v1.id
        test_db.flush()

        response = client.post(
            f"/api/v1/templates/{template.id}/versions?bump=minor",
            json={"content": "v1.1 content"},
        )

        assert response.status_code == 201
        assert response.json()["data"]["version_string"] == "v1.1"

    def test_create_major_version(self, client, test_db):
        """POST /templates/{id}/versions?bump=major increments major version."""
        from src.db.models import Template, TemplateVersion
        template = Template(name="test-kickstart", type="kickstart")
        test_db.add(template)
        test_db.flush()

        v1 = TemplateVersion(
            template_id=template.id, major=1, minor=0,
            content="v1.0", content_hash="hash1"
        )
        test_db.add(v1)
        test_db.flush()
        template.current_version_id = v1.id
        test_db.flush()

        response = client.post(
            f"/api/v1/templates/{template.id}/versions?bump=major",
            json={"content": "v2.0 content"},
        )

        assert response.status_code == 201
        assert response.json()["data"]["version_string"] == "v2.0"

    def test_list_versions(self, client, test_db):
        """GET /templates/{id}/versions returns all versions."""
        from src.db.models import Template, TemplateVersion
        template = Template(name="test-kickstart", type="kickstart")
        test_db.add(template)
        test_db.flush()

        for i in range(3):
            v = TemplateVersion(
                template_id=template.id, major=1, minor=i,
                content=f"v1.{i}", content_hash=f"hash{i}"
            )
            test_db.add(v)
        test_db.flush()

        response = client.get(f"/api/v1/templates/{template.id}/versions")

        assert response.status_code == 200
        assert response.json()["total"] == 3

    def test_get_specific_version(self, client, test_db):
        """GET /templates/{id}/versions/v1.0 returns specific version."""
        from src.db.models import Template, TemplateVersion
        template = Template(name="test-kickstart", type="kickstart")
        test_db.add(template)
        test_db.flush()

        v1 = TemplateVersion(
            template_id=template.id, major=1, minor=0,
            content="Version 1.0 content", content_hash="hash1"
        )
        test_db.add(v1)
        test_db.flush()

        response = client.get(f"/api/v1/templates/{template.id}/versions/v1.0")

        assert response.status_code == 200
        assert response.json()["data"]["content"] == "Version 1.0 content"

    def test_get_latest_version(self, client, test_db):
        """GET /templates/{id}/versions/latest returns current version."""
        from src.db.models import Template, TemplateVersion
        template = Template(name="test-kickstart", type="kickstart")
        test_db.add(template)
        test_db.flush()

        v1 = TemplateVersion(
            template_id=template.id, major=1, minor=0,
            content="v1.0", content_hash="hash1"
        )
        v2 = TemplateVersion(
            template_id=template.id, major=1, minor=1,
            content="v1.1 latest", content_hash="hash2"
        )
        test_db.add_all([v1, v2])
        test_db.flush()
        template.current_version_id = v2.id
        test_db.flush()

        response = client.get(f"/api/v1/templates/{template.id}/versions/latest")

        assert response.status_code == 200
        assert response.json()["data"]["content"] == "v1.1 latest"

    def test_get_version_not_found(self, client, test_db):
        """GET /templates/{id}/versions/v99.0 returns 404."""
        from src.db.models import Template
        template = Template(name="test-kickstart", type="kickstart")
        test_db.add(template)
        test_db.flush()

        response = client.get(f"/api/v1/templates/{template.id}/versions/v99.0")

        assert response.status_code == 404

    def test_create_version_template_not_found(self, client, test_db):
        """POST /templates/{id}/versions returns 404 for missing template."""
        response = client.post(
            "/api/v1/templates/nonexistent-id/versions",
            json={"content": "test"},
        )

        assert response.status_code == 404

    def test_create_version_invalid_bump(self, client, test_db):
        """POST /templates/{id}/versions with invalid bump returns 400."""
        from src.db.models import Template
        template = Template(name="test-kickstart", type="kickstart")
        test_db.add(template)
        test_db.flush()

        response = client.post(
            f"/api/v1/templates/{template.id}/versions?bump=invalid",
            json={"content": "test content"},
        )

        assert response.status_code == 400
        assert "Invalid bump type" in response.json()["detail"]
