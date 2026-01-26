#!/bin/bash
# PureBoot Common Shared Functions
# This script provides shared functions for all clone and partition scripts
# Source this file: source /usr/local/bin/pureboot-common.sh

# Prevent direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "This script should be sourced, not executed directly."
    echo "Usage: source ${BASH_SOURCE[0]}"
    exit 1
fi

# =============================================================================
# Colors for logging
# =============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Queue directory for offline resilience
# =============================================================================
QUEUE_DIR="/tmp/pureboot-queue"

# =============================================================================
# Parsed kernel cmdline variables (populated by parse_cmdline)
# =============================================================================
PUREBOOT_SERVER=""
PUREBOOT_NODE_ID=""
PUREBOOT_SESSION_ID=""
PUREBOOT_MODE=""
PUREBOOT_DEVICE=""
PUREBOOT_TARGET_IP=""
PUREBOOT_TARGET_PORT=""

# =============================================================================
# Logging functions
# =============================================================================

# Log info message with timestamp
# Usage: log "message"
log() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${GREEN}[${timestamp}]${NC} [PureBoot] $*"
}

# Log warning message with timestamp
# Usage: log_warn "message"
log_warn() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${YELLOW}[${timestamp}]${NC} [PureBoot] WARNING: $*"
}

# Log error message with timestamp
# Usage: log_error "message"
log_error() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${RED}[${timestamp}]${NC} [PureBoot] ERROR: $*" >&2
}

# Log debug message (only if PUREBOOT_DEBUG is set)
# Usage: log_debug "message"
log_debug() {
    if [[ -n "${PUREBOOT_DEBUG:-}" ]]; then
        local timestamp
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo -e "${BLUE}[${timestamp}]${NC} [PureBoot] DEBUG: $*"
    fi
}

# =============================================================================
# Kernel command line parsing
# =============================================================================

# Parse kernel cmdline for pureboot.* parameters
# Sets global variables: PUREBOOT_SERVER, PUREBOOT_NODE_ID, PUREBOOT_SESSION_ID,
#                        PUREBOOT_MODE, PUREBOOT_DEVICE, PUREBOOT_TARGET_IP,
#                        PUREBOOT_TARGET_PORT
# Usage: parse_cmdline
parse_cmdline() {
    local cmdline
    if [[ -r /proc/cmdline ]]; then
        cmdline=$(cat /proc/cmdline)
    else
        log_warn "Cannot read /proc/cmdline, using environment variables"
        return 0
    fi

    local param
    for param in ${cmdline}; do
        case "${param}" in
            pureboot.server=*)
                PUREBOOT_SERVER="${param#pureboot.server=}"
                ;;
            pureboot.node_id=*)
                PUREBOOT_NODE_ID="${param#pureboot.node_id=}"
                ;;
            pureboot.session_id=*)
                PUREBOOT_SESSION_ID="${param#pureboot.session_id=}"
                ;;
            pureboot.mode=*)
                PUREBOOT_MODE="${param#pureboot.mode=}"
                ;;
            pureboot.device=*)
                PUREBOOT_DEVICE="${param#pureboot.device=}"
                ;;
            pureboot.target_ip=*)
                PUREBOOT_TARGET_IP="${param#pureboot.target_ip=}"
                ;;
            pureboot.target_port=*)
                PUREBOOT_TARGET_PORT="${param#pureboot.target_port=}"
                ;;
        esac
    done

    log_debug "Parsed cmdline: server=${PUREBOOT_SERVER}, node_id=${PUREBOOT_NODE_ID}, session_id=${PUREBOOT_SESSION_ID}"
    log_debug "Parsed cmdline: mode=${PUREBOOT_MODE}, device=${PUREBOOT_DEVICE}"
    log_debug "Parsed cmdline: target_ip=${PUREBOOT_TARGET_IP}, target_port=${PUREBOOT_TARGET_PORT}"
}

# =============================================================================
# Network utilities
# =============================================================================

# Get local IP address from common interface names
# Returns the first valid IP found from eth0, ens3, enp0s3, enp1s0
# Usage: local_ip=$(get_local_ip)
get_local_ip() {
    local iface ip_addr
    local interfaces=("eth0" "ens3" "enp0s3" "enp1s0" "ens192" "ens160")

    for iface in "${interfaces[@]}"; do
        if ip link show "${iface}" &>/dev/null; then
            ip_addr=$(ip -4 addr show "${iface}" 2>/dev/null | grep -oP 'inet \K[\d.]+' | head -1)
            if [[ -n "${ip_addr}" ]]; then
                echo "${ip_addr}"
                return 0
            fi
        fi
    done

    # Fallback: get any non-loopback IP
    ip_addr=$(ip -4 addr show scope global 2>/dev/null | grep -oP 'inet \K[\d.]+' | head -1)
    if [[ -n "${ip_addr}" ]]; then
        echo "${ip_addr}"
        return 0
    fi

    log_error "Could not determine local IP address"
    return 1
}

