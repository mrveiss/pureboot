# ARM64/Raspberry Pi Phase 5: OS Installers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete OS deployment workflows with post-install configuration support

**Architecture:** Add post-install script execution to deploy scripts, create cloud-init integration for Ubuntu ARM64, and add Raspberry Pi OS specific workflow support.

**Tech Stack:** Shell scripts, YAML workflows, cloud-init

---

## Task 1: Add Post-Install Script Support to Pi Image Script

**Files:**
- Modify: `deploy/scripts/pureboot-pi-image.sh`

**Step 1: Add post-install script execution**

Add function to download and run post-install scripts:

```bash
# Run post-install scripts from workflow
run_post_install() {
    if [[ -z "${PUREBOOT_POST_SCRIPT}" ]]; then
        log "No post-install script configured"
        return 0
    fi

    log "Running post-install script..."

    # Mount the target filesystem
    local mount_point="/mnt/target"
    mkdir -p "${mount_point}"

    # Find and mount root partition
    local root_part
    root_part=$(find_root_partition "${PUREBOOT_TARGET}")

    if [[ -z "${root_part}" ]]; then
        log_warn "Could not find root partition for post-install"
        return 1
    fi

    mount "${root_part}" "${mount_point}" || {
        log_error "Failed to mount root partition"
        return 1
    }

    # Download and run script
    local script_file="/tmp/post-install.sh"
    if curl -sfL "${PUREBOOT_POST_SCRIPT}" -o "${script_file}"; then
        chmod +x "${script_file}"

        # Run in chroot if possible
        if [[ -d "${mount_point}/bin" ]]; then
            cp "${script_file}" "${mount_point}/tmp/"
            chroot "${mount_point}" /tmp/post-install.sh || log_warn "Post-install script returned non-zero"
            rm -f "${mount_point}/tmp/post-install.sh"
        else
            "${script_file}" "${mount_point}" || log_warn "Post-install script returned non-zero"
        fi

        log "Post-install script completed"
    else
        log_error "Failed to download post-install script"
    fi

    umount "${mount_point}"
    return 0
}

# Find root partition on target device
find_root_partition() {
    local device="$1"
    local part_prefix="${device}"

    # Handle partition naming
    if is_sd_card "${device}" || [[ "${device}" == /dev/nvme* ]]; then
        part_prefix="${device}p"
    fi

    # Try common root partition numbers (2 for Pi, 1 for simple images)
    for num in 2 1 3; do
        local part="${part_prefix}${num}"
        if [[ -b "${part}" ]]; then
            local fstype
            fstype=$(blkid -o value -s TYPE "${part}" 2>/dev/null)
            if [[ "${fstype}" =~ ^(ext4|ext3|btrfs|xfs)$ ]]; then
                echo "${part}"
                return 0
            fi
        fi
    done

    return 1
}
```

**Step 2: Commit**

```bash
git add deploy/scripts/pureboot-pi-image.sh
git commit -m "feat: add post-install script support to Pi image deployment"
```

---

## Task 2: Add Cloud-Init Support for Ubuntu ARM64

**Files:**
- Create: `deploy/scripts/pureboot-cloud-init.sh`

**Step 1: Create cloud-init configuration helper**

