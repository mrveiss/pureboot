"""Tests for iPXE builder."""
import pytest
from unittest.mock import AsyncMock, patch

from src.pxe.ipxe_builder import IPXEBuilder


class TestIPXEBuilder:
    """Test iPXE binary building."""

    @pytest.fixture
    def builder(self):
        """Create builder instance."""
        return IPXEBuilder()

    def test_generates_build_script(self, builder):
        """Builder generates correct embedded script."""
        script = builder.generate_embedded_script(
            server_address="192.168.1.10",
            timeout=5
        )

        assert "#!ipxe" in script
        assert "192.168.1.10" in script
        assert "dhcp" in script

    @pytest.mark.asyncio
    async def test_build_returns_bytes(self, builder):
        """Build returns binary data."""
        with patch.object(builder, "_run_docker_build", new_callable=AsyncMock) as mock:
            mock.return_value = b"ELF binary data"

            result = await builder.build(
                architecture="bios",
                server_address="192.168.1.10"
            )

            assert isinstance(result, bytes)
            assert len(result) > 0

    def test_architecture_validation(self, builder):
        """Only bios and uefi architectures allowed."""
        with pytest.raises(ValueError):
            builder.generate_embedded_script(
                server_address="192.168.1.10",
                architecture="invalid"
            )
