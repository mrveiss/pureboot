# API Documentation

This directory contains REST API documentation for PureBoot.

## Contents

- [nodes.md](nodes.md) - Node management endpoints
- [workflows.md](workflows.md) - Workflow management endpoints
- [templates.md](templates.md) - Template management endpoints
- [provisioning.md](provisioning.md) - Provisioning and boot decision endpoints
- [hypervisors.md](hypervisors.md) - Hypervisor integration endpoints

## Base URL

```
/api/v1
```

## Authentication

All API endpoints require JWT authentication except for provisioning endpoints used by nodes during boot.

```http
Authorization: Bearer <token>
```

## Response Format

All responses follow a consistent structure:

```json
{
  "success": true,
  "data": {...},
  "message": "Operation completed"
}
```

## Endpoint Overview

### Node Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/nodes` | List all nodes |
| GET | `/api/v1/nodes/{id}` | Get node details |
| POST | `/api/v1/nodes` | Register new node |
| PATCH | `/api/v1/nodes/{id}` | Update node |
| PATCH | `/api/v1/nodes/{id}/state` | Transition state |
| DELETE | `/api/v1/nodes/{id}` | Retire node |
| POST | `/api/v1/nodes/{id}/approve` | Four-Eye approval |

### Workflow Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/workflows` | List workflows |
| GET | `/api/v1/workflows/{id}` | Get workflow details |
| POST | `/api/v1/workflows` | Create workflow |
| PATCH | `/api/v1/workflows/{id}` | Update workflow |
| DELETE | `/api/v1/workflows/{id}` | Delete workflow |

### Provisioning

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/next?mac={mac}` | Get boot instructions |
| POST | `/api/v1/report` | Node status reporting |
| POST | `/api/v1/deprovision` | Secure data erasure |
| POST | `/api/v1/migrate` | Hardware migration |

### Hypervisor Integration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/hypervisors` | List hypervisors |
| POST | `/api/v1/hypervisors` | Add hypervisor |
| GET | `/api/v1/hypervisors/{id}/vms` | List VMs |
| POST | `/api/v1/hypervisors/{id}/vms` | Create VM |
| POST | `/api/v1/hypervisors/{id}/sync` | Sync templates |

See individual endpoint files for detailed request/response schemas.
