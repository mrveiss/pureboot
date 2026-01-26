# ARM64/Raspberry Pi Support Design

**Date:** 2026-01-26
**Issue:** [#77](https://github.com/mrveiss/pureboot/issues/77)
**Related:** [#6](https://github.com/mrveiss/pureboot/issues/6) (Raspberry Pi Network Boot)
**Status:** Design Complete

## Overview

Enable PureBoot to provision ARM64 devices including Raspberry Pi 4 (primary target) and other ARM SBCs. The design supports Pi 5 and other ARM devices in the future.

## Requirements

From GitHub issue #77:
- Raspberry Pi network boot (Pi 3B+, Pi 4, Pi 5)
- UEFI firmware for ARM devices
- ARM64 kernel and initramfs generation
- U-Boot integration for non-Pi ARM boards
- Device tree blob (DTB) management

## Supported Use Cases

1. **Raspberry Pi OS deployment** - Standard Pi OS installation to SD/USB
2. **Ubuntu ARM deployment** - Ubuntu Server for ARM64 (K3s clusters, etc.)
3. **Diskless/netboot operation** - Pi boots and runs entirely from network (NFS root)
4. **Custom OS images** - User-provided ARM64 disk images

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Target hardware | Pi 4 (primary), Pi 5 (future) | Most common, best documented |
| Node identification | Both serial + MAC | Serial for TFTP paths, MAC for network consistency |
| TFTP structure | Dedicated `/<serial>/` dirs | Follows Pi boot ROM expectations |
| State machine | Same as x86 | Consistency, reuse approval workflows |
| Deploy environment | Alpine Linux ARM64 | Matches x86 deploy env, minimal size |

## Pi Boot Flow

### How Raspberry Pi Network Boot Works

Unlike x86 PXE which uses DHCP options, Pi network boot:

1. **Pi ROM stage**: Boot ROM requests files via TFTP using serial number as path prefix
   - Pi 3: `<serial>/bootcode.bin`
   - Pi 4+: `<serial>/start4.elf` (bootcode.bin in EEPROM)

2. **GPU firmware stage**: GPU loads `start4.elf`, reads `config.txt` and `cmdline.txt`

3. **Kernel stage**: Linux kernel boots with parameters from `cmdline.txt`

### PureBoot Integration

```
┌─────────────────┐     TFTP: /<serial>/start4.elf
│   Raspberry Pi  │────────────────────────────────────►┌─────────────────┐
│   Boot ROM      │                                     │  PureBoot TFTP  │
└─────────────────┘                                     │     Server      │
        │                                               └─────────────────┘
        │ Loads GPU firmware                                    │
        ▼                                                       │
┌─────────────────┐     TFTP: /<serial>/config.txt              │
│   GPU Firmware  │◄────────────────────────────────────────────┘
│   (start4.elf)  │     TFTP: /<serial>/cmdline.txt
└─────────────────┘     TFTP: /<serial>/kernel8.img
        │
        │ Boots kernel with cmdline params
        ▼
┌─────────────────┐     HTTP: /api/v1/boot/pi?serial=xxx
│   Linux Kernel  │────────────────────────────────────►┌─────────────────┐
│   + Initramfs   │                                     │  PureBoot API   │
└─────────────────┘◄────────────────────────────────────└─────────────────┘
        │               Returns state-based instructions
        │
        ▼
┌─────────────────┐
│  Install/Boot   │
│  based on state │
└─────────────────┘
```

## Data Model Changes

### Node Model Updates

Existing fields (no changes needed):
- `arch`: Use `aarch64` for Pi
- `serial_number`: Primary Pi identifier
- `boot_mode`: Add `pi` value

New field:
```python
# In Node model
pi_model: Mapped[str | None] = mapped_column(String(20), nullable=True)
# Values: pi3b+, pi4, pi5, cm4, etc.
```

### Boot Mode Values

```python
# boot_mode field values
BOOT_MODES = ["bios", "uefi", "pi"]
```

## TFTP Directory Structure

### Shared Files

```
tftpboot/
├── rpi-firmware/                    # Shared Pi firmware (read-only)
│   ├── start4.elf                   # Pi 4 GPU firmware
│   ├── fixup4.dat                   # Pi 4 GPU firmware
│   ├── start4x.elf                  # Pi 4 64-bit GPU firmware
│   ├── fixup4x.dat                  # Pi 4 64-bit GPU firmware
│   ├── bcm2711-rpi-4-b.dtb          # Pi 4 device tree
│   ├── bcm2712-rpi-5-b.dtb          # Pi 5 device tree
│   └── overlays/                    # Device tree overlays
│       └── disable-bt.dtbo
├── deploy-arm64/                    # ARM64 deploy environment
│   ├── kernel8.img                  # ARM64 Linux kernel
│   └── initramfs.img                # Alpine ARM64 + PureBoot agent
```

### Per-Node Directories

Created dynamically when Pi node is registered:

```
tftpboot/
└── d83add36/                        # Pi serial number
    ├── start4.elf -> ../rpi-firmware/start4.elf
    ├── fixup4.dat -> ../rpi-firmware/fixup4.dat
    ├── bcm2711-rpi-4-b.dtb -> ../rpi-firmware/bcm2711-rpi-4-b.dtb
    ├── kernel8.img -> ../deploy-arm64/kernel8.img  (or custom)
    ├── initramfs.img -> ../deploy-arm64/initramfs.img
    ├── config.txt                   # Generated per-node
    └── cmdline.txt                  # Generated based on state
```

## Config File Generation

### config.txt (Per-Node)

Base template:
```ini
# PureBoot generated config for node {node_id}
# Serial: {serial}

arm_64bit=1
kernel=kernel8.img
initramfs initramfs.img followkernel

# Enable UART for console
enable_uart=1

# Disable splash for faster boot
disable_splash=1

# Device tree
dtparam=audio=off
```

### cmdline.txt (State-Dependent)

**Discovered state:**
```
ip=dhcp pureboot.server=http://192.168.1.10:8080 pureboot.serial={serial} pureboot.state=discovered console=ttyAMA0,115200
```

**Installing state (image deploy):**
```
ip=dhcp pureboot.server=http://192.168.1.10:8080 pureboot.node_id={id} pureboot.mac={mac} pureboot.mode=install pureboot.image_url={image_url} pureboot.target=/dev/mmcblk0 pureboot.callback=http://192.168.1.10:8080/api/v1/nodes/{id}/installed console=ttyAMA0,115200
```

**Active state (NFS diskless):**
```
root=/dev/nfs nfsroot=192.168.1.10:/nfsroot/{serial},vers=4,tcp ip=dhcp rw console=ttyAMA0,115200
```

**Active state (local boot):**
```
# cmdline.txt not used - Pi boots from local storage
# PureBoot returns empty/default config pointing to local boot
```

## API Changes

### New Endpoints

#### GET /api/v1/boot/pi

Called by Pi deploy environment to get boot instructions.

**Query Parameters:**
- `serial` (required): Pi serial number
- `mac` (optional): MAC address for registration

**Response:** Plain text boot instructions or JSON status

**Example:**
```
GET /api/v1/boot/pi?serial=d83add36&mac=dc:a6:32:12:34:56

Response (discovered):
{
  "state": "discovered",
  "message": "Node registered, awaiting workflow assignment"
}

Response (installing):
{
  "state": "installing",
  "action": "deploy_image",
  "image_url": "http://server/images/ubuntu-arm64.img",
  "target_device": "/dev/mmcblk0",
  "callback_url": "http://server/api/v1/nodes/{id}/installed"
}
```

#### POST /api/v1/nodes/register-pi

Register or update a Pi node.

**Request Body:**
```json
{
  "serial": "d83add36",
  "mac": "dc:a6:32:12:34:56",
  "model": "pi4",
  "ip_address": "192.168.1.100"
}
```

**Response:**
```json
{
  "success": true,
  "node_id": "uuid-here",
  "state": "discovered",
  "message": "Node registered"
}
```

### Modified Endpoints

#### GET /api/v1/nodes

No changes needed - already returns all nodes. Frontend can filter by `arch=aarch64`.

#### PATCH /api/v1/nodes/{id}

No changes needed - works for Pi nodes same as x86.

## Workflow Support

### Workflow Schema Updates

Add optional `arch` field:

```yaml
id: ubuntu-arm64-server
name: Ubuntu 24.04 ARM64 Server
arch: aarch64                        # New: restrict to ARM64 nodes
install_method: image
image_url: http://server/images/ubuntu-24.04-arm64.img
target_device: /dev/mmcblk0          # SD card
post_install:
  - resize_rootfs
```

### Install Methods for Pi

| Method | Description | Use Case |
|--------|-------------|----------|
| `image` | Stream disk image to target device | Custom images, Ubuntu |
| `nfs` | Extract rootfs to NFS share | Diskless clusters |
| `script` | Run custom install script | Raspberry Pi OS installer |

### Example Workflows

**Raspberry Pi OS:**
```yaml
id: pi-raspios
name: Raspberry Pi OS (64-bit)
arch: aarch64
install_method: image
image_url: http://server/images/raspios-arm64-lite.img.xz
target_device: /dev/mmcblk0
post_install:
  - enable_ssh
  - set_hostname
```

**Ubuntu ARM64:**
```yaml
id: pi-ubuntu-server
name: Ubuntu 24.04 Server ARM64
arch: aarch64
install_method: image
image_url: http://server/images/ubuntu-24.04-preinstalled-server-arm64.img.xz
target_device: /dev/mmcblk0
post_install:
  - resize_rootfs
  - cloud_init_setup
```

**Diskless K3s Worker:**
```yaml
id: pi-k3s-worker
name: K3s Worker (Diskless)
arch: aarch64
install_method: nfs
nfs_server: 192.168.1.10
nfs_base_path: /nfsroot
nfs_image: ubuntu-arm64-base.tar.gz
post_install:
  - script: install-k3s-agent.sh
    args: "--server https://k3s-server:6443"
```

## NFS Diskless Boot

### Directory Structure

```
/nfsroot/
├── base/                            # Base root filesystem (read-only)
│   └── ubuntu-arm64/
│       ├── bin/
│       ├── etc/
│       └── ...
└── nodes/                           # Per-node overlays
    └── d83add36/                    # Pi serial
        ├── etc/
        │   ├── hostname
        │   ├── machine-id
        │   └── network/
        └── var/
```

### NFS Export Configuration

```
# /etc/exports
/nfsroot/nodes 192.168.1.0/24(rw,sync,no_subtree_check,no_root_squash)
```

### Overlay Filesystem

For diskless nodes, use overlayfs to combine:
- Lower (read-only): `/nfsroot/base/ubuntu-arm64`
- Upper (read-write): `/nfsroot/nodes/<serial>`

This allows:
- Shared base image across all nodes
- Per-node configuration and state
- Easy updates by replacing base image

## Deploy Environment (Alpine ARM64)

### Components

Same structure as x86 deploy environment:

```
deploy-arm64/
├── kernel8.img              # Linux kernel (from Alpine)
├── initramfs.img            # Custom initramfs containing:
│   ├── /init                # PureBoot init script
│   ├── /usr/bin/curl        # For API calls
│   ├── /usr/bin/dd          # For image writing
│   ├── /usr/bin/xz          # For decompression
│   ├── /usr/bin/parted      # For partitioning
│   └── /etc/pureboot/       # Agent scripts
│       ├── agent.sh         # Main agent
│       ├── deploy-image.sh  # Image deployment
│       └── setup-nfs.sh     # NFS root setup
```

### Init Script Flow

```bash
#!/bin/sh
# /init in initramfs

# 1. Basic setup
mount -t proc proc /proc
mount -t sysfs sys /sys
mount -t devtmpfs dev /dev

# 2. Network setup
ip link set eth0 up
udhcpc -i eth0

# 3. Parse kernel cmdline
eval $(cat /proc/cmdline | tr ' ' '\n' | grep pureboot)

# 4. Report boot to PureBoot
curl -X POST "$pureboot_server/api/v1/nodes/$pureboot_node_id/event" \
  -d '{"event_type": "boot_started", "status": "success"}'

# 5. Get instructions from API
INSTRUCTIONS=$(curl "$pureboot_server/api/v1/boot/pi?serial=$pureboot_serial")

# 6. Execute based on state
case "$pureboot_mode" in
  install)
    /etc/pureboot/deploy-image.sh
    ;;
  nfs)
    /etc/pureboot/setup-nfs.sh
    ;;
  clone_source)
    /etc/pureboot/clone-server.sh
    ;;
esac
```

## Implementation Phases

### Phase 1: Core Infrastructure
**Scope:** Database and TFTP foundation

- [ ] Add `pi_model` field to Node model
- [ ] Add `pi` to boot_mode enum
- [ ] Create `PiManager` class for TFTP directory management
- [ ] Implement per-node directory creation/deletion
- [ ] Add Pi firmware files to TFTP root
- [ ] Basic config.txt generation

**Files:**
- `src/db/models.py` - Add pi_model field
- `src/pxe/pi_manager.py` - New: Pi TFTP management
- `src/config/settings.py` - Pi firmware paths

### Phase 2: API & Registration
**Scope:** Pi boot endpoints and node registration

- [ ] `GET /api/v1/boot/pi` endpoint
- [ ] `POST /api/v1/nodes/register-pi` endpoint
- [ ] Dynamic cmdline.txt generation based on state
- [ ] Link serial numbers to MAC addresses
- [ ] Auto-discovery of Pi nodes via TFTP requests

**Files:**
- `src/api/routes/boot_pi.py` - New: Pi boot endpoints
- `src/api/routes/nodes.py` - Add register-pi endpoint

### Phase 3: Deploy Environment
**Scope:** ARM64 Alpine Linux initramfs

- [ ] Build Alpine ARM64 kernel + initramfs
- [ ] Port PureBoot agent scripts to ARM64
- [ ] Test boot on Pi 4 hardware
- [ ] Image deployment workflow (curl | dd)
- [ ] Progress reporting to API

**Files:**
- `deploy/build-arm64-initramfs.sh` - Build script
- `deploy/arm64/` - ARM64 specific scripts

### Phase 4: Diskless/NFS Support
**Scope:** NFS root filesystem management

- [ ] NFS storage backend type
- [ ] Per-node NFS directory provisioning
- [ ] `install_method: nfs` workflow support
- [ ] Overlay filesystem setup
- [ ] Persistent vs stateless modes

**Files:**
- `src/core/nfs_manager.py` - New: NFS root management
- `workflows/examples/pi-diskless-nfs.yaml`

### Phase 5: OS Installers
**Scope:** Full OS deployment workflows

- [ ] Raspberry Pi OS image deployment
- [ ] Ubuntu ARM64 cloud-init integration
- [ ] Custom image support
- [ ] Post-install script execution
- [ ] First-boot configuration

**Files:**
- `workflows/examples/pi-raspios.yaml`
- `workflows/examples/pi-ubuntu-arm64.yaml`

## Testing Strategy

### Unit Tests
- Pi directory creation/deletion
- Config.txt generation
- Cmdline.txt generation for each state
- Serial number validation

### Integration Tests
- API endpoint responses
- Node registration flow
- State transitions for Pi nodes

### Hardware Tests (Pi 4)
- Network boot from PureBoot TFTP
- Deploy environment boot
- Image deployment to SD card
- NFS root boot
- Full provisioning cycle

## Security Considerations

1. **TFTP is unencrypted** - Same as x86 PXE, network should be isolated
2. **Serial numbers are predictable** - Don't use for authentication
3. **NFS root security** - Use NFSv4 with proper access controls
4. **Deploy environment** - Runs as root, limit network exposure

## Future Enhancements

- **Pi 5 support** - Different device tree, PCIe boot
- **Compute Module 4** - eMMC boot, carrier board variants
- **U-Boot support** - For non-Pi ARM boards (Rock Pi, etc.)
- **UEFI boot** - For ARM servers with standard UEFI
- **Secure boot** - Pi 4 secure boot chain

## References

- [Raspberry Pi Network Boot](https://www.raspberrypi.com/documentation/computers/remote-access.html#network-boot-your-raspberry-pi)
- [Pi 4 Boot EEPROM](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#raspberry-pi-4-boot-eeprom)
- [Alpine Linux ARM](https://wiki.alpinelinux.org/wiki/Raspberry_Pi)
- [PureBoot PRD - ARM Support](docs/PureBoot_Product_Requirements_Document.md)
