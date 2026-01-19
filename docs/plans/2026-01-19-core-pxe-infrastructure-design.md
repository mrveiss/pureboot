# Core PXE Infrastructure Design

**Date:** 2026-01-19
**Issue:** #1 - Core PXE Infrastructure
**Status:** Approved

## Overview

This document describes the design for PureBoot's core PXE/iPXE/UEFI boot infrastructure, which serves as the foundation for all provisioning workflows.

## Architecture

### Boot Flow

```
┌─────────────┐     DHCP      ┌─────────────────┐
│   Hardware  │──────────────▶│  Network DHCP   │
│  (PXE ROM)  │◀──────────────│  (External or   │
└─────────────┘   IP + next   │  Proxy DHCP)    │
       │          server      └─────────────────┘
       │
       │ TFTP request (port 69)
       ▼
┌─────────────────────────────────────────────────┐
│                PureBoot Server                   │
├─────────────┬─────────────────┬─────────────────┤
│ TFTP Server │  FastAPI (HTTP) │   Web UI        │
│ (Python)    │  /api/v1/boot   │   iPXE Builder  │
├─────────────┴─────────────────┴─────────────────┤
│              tftp/                               │
│              ├── bios/undionly.kpxe             │
│              └── uefi/ipxe.efi                  │
└─────────────────────────────────────────────────┘
       │
       │ iPXE chains to HTTP
       ▼
┌─────────────┐
│  iPXE gets  │──▶ GET /api/v1/boot?mac=XX:XX:XX
│  boot script│◀── (kernel, initrd, cmdline or "boot local")
└─────────────┘
```

### Key Decisions

| Component | Decision | Rationale |
|-----------|----------|-----------|
| DHCP | External config + optional Proxy DHCP | Flexibility for different network environments |
| TFTP | Pure Python server | Single deployable unit, no external dependencies |
| Boot flow | Always chainload to iPXE | Single code path, dynamic boot via HTTP API |
| iPXE binaries | Generated via Web UI | User configures server IP, downloads custom binary |
| Boot menu | PNG logo (UEFI) + ASCII fallback | Branding with universal compatibility |
| iPXE compilation | Docker-based | Clean build environment, no host dependencies |

## Components

### 1. TFTP Server

Pure Python TFTP server that serves only iPXE bootloader binaries.

```python
class TFTPServer:
    def __init__(self, tftp_root: str, bind_address: str = "0.0.0.0", port: int = 69):
        self.tftp_root = tftp_root
        self.bind_address = bind_address
        self.port = port

    async def start(self):
        """Start TFTP server (runs alongside FastAPI)"""

    async def handle_request(self, filename: str, client_addr: tuple):
        """Serve file from tftp_root, log request for discovery"""
```

**Features:**

- Read-only (serves files only, no uploads)
- Logs all requests (MAC address extraction for node discovery)
- Validates file paths (prevents directory traversal)
- Configurable root directory and bind address

**TFTP Root Structure:**

```
tftp/
├── bios/
│   └── undionly.kpxe      # Generated via Web UI
└── uefi/
    └── ipxe.efi           # Generated via Web UI
```

### 2. Proxy DHCP Server (Optional)

Proxy DHCP that provides PXE boot options without assigning IP addresses.

```python
class ProxyDHCPServer:
    def __init__(self, tftp_server: str, bind_address: str = "0.0.0.0"):
        self.tftp_server = tftp_server
        self.bind_address = bind_address

    async def start(self):
        """Listen on port 4011 (proxy DHCP port)"""

    async def handle_request(self, packet: bytes, client_addr: tuple):
        """Respond with PXE options based on client architecture"""
```

**Architecture Detection via DHCP Option 93:**

| Value | Architecture | Boot File |
|-------|--------------|-----------|
| 0x00 | BIOS | `bios/undionly.kpxe` |
| 0x07 | UEFI x64 | `uefi/ipxe.efi` |
| 0x09 | UEFI x64 (alt) | `uefi/ipxe.efi` |

**Use Cases:**

- No access to main DHCP server configuration
- Quick testing without network changes
- Isolated provisioning network

### 3. Boot API Endpoint

`GET /api/v1/boot?mac={mac}` returns iPXE script based on node state.

```python
@router.get("/boot")
async def get_boot_script(mac: str, request: Request):
    """Return iPXE script for node based on current state"""

    node = await node_service.find_by_mac(mac)

    if not node:
        # Unknown node - register as discovered, boot to local
        await node_service.create_discovered(mac, request.client.host)
        return ipxe_script_local_boot()

    if node.state in ("installed", "active"):
        # Already provisioned - boot from local disk
        return ipxe_script_local_boot()

    if node.state == "pending":
        # Ready to install - transition to installing, return install script
        await node_service.transition(node.id, "installing")
        return ipxe_script_install(node.workflow)

    # Other states (discovered, installing) - boot local
    return ipxe_script_local_boot()
```

**Response Content-Type:** `text/plain`

### 4. iPXE Boot Menu

Embedded script with branding, countdown timer, and user controls.

