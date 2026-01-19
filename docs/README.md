# PureBoot Documentation

This directory contains all project documentation for PureBoot.

## Documentation Structure

```
docs/
├── PureBoot_Product_Requirements_Document.md  # Main PRD (v2.0)
├── architecture/          # System architecture and design
├── api/                   # API documentation and specifications
├── guides/                # User and developer guides
├── workflows/             # Provisioning workflow documentation
├── integrations/          # Third-party integration guides
└── reference/             # Technical reference materials
```

## Quick Links

### Core Documentation

- [Product Requirements Document](PureBoot_Product_Requirements_Document.md) - Complete PRD v2.0

### Architecture

- [System Architecture](architecture/README.md) - High-level system design
- [State Machine](architecture/state-machine.md) - Node lifecycle state machine
- [Boot Infrastructure](architecture/boot-infrastructure.md) - PXE/iPXE/UEFI boot system

### API Documentation

- [API Overview](api/README.md) - REST API documentation
- [Node Management API](api/nodes.md) - Node CRUD operations
- [Workflow API](api/workflows.md) - Workflow management
- [Provisioning API](api/provisioning.md) - Boot decision endpoints

### Guides

- [Getting Started](guides/getting-started.md) - Quick start guide
- [Installation](guides/installation.md) - Installation instructions
- [Configuration](guides/configuration.md) - Configuration reference
- [Development](guides/development.md) - Developer guide

### Workflows

- [Linux Provisioning](workflows/linux-provisioning.md) - Ubuntu, Debian, etc.
- [Windows Provisioning](workflows/windows-provisioning.md) - Windows with AD join
- [Raspberry Pi](workflows/raspberry-pi.md) - ARM SBC provisioning

### Integrations

- [oVirt/RHV Integration](integrations/oVirt_Integration.md) - Enterprise virtualization
- [Proxmox Integration](integrations/proxmox.md) - Proxmox VE
- [Hypervisor Overview](integrations/README.md) - All hypervisor integrations

### Reference

- [Bootloader Reference](reference/bootloaders.md) - PXELINUX, GRUB, iPXE
- [Template Reference](reference/templates.md) - Template formats and usage
- [Troubleshooting](reference/troubleshooting.md) - Common issues and solutions
