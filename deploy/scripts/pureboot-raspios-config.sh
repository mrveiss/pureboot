#!/bin/bash
# PureBoot Raspberry Pi OS Configuration Helper
# Configures Raspberry Pi OS specific settings

set -e

if [[ -f /usr/local/bin/pureboot-common.sh ]]; then
    source /usr/local/bin/pureboot-common.sh
else
    log() { echo "[$(date '+%H:%M:%S')] $*"; }
    log_warn() { echo "[$(date '+%H:%M:%S')] WARN: $*" >&2; }
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
