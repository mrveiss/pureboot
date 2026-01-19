# Integrations

This directory contains documentation for third-party integrations.

## Contents

### Hypervisor Integrations

- [oVirt_Integration.md](oVirt_Integration.md) - oVirt/RHV enterprise virtualization
- [proxmox.md](proxmox.md) - Proxmox VE integration
- [hyper-v.md](hyper-v.md) - Microsoft Hyper-V integration
- [vmware.md](vmware.md) - VMware ESXi/vSphere integration
- [kvm-libvirt.md](kvm-libvirt.md) - KVM/Libvirt integration

### Configuration Management

- [ansible.md](ansible.md) - Ansible integration
- [saltstack.md](saltstack.md) - SaltStack integration

### Monitoring

- [prometheus.md](prometheus.md) - Prometheus metrics
- [grafana.md](grafana.md) - Grafana dashboards

## Supported Hypervisors

| Hypervisor | Integration Level | Capabilities |
|------------|-------------------|--------------|
| oVirt/RHV | Full API | VM creation, HA, live migration, storage domains |
| Proxmox VE | Full API | VM/container creation, template management |
| KVM/Libvirt | Full API | VM lifecycle, storage management |
| Hyper-V | Full API | VM creation, PXE boot, template cloning |
| VMware ESXi | Partial API | VM creation, basic management |

## Integration Capabilities

All hypervisor integrations support:

- **VM Creation** - Instantiate new virtual machines
- **Template Cloning** - Fast deployment from golden images
- **Storage Management** - Attach/detach disks and ISOs
- **Network Configuration** - Configure virtual networks
- **Power Management** - Start/stop/reset VMs
- **PXE Boot Triggering** - Force VMs to PXE boot

### oVirt/RHV Additional Features

- Live migration between hosts
- High availability configuration
- Storage domain management
- Advanced networking features

See individual integration files for setup instructions and examples.