# =============================================================================
# API communication functions
# =============================================================================

# POST data to controller API
# Usage: api_post "/api/v1/endpoint" '{"key": "value"}'
# Returns: 0 on success, non-zero on failure
api_post() {
    local endpoint="$1"
    local data="$2"
    local url="${PUREBOOT_SERVER}${endpoint}"
    local response
    local http_code

    if [[ -z "${PUREBOOT_SERVER}" ]]; then
        log_error "PUREBOOT_SERVER not set, cannot make API call"
        return 1
    fi

    log_debug "API POST to ${url}"
    log_debug "Data: ${data}"

    # Make the request with timeout and capture both response and HTTP code
    response=$(curl -sf \
        --connect-timeout 10 \
        --max-time 30 \
        -X POST \
        -H "Content-Type: application/json" \
        -w "\n%{http_code}" \
        -d "${data}" \
        "${url}" 2>/dev/null)

    local curl_exit=$?

    # Extract HTTP code from last line
    http_code=$(echo "${response}" | tail -n1)
    response=$(echo "${response}" | sed '$d')

    if [[ ${curl_exit} -ne 0 ]]; then
        log_debug "API POST failed with curl exit code: ${curl_exit}"
        return 1
    fi

    if [[ "${http_code}" -ge 200 && "${http_code}" -lt 300 ]]; then
        log_debug "API POST successful (HTTP ${http_code})"
        echo "${response}"
        return 0
    else
        log_debug "API POST failed with HTTP ${http_code}: ${response}"
        return 1
    fi
}

# Queue an update for later delivery when controller is unreachable
# Usage: queue_update "/api/v1/endpoint" '{"key": "value"}'
queue_update() {
    local endpoint="$1"
    local data="$2"
    local timestamp
    timestamp=$(date +%s%N)
    local queue_file="${QUEUE_DIR}/${timestamp}.json"

    # Ensure queue directory exists
    mkdir -p "${QUEUE_DIR}"

    # Write queued request
    cat > "${queue_file}" << EOF
{
    "endpoint": "${endpoint}",
    "data": ${data},
    "queued_at": "${timestamp}"
}
EOF

    log_debug "Queued update to ${queue_file}"
    return 0
}

