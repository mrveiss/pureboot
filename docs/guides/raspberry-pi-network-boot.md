# Raspberry Pi Network Boot Guide

This guide covers setting up Raspberry Pi devices for network boot with PureBoot.

## Supported Models

| Model | Network Boot | SD Card Required | Setup |
|-------|--------------|------------------|-------|
| Pi 3B | Yes | One-time setup only | OTP programming required |
| Pi 3B+ | Yes | No | Ready out of box |
| CM3 | Yes | One-time setup only | OTP programming required |
| Pi 4 | Yes | No | Ready out of box |
| Pi 5 | Yes | No | Ready out of box |

## How It Works

Raspberry Pi network boot uses TFTP to load firmware and kernel files:

1. Pi powers on and looks for boot files via TFTP
2. Pi requests files using its serial number as the path: `/<serial>/`
3. PureBoot serves `bootcode.bin`, firmware, kernel, and config files
4. Pi boots the PureBoot deploy environment
5. Deploy environment contacts PureBoot API for instructions
6. OS is installed to SD card, NVMe, or runs diskless via NFS

## Pi 3B vs Pi 3B+ vs Pi 4/5

### Pi 3B - Requires One-Time Setup

Pi 3B does **not** have network boot enabled by default. You must program the OTP (One-Time Programmable) fuse to enable it.

**Setup Steps:**

1. Create an SD card with a single FAT32 partition
2. Add a `config.txt` file with this content:
   ```
   program_usb_boot_mode=1
   ```
3. Insert SD card into Pi 3B and power on
4. Wait 10+ seconds for OTP to be programmed
5. Power off and remove SD card
6. Pi 3B can now network boot permanently

**Verification:**
```bash
# On a running Pi 3B, check if OTP is programmed:
vcgencmd otp_dump | grep 17:
# Should show: 17:3020000a (bit 29 set = USB boot enabled)
```

> **Note:** This is permanent and cannot be undone. The Pi will still boot from SD card if one is present.

### Pi 3B+ - Ready Out of Box

Pi 3B+ has network boot enabled by default in the boot ROM. No setup required.

Just connect to network with DHCP and PureBoot TFTP server running.

### Pi 4 and Pi 5 - Ready Out of Box

Pi 4 and Pi 5 have network boot capability in the EEPROM bootloader. Recent firmware has it enabled by default.

**Check/Enable on Pi 4:**
```bash
# Check current boot order
rpi-eeprom-config

# If needed, update to enable network boot
sudo rpi-eeprom-config --edit
# Set: BOOT_ORDER=0xf241  (network boot after SD, USB)
```

## Firmware Requirements

PureBoot needs the following firmware files in the TFTP directory:

### For Pi 3/3B+/CM3

```
/tftp/rpi-firmware/
├── bootcode.bin      # First-stage bootloader (required!)
├── start.elf         # GPU firmware
├── fixup.dat         # Memory configuration
├── bcm2710-rpi-3-b.dtb       # Pi 3B device tree
├── bcm2710-rpi-3-b-plus.dtb  # Pi 3B+ device tree
└── bcm2710-rpi-cm3.dtb       # CM3 device tree
```

### For Pi 4/5

```
/tftp/rpi-firmware/
├── start4.elf        # GPU firmware (Pi 4/5)
├── fixup4.dat        # Memory configuration
├── bcm2711-rpi-4-b.dtb       # Pi 4 device tree
└── bcm2712-rpi-5-b.dtb       # Pi 5 device tree
```

> **Important:** Pi 3 requires `bootcode.bin` from TFTP. Pi 4/5 have it built into the EEPROM.

### Download Firmware

Get official firmware from the Raspberry Pi GitHub:
```bash
git clone --depth 1 https://github.com/raspberrypi/firmware
cp firmware/boot/bootcode.bin /srv/tftp/rpi-firmware/
cp firmware/boot/start*.elf /srv/tftp/rpi-firmware/
cp firmware/boot/fixup*.dat /srv/tftp/rpi-firmware/
cp firmware/boot/*.dtb /srv/tftp/rpi-firmware/
```

## DHCP Configuration

Your DHCP server must provide the TFTP server address. Example for dnsmasq:

```conf
# Enable TFTP
enable-tftp
tftp-root=/srv/tftp

# Pi-specific boot file (uses serial number path)
# Pi requests: /<serial>/bootcode.bin (Pi 3) or /<serial>/start4.elf (Pi 4/5)
pxe-service=0,"Raspberry Pi Boot"
```

For ISC DHCP:
```conf
if exists vendor-class-identifier {
  if substring(option vendor-class-identifier, 0, 10) = "PXEClient" {
    next-server 192.168.1.10;  # PureBoot server IP
  }
}
```

## PureBoot Configuration

Configure Pi settings in PureBoot's `config/settings.py`:

```python
class PiSettings(BaseSettings):
    firmware_dir: str = "/srv/tftp/rpi-firmware"
    deploy_dir: str = "/srv/tftp/deploy-arm64"
    nodes_dir: str = "/srv/tftp/pi-nodes"
```

