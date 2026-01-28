# Multi-Site Management Phase 2: Site Agent (Minimal)

**Issue:** #76 (Phase 2 of 7)
**Status:** COMPLETED
**Prerequisites:** Phase 1 (Site Model Foundation) - COMPLETED
**Completed:** 2026-01-28

---

## Overview

Phase 2 creates a minimal site agent that can serve boot files locally and register with the central controller. The agent reuses existing PureBoot components (TFTP, HTTP) in a standalone deployment mode.

### Goals

1. Create site agent entry point and configuration
2. Implement agent registration with central controller
3. Implement heartbeat protocol
4. Enable agent to serve boot files locally
5. Add agent management endpoints to central

### Non-Goals (Later Phases)

- API proxy and caching (Phase 3)
- Offline operation (Phase 4)
- Conflict resolution (Phase 5)
- Node migration (Phase 6)

---

## Implementation Tasks (TDD)

### Task 1: Agent Configuration Model

**Files:**
- Modify: `src/config.py`
- Test: `tests/unit/test_config.py`

**Changes:**
```python
class AgentSettings(BaseSettings):
    """Site agent configuration."""
    mode: str = "controller"  # controller, agent
    site_id: str | None = None  # Required when mode=agent
    central_url: str | None = None  # Central controller URL
    central_token: str | None = None  # Registration token
    heartbeat_interval: int = 60  # seconds
    data_dir: str = "/var/lib/pureboot-agent"
```

**Tests:**
- test_agent_mode_configuration
- test_agent_requires_site_id
- test_agent_requires_central_url

---

### Task 2: Agent Registration Endpoint (Central)

**Files:**
- Create: `src/api/routes/agents.py`
- Modify: `src/main.py`
- Test: `tests/integration/test_agents_api.py`

**Endpoints:**
```python
@router.post("/agents/register")
async def register_agent(registration: AgentRegistration):
    """Agent registers with central controller.

    Validates token, updates site's agent_url and agent_status.
    Returns agent configuration (sync settings, cache policy, etc.)
    """

class AgentRegistration(BaseModel):
    site_id: str
    token: str
    agent_url: str
    agent_version: str
    capabilities: list[str] = []  # tftp, http, proxy
```

**Tests:**
- test_register_agent_valid_token
- test_register_agent_invalid_token
- test_register_agent_updates_site_status
- test_register_agent_returns_config

---

### Task 3: Agent Token Generation

**Files:**
- Modify: `src/api/routes/sites.py`
- Modify: `src/db/models.py`
- Test: `tests/integration/test_sites_api.py`

**Changes:**
```python
@router.post("/sites/{site_id}/agent-token")
async def generate_agent_token(site_id: str):
    """Generate a one-time registration token for site agent.

    Token is stored hashed, returned once in plain text.
    """
```

**Tests:**
- test_generate_agent_token
- test_token_only_shown_once
- test_regenerate_token_invalidates_old

---

### Task 4: Heartbeat Endpoint (Central)

**Files:**
- Modify: `src/api/routes/agents.py`
- Test: `tests/integration/test_agents_api.py`

**Endpoint:**
```python
@router.post("/agents/heartbeat")
async def agent_heartbeat(heartbeat: AgentHeartbeat):
    """Receive heartbeat from site agent.

    Updates agent_last_seen, agent_status.
    Returns any pending commands (sync trigger, config update).
    """

class AgentHeartbeat(BaseModel):
    site_id: str
    timestamp: datetime
    agent_version: str
    uptime_seconds: int
    services: dict[str, str]  # {"tftp": "ok", "http": "ok"}
    nodes_seen_last_hour: int = 0
    active_boots: int = 0
    cache_hit_rate: float = 0.0
    disk_usage_percent: float = 0.0
    pending_sync_items: int = 0
    last_sync_at: datetime | None = None
```

**Tests:**
- test_heartbeat_updates_last_seen
- test_heartbeat_updates_status_online
- test_heartbeat_returns_pending_commands
- test_stale_heartbeat_marks_degraded

---

### Task 5: Agent Status Update Job

**Files:**
- Create: `src/core/agent_status_job.py`
- Modify: `src/main.py` (register job)
- Test: `tests/unit/test_agent_status_job.py`

**Changes:**
```python
async def update_agent_statuses():
    """Periodic job to update agent statuses based on heartbeats.

    Runs every minute, marks agents as:
    - online: heartbeat within 2 intervals
    - degraded: heartbeat within 2-5 intervals
    - offline: no heartbeat for 5+ intervals
    """
```