# Flush all queued updates to the controller
# Usage: flush_queue
# Returns: 0 if all flushed successfully, 1 if any failed
flush_queue() {
    local queue_file endpoint data
    local failed=0
    local flushed=0

    if [[ ! -d "${QUEUE_DIR}" ]]; then
        log_debug "No queue directory, nothing to flush"
        return 0
    fi

    # Process queue files in order (sorted by timestamp in filename)
    for queue_file in "${QUEUE_DIR}"/*.json; do
        [[ -f "${queue_file}" ]] || continue

        endpoint=$(jq -r '.endpoint' "${queue_file}" 2>/dev/null)
        data=$(jq -c '.data' "${queue_file}" 2>/dev/null)

        if [[ -z "${endpoint}" || -z "${data}" ]]; then
            log_warn "Invalid queue file: ${queue_file}, removing"
            rm -f "${queue_file}"
            continue
        fi

        log_debug "Flushing queued update: ${endpoint}"

        if api_post "${endpoint}" "${data}"; then
            rm -f "${queue_file}"
            ((flushed++))
        else
            log_warn "Failed to flush queued update: ${endpoint}"
            ((failed++))
        fi
    done

    if [[ ${flushed} -gt 0 ]]; then
        log "Flushed ${flushed} queued updates"
    fi

    if [[ ${failed} -gt 0 ]]; then
        log_warn "${failed} queued updates remain unflushed"
        return 1
    fi

    return 0
}

# POST to API with offline resilience - queues if controller unreachable
# Usage: api_post_resilient "/api/v1/endpoint" '{"key": "value"}'
# Returns: 0 on success (either posted or queued)
api_post_resilient() {
    local endpoint="$1"
    local data="$2"

    # First, try to flush any existing queued updates
    flush_queue

    # Try to make the API call
    if api_post "${endpoint}" "${data}"; then
        return 0
    fi

    # API call failed, queue the update
    log_warn "Controller unreachable, queuing update for later"
    queue_update "${endpoint}" "${data}"
    return 0
}

# =============================================================================
# TLS certificate management
# =============================================================================

# Fetch TLS certificates from controller for source/target role
# Usage: fetch_certs "source" "/path/to/cert/dir"
#        fetch_certs "target" "/path/to/cert/dir"
# Returns: 0 on success, 1 on failure
fetch_certs() {
    local role="$1"
    local cert_dir="${2:-/tmp/pureboot-certs}"
    if [[ -z "${PUREBOOT_SERVER}" ]]; then
        log_error "PUREBOOT_SERVER not set, cannot fetch certificates"
        return 1
    fi

    if [[ -z "${PUREBOOT_SESSION_ID}" ]]; then
        log_error "PUREBOOT_SESSION_ID not set, cannot fetch certificates"
        return 1
    fi

    mkdir -p "${cert_dir}"

    local url="${PUREBOOT_SERVER}/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/certs?role=${role}"
    log "Fetching TLS certificates for role: ${role}"

    # Fetch certificate bundle
    local response
    response=$(curl -sf \
        --connect-timeout 10 \
        --max-time 30 \
        "${url}" 2>/dev/null)

    if [[ $? -ne 0 || -z "${response}" ]]; then
        log_error "Failed to fetch certificates from controller"
        return 1
    fi

    # Parse and save certificates from JSON response
    local cert key ca

    cert=$(echo "${response}" | jq -r '.cert_pem // empty' 2>/dev/null)
    key=$(echo "${response}" | jq -r '.key_pem // empty' 2>/dev/null)
    ca=$(echo "${response}" | jq -r '.ca_pem // empty' 2>/dev/null)

    if [[ -z "${cert}" || -z "${key}" || -z "${ca}" ]]; then
        log_error "Invalid certificate response from controller"
        return 1
    fi

    # Write certificates to files
    echo "${cert}" > "${cert_dir}/cert.pem"
    echo "${key}" > "${cert_dir}/key.pem"
    echo "${ca}" > "${cert_dir}/ca.pem"

    # Set secure permissions on key file
    chmod 600 "${cert_dir}/key.pem"
    chmod 644 "${cert_dir}/cert.pem"
    chmod 644 "${cert_dir}/ca.pem"

    log "Certificates saved to ${cert_dir}"
    return 0
}

# =============================================================================
# Disk utility functions
# =============================================================================

# Get disk size in bytes using blockdev
# Usage: size=$(get_disk_size "/dev/sda")
get_disk_size() {
    local device="$1"

    if [[ ! -b "${device}" ]]; then
        log_error "Device not found or not a block device: ${device}"
        return 1
    fi

    local size
    size=$(blockdev --getsize64 "${device}" 2>/dev/null)

    if [[ $? -ne 0 || -z "${size}" ]]; then
        log_error "Failed to get size of device: ${device}"
        return 1
    fi

    echo "${size}"
    return 0
}

# Format bytes to human readable string
# Usage: human=$(format_bytes 1073741824)  # Returns "1.00 GB"
format_bytes() {
    local bytes="$1"
    local units=("B" "KB" "MB" "GB" "TB" "PB")
    local unit_index=0
    local size="${bytes}"

    # Use awk for floating point arithmetic
    while [[ $(echo "${size} >= 1024" | bc -l 2>/dev/null || echo "0") -eq 1 ]] && [[ ${unit_index} -lt 5 ]]; do
        size=$(echo "scale=2; ${size} / 1024" | bc -l 2>/dev/null || echo "${size}")
        ((unit_index++))
    done

    # Format with 2 decimal places
    printf "%.2f %s" "${size}" "${units[${unit_index}]}"
}

# Check if a device is a valid block device
# Usage: if is_block_device "/dev/sda"; then ...
is_block_device() {
    local device="$1"
    [[ -b "${device}" ]]
}

# Get the parent disk of a partition
# Usage: disk=$(get_parent_disk "/dev/sda1")  # Returns "/dev/sda"
get_parent_disk() {
    local partition="$1"
    local disk

    # Remove partition number suffix
    disk=$(echo "${partition}" | sed 's/[0-9]*$//' | sed 's/p$//')

    # Handle NVMe devices (e.g., /dev/nvme0n1p1 -> /dev/nvme0n1)
    if [[ "${partition}" =~ nvme[0-9]+n[0-9]+p[0-9]+ ]]; then
        disk=$(echo "${partition}" | sed 's/p[0-9]*$//')
    fi

    echo "${disk}"
}

# =============================================================================
# Status reporting helpers
# =============================================================================

# Report progress to controller
# Usage: report_progress 50 "Copying data..."
report_progress() {
    local percent="$1"
    local message="${2:-}"
    local endpoint="/api/v1/clone/sessions/${PUREBOOT_SESSION_ID}/progress"

    local data
    data=$(cat << EOF
{
    "node_id": "${PUREBOOT_NODE_ID}",
    "percent": ${percent},
    "message": "${message}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    api_post_resilient "${endpoint}" "${data}"
}

# Report status change to controller
# Usage: report_status "streaming" "Started data transfer"
report_status() {
    local status="$1"
    local message="${2:-}"
    local endpoint="/api/v1/clone/sessions/${PUREBOOT_SESSION_ID}/status"

    local data
    data=$(cat << EOF
{
    "node_id": "${PUREBOOT_NODE_ID}",
    "status": "${status}",
    "message": "${message}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    api_post_resilient "${endpoint}" "${data}"
}

# Report error to controller
# Usage: report_error "Disk read failed" "101"
report_error() {
    local message="$1"
    local code="${2:-1}"
    local endpoint="/api/v1/clone/sessions/${PUREBOOT_SESSION_ID}/error"

    local data
    data=$(cat << EOF
{
    "node_id": "${PUREBOOT_NODE_ID}",
    "error_code": "${code}",
    "error_message": "${message}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

    api_post_resilient "${endpoint}" "${data}"
}

# =============================================================================
# NFS Mount Functions
# =============================================================================

# Mount NFS share
# Usage: mount_nfs "server" "export" "mountpoint" ["options"]
# Returns: 0 on success, 1 on failure
mount_nfs() {
    local server="$1"
    local export_path="$2"
    local mountpoint="$3"
    local options="${4:-rw,sync,noatime}"

    log "Mounting NFS share ${server}:${export_path} at ${mountpoint}"

    # Create mountpoint if needed
    mkdir -p "${mountpoint}"

    # Mount NFS
    if ! mount -t nfs -o "${options}" "${server}:${export_path}" "${mountpoint}"; then
        log_error "Failed to mount NFS share"
        return 1
    fi

    log "NFS share mounted successfully"
    return 0
}

# Unmount NFS share
# Usage: unmount_nfs "mountpoint"
# Returns: 0 on success
unmount_nfs() {
    local mountpoint="$1"

    log "Unmounting NFS share at ${mountpoint}"

    # Sync before unmount
    sync

    if mountpoint -q "${mountpoint}"; then
        if ! umount "${mountpoint}"; then
            log_error "Failed to unmount NFS share, trying lazy unmount"
            umount -l "${mountpoint}" || true
        fi
    fi

    log "NFS share unmounted"
    return 0
}

# =============================================================================
# iSCSI Functions
# =============================================================================

# Login to iSCSI target
# Usage: iscsi_login "target" "portal" ["username" "password"]
# Returns: 0 on success, 1 on failure
iscsi_login() {
    local target="$1"
    local portal="$2"
    local username="${3:-}"
    local password="${4:-}"

    log "Connecting to iSCSI target ${target} at ${portal}"

    # Set up authentication if provided
    if [[ -n "${username}" ]] && [[ -n "${password}" ]]; then
        iscsiadm -m node -T "${target}" -p "${portal}" \
            --op update -n node.session.auth.authmethod -v CHAP
        iscsiadm -m node -T "${target}" -p "${portal}" \
            --op update -n node.session.auth.username -v "${username}"
        iscsiadm -m node -T "${target}" -p "${portal}" \
            --op update -n node.session.auth.password -v "${password}"
    fi

    # Discover and login
    iscsiadm -m discovery -t sendtargets -p "${portal}" 2>/dev/null || true

    if ! iscsiadm -m node -T "${target}" -p "${portal}" --login; then
        log_error "Failed to login to iSCSI target"
        return 1
    fi

    # Wait for device to appear
    local retries=10
    while [[ ${retries} -gt 0 ]]; do
        if get_iscsi_device "${target}" >/dev/null 2>&1; then
            log "iSCSI target connected successfully"
            return 0
        fi
        sleep 1
        ((retries--))
    done

    log_error "iSCSI device did not appear"
    return 1
}

# Logout from iSCSI target
# Usage: iscsi_logout "target" ["portal"]
# Returns: 0 on success
iscsi_logout() {
    local target="$1"
    local portal="${2:-}"

    log "Disconnecting from iSCSI target ${target}"

    # Sync before logout
    sync

    if [[ -n "${portal}" ]]; then
        iscsiadm -m node -T "${target}" -p "${portal}" --logout 2>/dev/null || true
    else
        iscsiadm -m node -T "${target}" --logout 2>/dev/null || true
    fi

    log "iSCSI target disconnected"
    return 0
}

# Get device path for iSCSI target
# Usage: get_iscsi_device "target"
# Returns: device path on stdout, 0 on success, 1 on failure
get_iscsi_device() {
    local target="$1"
    local device

    # Find the device by target name
    device=$(lsblk -n -o NAME,TRAN | grep iscsi | head -1 | awk '{print "/dev/"$1}')

    if [[ -z "${device}" ]] || [[ ! -b "${device}" ]]; then
        # Alternative: find by session
        local session
        session=$(iscsiadm -m session 2>/dev/null | grep "${target}" | awk '{print $2}' | tr -d '[]')
        if [[ -n "${session}" ]]; then
            device=$(ls /sys/class/iscsi_session/session${session}/device/target*/*/block/ 2>/dev/null | head -1)
            if [[ -n "${device}" ]]; then
                device="/dev/${device}"
            fi
        fi
    fi

    if [[ -z "${device}" ]] || [[ ! -b "${device}" ]]; then
        log_error "Could not find iSCSI device for target ${target}"
        return 1
    fi

    echo "${device}"
    return 0
}