```bash
#!/bin/bash
# PureBoot Cloud-Init Configuration Helper
# Configures cloud-init for first-boot setup on deployed images

set -e

# Source common functions if available
if [[ -f /usr/local/bin/pureboot-common.sh ]]; then
    source /usr/local/bin/pureboot-common.sh
else
    log() { echo "[$(date '+%H:%M:%S')] $*"; }
    log_error() { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }
fi

# =============================================================================
# Cloud-Init Configuration
# =============================================================================

# Configure cloud-init on mounted filesystem
# Usage: configure_cloud_init <mount_point> <hostname> [ssh_keys...]
configure_cloud_init() {
    local mount_point="$1"
    local hostname="${2:-}"
    shift 2 || true
    local ssh_keys=("$@")

    local cloud_init_dir="${mount_point}/etc/cloud/cloud.cfg.d"
    local nocloud_dir="${mount_point}/var/lib/cloud/seed/nocloud"

    # Check if cloud-init exists on target
    if [[ ! -d "${mount_point}/etc/cloud" ]]; then
        log "Cloud-init not found on target, skipping configuration"
        return 0
    fi

    log "Configuring cloud-init..."

    # Create directories
    mkdir -p "${cloud_init_dir}"
    mkdir -p "${nocloud_dir}"

    # Disable cloud-init network config (we configure via other means)
    cat > "${cloud_init_dir}/99-pureboot.cfg" << 'CLOUDINIT'
# PureBoot cloud-init configuration
# Disable network config - handled by systemd-networkd or dhcpcd
network:
  config: disabled

# Disable some modules for faster boot
cloud_init_modules:
  - bootcmd
  - write-files
  - growpart
  - resizefs
  - set_hostname
  - update_hostname
  - users-groups
  - ssh

cloud_config_modules:
  - runcmd
  - ssh-import-id
  - keyboard
  - locale
  - set-passwords
  - ntp

cloud_final_modules:
  - package-update-upgrade-install
  - scripts-vendor
  - scripts-per-once
  - scripts-per-boot
  - scripts-per-instance
  - scripts-user
  - phone-home
  - final-message
CLOUDINIT

    # Create NoCloud seed for local datasource
    create_nocloud_seed "${nocloud_dir}" "${hostname}" "${ssh_keys[@]}"

    log "Cloud-init configured"
}

# Create NoCloud seed files
create_nocloud_seed() {
    local nocloud_dir="$1"
    local hostname="${2:-}"
    shift 2 || true
    local ssh_keys=("$@")

    # Create meta-data
    cat > "${nocloud_dir}/meta-data" << EOF
instance-id: $(cat /proc/sys/kernel/random/uuid)
local-hostname: ${hostname:-pureboot-node}
EOF

    # Create user-data
    cat > "${nocloud_dir}/user-data" << EOF
#cloud-config
# PureBoot generated cloud-init user-data

# Set hostname
hostname: ${hostname:-pureboot-node}
manage_etc_hosts: true

# Expand root filesystem
growpart:
  mode: auto
  devices: ['/']

resize_rootfs: true

# Configure default user
users:
  - name: ubuntu
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    lock_passwd: false
EOF

    # Add SSH keys if provided
    if [[ ${#ssh_keys[@]} -gt 0 ]]; then
        cat >> "${nocloud_dir}/user-data" << EOF
    ssh_authorized_keys:
EOF
        for key in "${ssh_keys[@]}"; do
            echo "      - ${key}" >> "${nocloud_dir}/user-data"
        done
    fi

    # Add package updates
    cat >> "${nocloud_dir}/user-data" << EOF

# Update packages on first boot
package_update: true
package_upgrade: false

# Final message
final_message: "PureBoot provisioning complete after \$UPTIME seconds"
EOF
}

# Disable cloud-init after first boot (optional)
disable_cloud_init_after_first_boot() {
    local mount_point="$1"

    # Create a script that runs on first boot to disable cloud-init
    local script_dir="${mount_point}/var/lib/cloud/scripts/per-once"
    mkdir -p "${script_dir}"

    cat > "${script_dir}/99-disable-cloud-init.sh" << 'SCRIPT'
#!/bin/bash
# Disable cloud-init after first boot
touch /etc/cloud/cloud-init.disabled
echo "Cloud-init disabled after first boot by PureBoot"
SCRIPT
    chmod +x "${script_dir}/99-disable-cloud-init.sh"
}

# Set hostname on target filesystem
set_target_hostname() {
    local mount_point="$1"
    local hostname="$2"

    if [[ -z "${hostname}" ]]; then
        return 0
    fi

    log "Setting hostname to: ${hostname}"

    echo "${hostname}" > "${mount_point}/etc/hostname"

    # Update /etc/hosts
    if [[ -f "${mount_point}/etc/hosts" ]]; then
        sed -i "s/127.0.1.1.*/127.0.1.1\t${hostname}/" "${mount_point}/etc/hosts"
    fi
}

# Enable SSH on target (for images that have it disabled by default)
enable_ssh() {
    local mount_point="$1"

    # For Raspberry Pi OS - create ssh file in boot partition
    if [[ -d "${mount_point}/boot/firmware" ]]; then
        touch "${mount_point}/boot/firmware/ssh"
        log "SSH enabled via boot flag"
    elif [[ -d "${mount_point}/boot" ]]; then
        touch "${mount_point}/boot/ssh"
        log "SSH enabled via boot flag"
    fi

    # For systemd systems - enable sshd service
    if [[ -d "${mount_point}/etc/systemd/system" ]]; then
        mkdir -p "${mount_point}/etc/systemd/system/multi-user.target.wants"
        if [[ -f "${mount_point}/lib/systemd/system/ssh.service" ]]; then
            ln -sf /lib/systemd/system/ssh.service \
                "${mount_point}/etc/systemd/system/multi-user.target.wants/ssh.service" 2>/dev/null || true
        elif [[ -f "${mount_point}/lib/systemd/system/sshd.service" ]]; then
            ln -sf /lib/systemd/system/sshd.service \
                "${mount_point}/etc/systemd/system/multi-user.target.wants/sshd.service" 2>/dev/null || true
        fi
    fi
}

# Main function for standalone use
main() {
    local mount_point="$1"
    local hostname="$2"
    shift 2 || true
    local ssh_keys=("$@")

    if [[ -z "${mount_point}" ]]; then
        echo "Usage: $0 <mount_point> <hostname> [ssh_key1] [ssh_key2] ..."
        exit 1
    fi

    configure_cloud_init "${mount_point}" "${hostname}" "${ssh_keys[@]}"
    set_target_hostname "${mount_point}" "${hostname}"
    enable_ssh "${mount_point}"
}

# Run main if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
```

