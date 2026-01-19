# PureBoot

**Unified Vendor-Neutral Node Lifecycle Platform**

PureBoot is a self-hosted, vendor-neutral provisioning and orchestration system designed to automate the entire lifecycle of diverse hardware platforms. It provides a unified control plane for bare-metal servers, enterprise laptops, virtual machines, Raspberry Pi nodes, and edge devices.

## Key Features

- **Unified Provisioning** - Single platform for x86 BIOS/UEFI, ARM (Raspberry Pi), VMs, and enterprise laptops
- **Enterprise Virtualization** - Full integration with oVirt/RHV, Proxmox, VMware, Hyper-V, and KVM
- **Lightweight & Portable** - Runs on NAS devices, Raspberry Pi, or small VMs
- **Vendor Neutral** - No lock-in to specific hardware or cloud providers
- **State Machine Driven** - Strict lifecycle management from discovery to retirement
- **Advanced Security** - Four-Eye Principle, RBAC, and comprehensive audit trails
- **Template-Based Deployment** - Rapid provisioning in under 5 minutes

## Supported Platforms

| Platform | Boot Method | OS Support |
|----------|-------------|------------|
| Bare-Metal Servers | BIOS/UEFI PXE | Ubuntu, Debian, Fedora, Rocky, Windows |
| Enterprise Laptops | BIOS/UEFI PXE | Windows (AD join), Linux |
| Hyper-V / VMware / Proxmox | PXE boot | Windows, Linux |
| oVirt/RHV VMs | API-driven | Linux, Windows |
| Raspberry Pi | Network boot | Raspberry Pi OS, Ubuntu ARM |
| Edge/IoT Devices | Network boot | Custom Linux |

## Node Lifecycle

```
discovered → pending → installing → installed → active → retired
                                                  ↓
                                            reprovision
```

## Quick Start

```bash
# Clone repository
git clone https://github.com/mrveiss/pureboot.git
cd pureboot

# Install dependencies
pip install -r requirements.txt

# Start database
docker-compose up -d db

# Run migrations
python -m scripts.migrate

# Start development server
uvicorn main:app --reload
```

## Documentation

All documentation is located in the [`docs/`](docs/) directory:

| Directory | Description |
|-----------|-------------|
| [docs/](docs/README.md) | Documentation index |
| [docs/PureBoot_Product_Requirements_Document.md](docs/PureBoot_Product_Requirements_Document.md) | Complete PRD v2.0 |
| [docs/architecture/](docs/architecture/) | System design and state machine |
| [docs/api/](docs/api/) | REST API documentation |
| [docs/guides/](docs/guides/) | User and developer guides |
| [docs/workflows/](docs/workflows/) | Provisioning workflow documentation |
| [docs/integrations/](docs/integrations/) | Hypervisor and third-party integrations |
| [docs/reference/](docs/reference/) | Technical reference materials |

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                        PureBoot Platform                       │
├─────────────────┬─────────────────┬─────────────────┬──────────┤
│  PXE/iPXE/UEFI  │  Controller API │   Web UI        │  Storage │
│  Infrastructure │  (Workflows,    │  (Management,   │  Backend │
│                 │   Templates)    │   Monitoring)   │          │
└─────────────────┴─────────────────┴─────────────────┴──────────┘
```

## Technology Stack

- **Backend:** Python / FastAPI
- **Database:** PostgreSQL (production) / SQLite (development)
- **Frontend:** React / Tailwind CSS
- **Infrastructure:** Docker / Kubernetes

## API Overview

```
GET    /api/v1/nodes              # List all nodes
POST   /api/v1/nodes              # Register new node
PATCH  /api/v1/nodes/{id}/state   # Transition state
GET    /api/v1/next?mac={mac}     # Get boot instructions
POST   /api/v1/report             # Node status reporting
```

See [API Documentation](docs/api/) for complete reference.

## Contributing

We welcome contributions! Please see our [Contributing Guide](docs/guides/contributing.md) for details.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'feat: add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

## License

This project is dual-licensed:

- **Free Tier (MIT)** - Personal, homelab, and educational use
- **Commercial License** - Business and enterprise use

See [LICENSE](LICENSE) for details.

## Support

- **GitHub Issues** - Bug reports and feature requests
- **Documentation** - [docs/](docs/)

## Roadmap

- [ ] Core PXE infrastructure
- [ ] Controller API with node management
- [ ] Web UI for monitoring
- [ ] Linux provisioning (Ubuntu/Debian)
- [ ] Windows provisioning with AD join
- [ ] Raspberry Pi network boot
- [ ] oVirt/RHV integration
- [ ] Advanced RBAC and audit logging

---

**Author:** Martins Veiss (mrveiss)

**Status:** Design/Planning Phase - Documentation Complete, Implementation Pending