# =============================================================================
# Staging Mount Functions
# =============================================================================

# Mount staging storage based on type
# Usage: mount_staging "staging_info_json" "mountpoint"
# Returns: device path for iSCSI, or confirms NFS mount. 0 on success, 1 on failure
mount_staging() {
    local staging_json="$1"
    local mountpoint="$2"
    local staging_type

    staging_type=$(echo "${staging_json}" | jq -r '.type')

    case "${staging_type}" in
        nfs)
            local server export_path options path
            server=$(echo "${staging_json}" | jq -r '.server')
            export_path=$(echo "${staging_json}" | jq -r '.export')
            path=$(echo "${staging_json}" | jq -r '.path // empty')
            options=$(echo "${staging_json}" | jq -r '.options // "rw,sync,noatime"')

            # Full path includes subdirectory
            local full_export="${export_path}"
            if [[ -n "${path}" ]]; then
                full_export="${export_path}/${path}"
            fi

            mount_nfs "${server}" "${full_export}" "${mountpoint}" "${options}"
            ;;
        iscsi)
            local target portal username password
            target=$(echo "${staging_json}" | jq -r '.target')
            portal=$(echo "${staging_json}" | jq -r '.portal')
            username=$(echo "${staging_json}" | jq -r '.username // empty')
            password=$(echo "${staging_json}" | jq -r '.password // empty')

            iscsi_login "${target}" "${portal}" "${username}" "${password}"
            get_iscsi_device "${target}"
            ;;
        *)
            log_error "Unknown staging type: ${staging_type}"
            return 1
            ;;
    esac
}

# Unmount staging storage based on type
# Usage: unmount_staging "staging_info_json" "mountpoint"
# Returns: 0 on success, 1 on failure
unmount_staging() {
    local staging_json="$1"
    local mountpoint="$2"
    local staging_type

    staging_type=$(echo "${staging_json}" | jq -r '.type')

    case "${staging_type}" in
        nfs)
            unmount_nfs "${mountpoint}"
            ;;
        iscsi)
            local target portal
            target=$(echo "${staging_json}" | jq -r '.target')
            portal=$(echo "${staging_json}" | jq -r '.portal // empty')
            iscsi_logout "${target}" "${portal}"
            ;;
        *)
            log_error "Unknown staging type: ${staging_type}"
            return 1
            ;;
    esac
}

# =============================================================================
# Initialization
# =============================================================================

# Initialize the common library
# This is called automatically when the script is sourced
_pureboot_common_init() {
    # Create queue directory if it doesn't exist
    mkdir -p "${QUEUE_DIR}" 2>/dev/null || true

    # Parse cmdline if /proc/cmdline exists
    if [[ -r /proc/cmdline ]]; then
        parse_cmdline
    fi
}

# Run initialization
_pureboot_common_init