**Step 2: Commit**

```bash
chmod +x deploy/scripts/pureboot-cloud-init.sh
git add deploy/scripts/pureboot-cloud-init.sh
git commit -m "feat: add cloud-init configuration helper for Ubuntu ARM64"
```

---

## Task 3: Create Raspberry Pi OS Specific Support

**Files:**
- Create: `deploy/scripts/pureboot-raspios-config.sh`

**Step 1: Create Raspberry Pi OS configuration helper**

```bash
#!/bin/bash
# PureBoot Raspberry Pi OS Configuration Helper
# Configures Raspberry Pi OS specific settings

set -e

if [[ -f /usr/local/bin/pureboot-common.sh ]]; then
    source /usr/local/bin/pureboot-common.sh
else
    log() { echo "[$(date '+%H:%M:%S')] $*"; }
fi

# =============================================================================
# Raspberry Pi OS Configuration
# =============================================================================

# Configure Raspberry Pi OS on mounted filesystem
configure_raspios() {
    local mount_point="$1"
    local hostname="${2:-}"
    local wifi_ssid="${3:-}"
    local wifi_pass="${4:-}"
    local wifi_country="${5:-US}"

    local boot_dir="${mount_point}/boot"
    [[ -d "${mount_point}/boot/firmware" ]] && boot_dir="${mount_point}/boot/firmware"

    log "Configuring Raspberry Pi OS..."

    # Enable SSH
    touch "${boot_dir}/ssh"
    log "SSH enabled"

    # Set hostname
    if [[ -n "${hostname}" ]]; then
        echo "${hostname}" > "${mount_point}/etc/hostname"
        sed -i "s/raspberrypi/${hostname}/g" "${mount_point}/etc/hosts" 2>/dev/null || true
        log "Hostname set to: ${hostname}"
    fi

    # Configure WiFi if credentials provided
    if [[ -n "${wifi_ssid}" && -n "${wifi_pass}" ]]; then
        configure_wifi "${boot_dir}" "${wifi_ssid}" "${wifi_pass}" "${wifi_country}"
    fi

    # Disable initial setup wizard
    disable_piwiz "${mount_point}"

    log "Raspberry Pi OS configured"
}

# Configure WiFi via wpa_supplicant.conf
configure_wifi() {
    local boot_dir="$1"
    local ssid="$2"
    local pass="$3"
    local country="${4:-US}"

    cat > "${boot_dir}/wpa_supplicant.conf" << EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=${country}

network={
    ssid="${ssid}"
    psk="${pass}"
    key_mgmt=WPA-PSK
}
EOF
    log "WiFi configured for SSID: ${ssid}"
}

# Disable the Raspberry Pi OS first-boot wizard
disable_piwiz() {
    local mount_point="$1"

    # Remove piwiz from autostart
    local autostart="${mount_point}/etc/xdg/autostart/piwiz.desktop"
    [[ -f "${autostart}" ]] && rm -f "${autostart}"

    # Create flag file to indicate setup is complete
    touch "${mount_point}/etc/pureboot-configured"
}

# Set default user password (hashed)
set_user_password() {
    local mount_point="$1"
    local username="$2"
    local password="$3"

    if [[ -z "${password}" ]]; then
        return 0
    fi

    # Generate password hash
    local hash
    hash=$(openssl passwd -6 "${password}")

    # Update shadow file
    if [[ -f "${mount_point}/etc/shadow" ]]; then
        sed -i "s|^${username}:[^:]*:|${username}:${hash}:|" "${mount_point}/etc/shadow"
        log "Password set for user: ${username}"
    fi
}

# Create userconf.txt for Raspberry Pi OS headless setup
create_userconf() {
    local boot_dir="$1"
    local username="${2:-pi}"
    local password="$3"

    if [[ -z "${password}" ]]; then
        return 0
    fi

    # Generate password hash
    local hash
    hash=$(openssl passwd -6 "${password}")

    echo "${username}:${hash}" > "${boot_dir}/userconf.txt"
    log "Created userconf.txt for user: ${username}"
}

# Add SSH authorized keys
add_ssh_keys() {
    local mount_point="$1"
    local username="$2"
    shift 2
    local keys=("$@")

    if [[ ${#keys[@]} -eq 0 ]]; then
        return 0
    fi

    local ssh_dir="${mount_point}/home/${username}/.ssh"
    mkdir -p "${ssh_dir}"

    for key in "${keys[@]}"; do
        echo "${key}" >> "${ssh_dir}/authorized_keys"
    done

    chmod 700 "${ssh_dir}"
    chmod 600 "${ssh_dir}/authorized_keys"

    # Fix ownership (uid/gid 1000 is typically the first user)
    chown -R 1000:1000 "${ssh_dir}"

    log "Added ${#keys[@]} SSH key(s) for user: ${username}"
}

# Main function
main() {
    local mount_point="$1"
    local hostname="${2:-}"

    if [[ -z "${mount_point}" ]]; then
        echo "Usage: $0 <mount_point> [hostname]"
        exit 1
    fi

    configure_raspios "${mount_point}" "${hostname}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
```

