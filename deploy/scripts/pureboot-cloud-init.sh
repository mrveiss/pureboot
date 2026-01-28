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
    log_warn() { echo "[$(date '+%H:%M:%S')] WARN: $*" >&2; }
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
        log "SSH enabled via boot flag (boot/firmware)"
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
            log "SSH service enabled (ssh.service)"
        elif [[ -f "${mount_point}/lib/systemd/system/sshd.service" ]]; then
            ln -sf /lib/systemd/system/sshd.service \
                "${mount_point}/etc/systemd/system/multi-user.target.wants/sshd.service" 2>/dev/null || true
            log "SSH service enabled (sshd.service)"
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