**Tests:**
- test_online_status_recent_heartbeat
- test_degraded_status_stale_heartbeat
- test_offline_status_no_heartbeat

---

### Task 6: Site Agent Entry Point

**Files:**
- Create: `src/agent/__init__.py`
- Create: `src/agent/main.py`
- Test: `tests/unit/test_agent_main.py`

**Changes:**
```python
# src/agent/main.py
"""PureBoot Site Agent entry point."""

async def main():
    """Run site agent."""
    # 1. Load agent config
    # 2. Register with central (if not registered)
    # 3. Start TFTP server
    # 4. Start HTTP server
    # 5. Start heartbeat loop
```

**Tests:**
- test_agent_starts_tftp
- test_agent_starts_http
- test_agent_registers_on_startup
- test_agent_sends_heartbeats

---

### Task 7: Agent Registration Client

**Files:**
- Create: `src/agent/central_client.py`
- Test: `tests/unit/test_central_client.py`

**Changes:**
```python
class CentralClient:
    """Client for communicating with central controller."""

    def __init__(self, central_url: str, site_id: str, token: str):
        ...

    async def register(self, agent_url: str) -> AgentConfig:
        """Register with central, return config."""

    async def heartbeat(self, metrics: AgentMetrics) -> HeartbeatResponse:
        """Send heartbeat, return any pending commands."""
```

**Tests:**
- test_register_success
- test_register_invalid_token
- test_heartbeat_success
- test_heartbeat_offline_handling

---

### Task 8: Agent Heartbeat Loop

**Files:**
- Create: `src/agent/heartbeat.py`
- Test: `tests/unit/test_agent_heartbeat.py`

**Changes:**
```python
class HeartbeatLoop:
    """Manages periodic heartbeat to central."""

    def __init__(self, client: CentralClient, interval: int = 60):
        ...

    async def start(self):
        """Start heartbeat loop."""

    async def stop(self):
        """Stop heartbeat loop."""

    def collect_metrics(self) -> AgentMetrics:
        """Collect current agent metrics."""
```

**Tests:**
- test_heartbeat_loop_sends_on_interval
- test_heartbeat_loop_handles_network_failure
- test_heartbeat_loop_collects_metrics

---

### Task 9: Agent Boot Services

**Files:**
- Modify: `src/agent/main.py`
- Test: `tests/integration/test_agent_boot.py`

**Changes:**
Reuse existing TFTP and HTTP servers in agent mode:
- TFTP serves bootloaders from local cache
- HTTP serves boot scripts and templates

**Tests:**
- test_agent_serves_ipxe_binary
- test_agent_serves_boot_script
- test_agent_logs_boot_requests

---

### Task 10: Agent Docker Configuration

**Files:**
- Create: `docker/agent/Dockerfile`
- Create: `docker/agent/docker-compose.yml`
- Create: `docker/agent/entrypoint.sh`

**Dockerfile:**
```dockerfile
FROM python:3.12-slim
# Install pureboot in agent mode
# Expose ports: 69/udp (TFTP), 8080 (HTTP), 8443 (API)
```

---

### Task 11: Agent CLI Commands

**Files:**
- Create: `src/agent/cli.py`
- Test: `tests/unit/test_agent_cli.py`

**Commands:**
```bash
pureboot-agent init --site-id <id> --central-url <url> --token <token>
pureboot-agent start
pureboot-agent status
pureboot-agent sync --force
```

**Tests:**
- test_init_creates_config
- test_start_requires_config
- test_status_shows_connection_state

---

## Dependencies

| Task | Depends On |
|------|------------|
| 2 | 1 |
| 3 | 1 |
| 4 | 2 |
| 5 | 4 |
| 6 | 1, 7 |
| 7 | 1 |
| 8 | 7 |
| 9 | 6 |
| 10 | 6 |
| 11 | 6 |

---

## Success Criteria

1. Site admin can generate agent registration token
2. Agent can register with central controller
3. Agent sends periodic heartbeats
4. Central tracks agent status (online/degraded/offline)
5. Agent serves TFTP and HTTP boot files
6. Agent can be deployed via Docker
7. Agent CLI for initialization and management

---

## Notes

- Agent reuses existing PureBoot TFTP/HTTP code
- Agent runs as a separate process (not embedded in controller)
- Token-based authentication for initial registration
- Heartbeat carries agent metrics for monitoring
- Phase 3 will add API proxy and content caching