**Step 2: Commit**

```bash
chmod +x deploy/scripts/pureboot-raspios-config.sh
git add deploy/scripts/pureboot-raspios-config.sh
git commit -m "feat: add Raspberry Pi OS configuration helper"
```

---

## Task 4: Update Build Script to Include New Scripts

**Files:**
- Modify: `deploy/build-arm64-deploy-image.sh`

**Step 1: Add new scripts to the build**

Add the new scripts to the copy section:

```bash
# Copy configuration helpers
cp "${SCRIPT_DIR}/scripts/pureboot-cloud-init.sh" "${ROOTFS_DIR}/usr/local/bin/"
cp "${SCRIPT_DIR}/scripts/pureboot-raspios-config.sh" "${ROOTFS_DIR}/usr/local/bin/"
chmod +x "${ROOTFS_DIR}/usr/local/bin/pureboot-cloud-init.sh"
chmod +x "${ROOTFS_DIR}/usr/local/bin/pureboot-raspios-config.sh"
```

**Step 2: Commit**

```bash
git add deploy/build-arm64-deploy-image.sh
git commit -m "feat: include OS configuration helpers in ARM64 initramfs"
```

---

## Task 5: Create Additional Example Workflows

**Files:**
- Create: `workflows/pi-raspios-lite.yaml`

**Step 1: Create Raspberry Pi OS Lite workflow**

```yaml
# Pi Raspberry Pi OS Lite
# Deploys Raspberry Pi OS Lite (64-bit) with headless configuration

id: pi-raspios-lite
name: Raspberry Pi OS Lite (64-bit)
description: Minimal Raspberry Pi OS for headless servers
version: "1.0"
arch: aarch64
install_method: image

image_url: "{{ image_url | default('http://pureboot.local/images/raspios-bookworm-arm64-lite.img.xz') }}"
target_device: "{{ target_device | default('/dev/mmcblk0') }}"

boot_params:
  resize_rootfs: true

post_install:
  - name: Enable SSH
    enabled: true
  - name: Set hostname
    enabled: true
    hostname: "{{ hostname | default('pi-{{ serial }}') }}"
  - name: Configure user
    enabled: "{{ user_password is defined }}"
    username: "{{ username | default('pi') }}"
    password: "{{ user_password }}"

variables:
  hostname: ""
  username: "pi"
  user_password: ""
  ssh_keys: []

tags:
  - raspberry-pi-os
  - raspios
  - lite
  - headless
  - aarch64

author: PureBoot
created: "2026-01-28"
```

**Step 2: Commit**

```bash
git add workflows/pi-raspios-lite.yaml
git commit -m "feat: add Raspberry Pi OS Lite workflow"
```

---

## Task 6: Add Integration with Post-Install in Pi Image Script

**Files:**
- Modify: `deploy/scripts/pureboot-pi-image.sh`

**Step 1: Integrate cloud-init and raspios helpers**

Update main() to call configuration helpers based on image type:

```bash
# Detect OS type and configure accordingly
configure_os() {
    local mount_point="$1"

    # Detect OS type
    if [[ -f "${mount_point}/etc/rpi-issue" ]] || \
       [[ -f "${mount_point}/etc/apt/sources.list.d/raspi.list" ]]; then
        log "Detected Raspberry Pi OS"
        if [[ -x /usr/local/bin/pureboot-raspios-config.sh ]]; then
            source /usr/local/bin/pureboot-raspios-config.sh
            configure_raspios "${mount_point}" "${PUREBOOT_HOSTNAME:-}"
        fi
    elif [[ -d "${mount_point}/etc/cloud" ]]; then
        log "Detected cloud-init enabled OS"
        if [[ -x /usr/local/bin/pureboot-cloud-init.sh ]]; then
            source /usr/local/bin/pureboot-cloud-init.sh
            configure_cloud_init "${mount_point}" "${PUREBOOT_HOSTNAME:-}" ${PUREBOOT_SSH_KEYS:-}
        fi
    fi

    # Always enable SSH
    if [[ -x /usr/local/bin/pureboot-cloud-init.sh ]]; then
        source /usr/local/bin/pureboot-cloud-init.sh
        enable_ssh "${mount_point}"
    fi
}
```

**Step 2: Commit**

```bash
git add deploy/scripts/pureboot-pi-image.sh
git commit -m "feat: integrate OS detection and auto-configuration in Pi image deployment"
```

---

## Task 7: Add Unit Tests for OS Configuration Scripts

**Files:**
- Create: `tests/unit/test_os_config_scripts.py`

**Step 1: Create tests**

```python
"""Unit tests for OS configuration scripts."""
import os
import subprocess
from pathlib import Path

import pytest

DEPLOY_DIR = Path(__file__).parent.parent.parent / "deploy"
SCRIPTS_DIR = DEPLOY_DIR / "scripts"


class TestOSConfigScriptExistence:
    """Verify OS configuration scripts exist."""

    def test_cloud_init_script_exists(self):
        """Test cloud-init helper exists."""
        script = SCRIPTS_DIR / "pureboot-cloud-init.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"

    def test_raspios_config_script_exists(self):
        """Test Raspberry Pi OS helper exists."""
        script = SCRIPTS_DIR / "pureboot-raspios-config.sh"
        assert script.exists(), f"Missing: {script}"
        assert os.access(script, os.X_OK), f"Not executable: {script}"


class TestOSConfigScriptSyntax:
    """Verify scripts have valid syntax."""

    @pytest.mark.parametrize("script_name", [
        "pureboot-cloud-init.sh",
        "pureboot-raspios-config.sh",
    ])
    def test_script_syntax(self, script_name):
        """Test script has valid bash syntax."""
        script = SCRIPTS_DIR / script_name
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


class TestOSConfigScriptContent:
    """Verify scripts contain expected functions."""

    def test_cloud_init_has_functions(self):
        """Test cloud-init script has expected functions."""
        script = SCRIPTS_DIR / "pureboot-cloud-init.sh"
        content = script.read_text()

        expected = [
            "configure_cloud_init",
            "create_nocloud_seed",
            "set_target_hostname",
            "enable_ssh",
        ]

        for func in expected:
            assert func in content, f"Missing function: {func}"

    def test_raspios_config_has_functions(self):
        """Test Raspberry Pi OS script has expected functions."""
        script = SCRIPTS_DIR / "pureboot-raspios-config.sh"
        content = script.read_text()

        expected = [
            "configure_raspios",
            "configure_wifi",
            "disable_piwiz",
            "create_userconf",
            "add_ssh_keys",
        ]

        for func in expected:
            assert func in content, f"Missing function: {func}"
```

**Step 2: Commit**

```bash
git add tests/unit/test_os_config_scripts.py
git commit -m "test: add unit tests for OS configuration scripts"
```

---

## Task 8: Push Branch and Update PR

**Files:**
- None (git operations only)

**Step 1: Push changes**

```bash
git push origin feature/arm64-raspberry-pi
```

**Step 2: Update PR description to mark Phase 5 complete**

---

## Summary

Phase 5 adds OS installer support with:

1. **Post-Install Scripts** - Download and execute custom scripts after image deployment
2. **Cloud-Init Helper** - Configure Ubuntu ARM64 with cloud-init NoCloud datasource
3. **Raspberry Pi OS Helper** - Configure RasPi OS with SSH, WiFi, user setup
4. **OS Auto-Detection** - Automatically detect and configure OS type
5. **Example Workflows** - Raspberry Pi OS Lite workflow
6. **Unit Tests** - Script syntax and function verification

The deployment flow now supports:
- Image deployment with automatic partition resize
- OS-specific configuration (cloud-init or RasPi OS)
- SSH enablement by default
- Custom hostname configuration
- Post-install script execution