```ipxe
#!ipxe

# Try graphical logo on UEFI (requires IMAGE_PNG build flag)
console --picture http://${next-server}/assets/pureboot-logo.png 2>/dev/null ||

# ASCII fallback (always works)
echo
echo  ____                 ____              _
echo |  _ \ _   _ _ __ ___| __ )  ___   ___ | |_
echo | |_) | | | | '__/ _ \  _ \ / _ \ / _ \| __|
echo |  __/| |_| | | |  __/ |_) | (_) | (_) | |_
echo |_|    \__,_|_|  \___|____/ \___/ \___/ \__|
echo
echo Contacting PureBoot server...
echo

# Fetch boot instructions with timeout and retry
:retry
imgfetch --timeout 5000 http://${next-server}/api/v1/boot?mac=${mac:hexhyp} && goto boot_menu ||
echo Server unreachable. Retrying in 5 seconds... (Press 'L' for local boot)
sleep 5
goto retry

:boot_menu
echo
echo Boot instructions received.
echo
echo Press any key for boot menu, or wait 5 seconds to continue...
sleep 1 || goto menu
sleep 1 || goto menu
sleep 1 || goto menu
sleep 1 || goto menu
sleep 1 || goto menu
goto autoboot

:menu
menu PureBoot Options
item autoboot Continue with assigned action
item localboot Boot from local disk
item retry Retry server connection
item shell iPXE shell
choose --default autoboot --timeout 10000 selected
goto ${selected}

:autoboot
chain http://${next-server}/api/v1/boot?mac=${mac:hexhyp}

:localboot
echo Booting from local disk...
exit

:shell
shell
```

### 5. iPXE Builder (Web UI)

Web UI component that generates custom iPXE binaries with embedded boot script.

**API Endpoint:**

```python
@router.post("/api/v1/ipxe/build")
async def build_ipxe(
    server_address: str,
    architecture: Literal["bios", "uefi"],
    timeout: int = 5,
    show_menu: bool = True
):
    """Build custom iPXE binary with embedded script."""

    script = generate_boot_script(server_address, timeout, show_menu)
    binary = await compile_ipxe(architecture, script)

    filename = f"pureboot-{architecture}.{'kpxe' if architecture == 'bios' else 'efi'}"
    return StreamingResponse(binary, media_type="application/octet-stream",
                            headers={"Content-Disposition": f"attachment; filename={filename}"})
```

**Build Process (Docker-based):**

```python
async def compile_ipxe(arch: str, script: str) -> bytes:
    """Compile iPXE with embedded script using Docker"""
    # Write script to temp file
    # Run Docker container with iPXE source
    # Enable IMAGE_PNG and DOWNLOAD_PROTO_HTTPS flags
    # Return compiled binary
```

**Required iPXE Build Flags:**

```
IMAGE_PNG=1              # PNG logo support
DOWNLOAD_PROTO_HTTPS=1   # HTTPS support (recommended)
```

**Web UI Form:**

- Server IP/hostname input (with auto-detect option)
- Architecture selector (BIOS / UEFI / Both)
- Timeout setting
- Download button

## Project Structure

```
src/
├── pxe/
│   ├── __init__.py
│   ├── tftp_server.py      # Pure Python TFTP server
│   ├── dhcp_proxy.py       # Optional proxy DHCP
│   └── ipxe_builder.py     # iPXE compilation logic
├── api/
│   └── routes/
│       ├── boot.py         # GET /api/v1/boot
│       └── ipxe.py         # POST /api/v1/ipxe/build
├── config/
│   └── settings.py         # Pydantic settings
└── main.py                 # FastAPI app, starts TFTP/DHCP

tftp/                       # TFTP root (created on first run)
├── bios/
│   └── .gitkeep
└── uefi/
    └── .gitkeep

assets/
└── pureboot-logo.png       # Boot logo for UEFI

docker/
└── ipxe-builder/
    └── Dockerfile          # iPXE build environment
```

## Configuration

```yaml
server:
  host: "0.0.0.0"
  port: 8080

tftp:
  enabled: true
  host: "0.0.0.0"
  port: 69
  root: "./tftp"

dhcp_proxy:
  enabled: false
  host: "0.0.0.0"

boot_menu:
  timeout: 5
  show_menu: true
  logo_url: "/assets/pureboot-logo.png"
```

## Dependencies

**Python packages:**

- `fastapi` - HTTP API framework
- `uvicorn` - ASGI server
- `pydantic` - Configuration and validation
- TFTP library (TBD: `py3tftp` or custom implementation)

**System/Docker:**

- Docker (for iPXE compilation)
- iPXE source (fetched during build)

## Acceptance Criteria

- [ ] Nodes can PXE boot and receive boot instructions
- [ ] Both BIOS and UEFI systems supported
- [ ] iPXE chainloading working
- [ ] Boot menus generated dynamically based on node state
- [ ] Web UI can generate custom iPXE binaries
- [ ] Proxy DHCP can be enabled/disabled as needed

## Future Considerations

- Raspberry Pi network boot (separate boot flow, not PXE)
- HTTPS support for boot API
- Boot metrics and logging dashboard
- Pre-built iPXE binaries using `${next-server}` for quick start
