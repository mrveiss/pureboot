# Architecture Documentation

This directory contains system architecture and design documentation for PureBoot.

## Contents

- [state-machine.md](state-machine.md) - Node lifecycle state machine
- [boot-infrastructure.md](boot-infrastructure.md) - PXE/iPXE/UEFI boot system
- [controller.md](controller.md) - Controller service architecture
- [storage.md](storage.md) - Storage backend and templates
- [security.md](security.md) - Security architecture and RBAC

## High-Level Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                        PureBoot Platform                       │
├─────────────────┬─────────────────┬─────────────────┬──────────┤
│  PXE/iPXE/UEFI  │  Controller API │   Web UI        │  Storage │
│  Infrastructure │  (Workflows,    │  (Management,   │  Backend │
│                 │   Templates,    │   Monitoring)   │          │
│                 │   Node Registry)│                 │          │
└─────────────────┴─────────────────┴─────────────────┴──────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────┐
│                        Target Devices                          │
├─────────────┬─────────────┬─────────────┬─────────────┬───────┤
│  Bare-Metal │  Enterprise │  Virtual    │  Raspberry  │  Edge │
│  Servers    │  Laptops    │  Machines   │  Pi/ARM     │  IoT  │
└─────────────┴─────────────┴─────────────┴─────────────┴───────┘
```

## Core Components

1. **Boot Infrastructure** - TFTP/HTTP servers, DHCP integration
2. **Controller Service** - REST API, workflow engine, state machine
3. **Web UI** - Node management, monitoring, configuration
4. **Storage Backend** - Templates, ISOs, database

See the main [PRD](../PureBoot_Product_Requirements_Document.md) for complete architecture details.
