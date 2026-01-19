# Provisioning Workflows

This directory contains documentation for provisioning workflows.

## Contents

- [linux-provisioning.md](linux-provisioning.md) - Linux distribution provisioning
- [windows-provisioning.md](windows-provisioning.md) - Windows with AD join
- [raspberry-pi.md](raspberry-pi.md) - Raspberry Pi and ARM SBC provisioning
- [kubernetes.md](kubernetes.md) - Kubernetes node provisioning
- [custom-workflows.md](custom-workflows.md) - Creating custom workflows

## Workflow Overview

### Supported Platforms

| Platform | Boot Method | Supported OS |
|----------|-------------|--------------|
| Bare-Metal Servers | BIOS/UEFI PXE | Ubuntu, Debian, Fedora, Rocky, Windows |
| Enterprise Laptops | BIOS/UEFI PXE | Windows (AD join), Linux |
| Hyper-V VMs | PXE boot | Windows, Linux |
| Proxmox/KVM VMs | PXE boot | Linux, Windows |
| oVirt/RHV VMs | API-driven | Linux, Windows |
| Raspberry Pi | Network boot | Raspberry Pi OS, Ubuntu ARM |

### Workflow Definition Format

```yaml
name: example-workflow
description: Example provisioning workflow
tasks:
  - type: pxe_boot
    bootloader: grub
    kernel: /tftp/ubuntu/vmlinuz
    initrd: /tftp/ubuntu/initrd
    cmdline: "ip=dhcp url=http://pureboot.local/ubuntu.iso"

  - type: image_deploy
    image: /templates/ubuntu.tar.gz
    target: /dev/sda

  - type: script_run
    script: /scripts/post-install.sh

  - type: reboot
    delay: 10

  - type: chain_boot
    method: grub
    target: (hd0)+1
```

### Task Types

| Task Type | Description |
|-----------|-------------|
| pxe_boot | Serve boot files |
| image_deploy | Deploy OS image |
| disk_wipe | Secure disk erasure |
| partition | Disk partitioning |
| domain_join | AD integration |
| script_run | Custom scripts |
| package_install | Software packages |
| reboot | System restart |
| chain_boot | Bootloader chain |
| ovirt_vm_create | oVirt VM provisioning |

See individual workflow files for detailed examples and configurations.