## Auto-Discovery (No Pre-Registration Required)

PureBoot supports automatic discovery of unknown Pi devices. When a Pi with an unregistered serial number attempts to network boot, PureBoot serves boot files from a discovery directory instead of rejecting the request.

### How It Works

1. **Unknown Pi boots** - TFTP request comes in with path `/<serial>/start4.elf`
2. **PureBoot detects Pi request** - Combined detection: 8-hex-char serial + known boot file
3. **Fallback to discovery directory** - Since serial isn't registered, PureBoot serves from `/tftp/pi-discovery/`
4. **Pi boots into discovery environment** - cmdline.txt includes `pureboot.mode=discovery`
5. **Deploy environment registers Pi** - Calls `/api/v1/boot/pi?mode=discovery&serial=...`
6. **PureBoot creates node directory** - `/tftp/pi-nodes/<serial>/` is created
7. **Next boot uses registered config** - Subsequent boots use node-specific files

### Configuration

Enable/disable auto-discovery in your settings:

```python
# src/config/settings.py
class PiSettings(BaseSettings):
    discovery_enabled: bool = True  # Enable Pi auto-discovery
    discovery_dir: Path = Path("./tftp/pi-discovery")
    discovery_default_model: str = "pi4"  # Assumed model for discovery
```

Or via environment variables:

```bash
PUREBOOT_PI__DISCOVERY_ENABLED=true
PUREBOOT_PI__DISCOVERY_DIR=/srv/tftp/pi-discovery
PUREBOOT_PI__DISCOVERY_DEFAULT_MODEL=pi4
```

### Discovery Directory Contents

The discovery directory (`/tftp/pi-discovery/`) is automatically populated with:

```
/tftp/pi-discovery/
├── bootcode.bin → ../rpi-firmware/bootcode.bin  # For Pi 3
├── start.elf → ../rpi-firmware/start.elf        # For Pi 3
├── start4.elf → ../rpi-firmware/start4.elf      # For Pi 4/5
├── fixup.dat → ../rpi-firmware/fixup.dat
├── fixup4.dat → ../rpi-firmware/fixup4.dat
├── kernel8.img → ../deploy-arm64/kernel8.img
├── initramfs.img → ../deploy-arm64/initramfs.img
├── bcm2710-rpi-3-b.dtb → ...
├── bcm2711-rpi-4-b.dtb → ...
├── config.txt                                    # Generic config for all models
└── cmdline.txt                                   # Includes pureboot.mode=discovery
```

### Benefits

- **Zero pre-configuration** - No need to register Pi serial numbers before first boot
- **Plug and play** - Connect a new Pi to the network and it registers itself
- **Model detection** - Pi model is detected during registration and config updated
- **Secure** - Auto-registration can be disabled if strict control is required

## Provisioning Workflow

1. **Discovery:** Pi boots (auto-discovery or pre-registered), contacts PureBoot, gets registered with serial number
2. **Pending:** Assign a workflow (Ubuntu, Raspberry Pi OS, NFS diskless)
3. **Installing:** Pi reboots, PureBoot provides install parameters
4. **Installed:** OS written to storage, Pi reports completion
5. **Active:** Pi boots from local storage

## Available Workflows

| Workflow | Description |
|----------|-------------|
| `pi-ubuntu-arm64.yaml` | Ubuntu Server 24.04 LTS ARM64 |
| `pi-raspios-lite.yaml` | Raspberry Pi OS Lite 64-bit |
| `pi-diskless-nfs.yaml` | NFS root (no local storage) |
| `pi-k3s-worker.yaml` | K3s cluster worker (diskless) |

## Troubleshooting

### Pi 3B won't network boot

1. Verify OTP is programmed: `vcgencmd otp_dump | grep 17:`
2. Check `bootcode.bin` exists in TFTP path
3. Verify DHCP provides TFTP server address

### Pi 4/5 won't network boot

1. Check EEPROM boot order: `rpi-eeprom-config`
2. Update EEPROM if needed: `sudo rpi-eeprom-update`
3. Verify `start4.elf` exists in TFTP path

### Pi boots but doesn't contact PureBoot

1. Check network connectivity from Pi
2. Verify `cmdline.txt` has correct `pureboot.url`
3. Check PureBoot API is accessible

### Wrong device tree loaded

1. Verify correct model is set in PureBoot
2. Check DTB file exists for your Pi model
3. Verify `config.txt` references correct DTB

## Serial Number Reference

Pi serial numbers are 8 hex characters. Find yours:

```bash
# On a running Pi:
cat /proc/cpuinfo | grep Serial
# Output: Serial          : 10000000d83add36
# Use last 8 chars: d83add36
```

PureBoot creates per-node directories at `/tftp/pi-nodes/<serial>/` containing:
- Symlinks to firmware files
- Generated `config.txt`
- Generated `cmdline.txt` with boot parameters

## See Also

- [ARM64 Design Document](../plans/2026-01-26-arm64-raspberry-pi-design.md)
- [NFS Diskless Boot](../workflows/README.md)
- [Workflow Configuration](../workflows/README.md)
