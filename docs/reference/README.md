# Reference Documentation

This directory contains technical reference materials for PureBoot.

## Contents

- [bootloaders.md](bootloaders.md) - Bootloader configuration reference
- [templates.md](templates.md) - Template formats and usage
- [state-transitions.md](state-transitions.md) - Valid state machine transitions
- [troubleshooting.md](troubleshooting.md) - Common issues and solutions
- [glossary.md](glossary.md) - Terminology and definitions

## State Machine Reference

### States

| State | Description |
|-------|-------------|
| discovered | Node appeared via PXE, waiting for admin action |
| pending | Workflow assigned, ready for next PXE boot |
| installing | OS installation in progress |
| installed | Installation complete, ready for local boot |
| active | Running from local disk |
| reprovision | Marked for reinstallation |
| retired | Removed from inventory |
| deprovisioning | Secure data erasure in progress |
| migrating | Hardware replacement workflow |

### Valid Transitions

```
discovered → pending
pending → installing
installing → installed
installed → active
active → reprovision → pending
active → deprovisioning → retired
active → migrating → active (new hardware)
any → retired
```

## Boot Behavior Rules

1. **Rule A:** PXE boot mandatory only during installation
2. **Rule B:** Post-install returns "boot from local disk"
3. **Rule C:** Reinstallations only on explicit admin request
4. **Rule D:** Offline resilience - nodes boot locally if network unavailable
5. **Rule E:** Provisioning-only DHCP - only provisioning states get DHCP

## Bootloader Commands

| Bootloader | Local Boot Command |
|------------|-------------------|
| PXELINUX | `LOCALBOOT 0` |
| iPXE | `sanboot --drive 0x80` |
| GRUB | `chainloader (hd0)+1` |

See individual reference files for detailed information.
