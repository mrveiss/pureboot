#!/bin/bash
# PureBoot Direct Mode Clone Source Script
# This script runs on a source node to serve its disk via HTTPS for peer-to-peer cloning.
# The disk is served using lighttpd with mTLS for secure transfer.

set -e

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="/tmp/pureboot-certs"
WWW_DIR="/tmp/www"
LIGHTTPD_CONF="/tmp/lighttpd.conf"
LIGHTTPD_PID="/tmp/lighttpd.pid"
ACCESS_LOG="/tmp/lighttpd-access.log"
ERROR_LOG="/tmp/lighttpd-error.log"

# Progress reporting interval in seconds
PROGRESS_INTERVAL=5

# =============================================================================
# Source common functions
# =============================================================================

# Try multiple locations for common script
if [[ -f "${SCRIPT_DIR}/pureboot-common.sh" ]]; then
    source "${SCRIPT_DIR}/pureboot-common.sh"
elif [[ -f "/usr/local/bin/pureboot-common.sh" ]]; then
    source "/usr/local/bin/pureboot-common.sh"
else
    echo "ERROR: Cannot find pureboot-common.sh"
    exit 1
fi

# =============================================================================
# Set listen port
# =============================================================================

LISTEN_PORT="${PUREBOOT_TARGET_PORT:-9999}"

# =============================================================================
# Cleanup function
# =============================================================================

cleanup() {
    log "Cleaning up..."

    # Stop lighttpd if running
    if [[ -f "${LIGHTTPD_PID}" ]]; then
        local pid
        pid=$(cat "${LIGHTTPD_PID}" 2>/dev/null)
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            log "Stopping lighttpd (PID: ${pid})"
            kill "${pid}" 2>/dev/null || true
            # Wait for graceful shutdown
            local wait_count=0
            while kill -0 "${pid}" 2>/dev/null && [[ ${wait_count} -lt 10 ]]; do
                sleep 0.5
                ((wait_count++))
            done
            # Force kill if still running
            if kill -0 "${pid}" 2>/dev/null; then
                kill -9 "${pid}" 2>/dev/null || true
            fi
        fi
        rm -f "${LIGHTTPD_PID}"
    fi

    # Remove temporary files
    rm -f "${LIGHTTPD_CONF}"
    rm -rf "${WWW_DIR}"
    rm -f "${ACCESS_LOG}" "${ERROR_LOG}"

    # Flush any remaining queued updates
    flush_queue

    log "Cleanup complete"
}

# Set up cleanup trap
trap cleanup EXIT INT TERM

# =============================================================================
# Validation
# =============================================================================

log "PureBoot Direct Mode Clone Source starting..."

# Validate required parameters
if [[ -z "${PUREBOOT_SERVER}" ]]; then
    log_error "PUREBOOT_SERVER not set. Cannot communicate with controller."
    exit 1
fi

if [[ -z "${PUREBOOT_SESSION_ID}" ]]; then
    log_error "PUREBOOT_SESSION_ID not set. Clone session not identified."
    exit 1
fi

if [[ -z "${PUREBOOT_DEVICE}" ]]; then
    log_error "PUREBOOT_DEVICE not set. No source disk specified."
    exit 1
fi

# Validate device exists and is a block device
if [[ ! -b "${PUREBOOT_DEVICE}" ]]; then
    log_error "Device not found or not a block device: ${PUREBOOT_DEVICE}"
    report_error "Source device not found: ${PUREBOOT_DEVICE}" "101"
    exit 1
fi

log "Configuration validated:"
log "  Server: ${PUREBOOT_SERVER}"
log "  Session ID: ${PUREBOOT_SESSION_ID}"
log "  Device: ${PUREBOOT_DEVICE}"
log "  Listen Port: ${LISTEN_PORT}"

# =============================================================================
# Get disk information
# =============================================================================

log "Getting disk information..."

DISK_SIZE=$(get_disk_size "${PUREBOOT_DEVICE}")
if [[ $? -ne 0 || -z "${DISK_SIZE}" ]]; then
    log_error "Failed to get disk size for ${PUREBOOT_DEVICE}"
    report_error "Failed to get disk size" "102"
    exit 1
fi

DISK_SIZE_HUMAN=$(format_bytes "${DISK_SIZE}")
log "Disk size: ${DISK_SIZE} bytes (${DISK_SIZE_HUMAN})"

# =============================================================================
# Get local IP address
# =============================================================================

log "Determining local IP address..."

LOCAL_IP=$(get_local_ip)
if [[ $? -ne 0 || -z "${LOCAL_IP}" ]]; then
    log_error "Failed to determine local IP address"
    report_error "Failed to determine local IP" "103"
    exit 1
fi

log "Local IP address: ${LOCAL_IP}"

# =============================================================================
# Fetch TLS certificates
# =============================================================================

log "Fetching TLS certificates for source role..."

if ! fetch_certs "source" "${CERT_DIR}"; then
    log_error "Failed to fetch TLS certificates"
    report_error "Failed to fetch TLS certificates" "104"
    exit 1
fi

log "TLS certificates fetched successfully"

# Verify certificate files exist
for cert_file in "${CERT_DIR}/cert.pem" "${CERT_DIR}/key.pem" "${CERT_DIR}/ca.pem"; do
    if [[ ! -f "${cert_file}" ]]; then
        log_error "Certificate file missing: ${cert_file}"
        report_error "Certificate file missing" "105"
        exit 1
    fi
done

# =============================================================================
# Prepare web directory
# =============================================================================

log "Preparing web directory..."

mkdir -p "${WWW_DIR}"

# Create symlink to the disk device
# lighttpd will serve this as a raw file
ln -sf "${PUREBOOT_DEVICE}" "${WWW_DIR}/disk.raw"

log "Created symlink: ${WWW_DIR}/disk.raw -> ${PUREBOOT_DEVICE}"

# =============================================================================
# Create lighttpd configuration
# =============================================================================

log "Creating lighttpd configuration..."

cat > "${LIGHTTPD_CONF}" << EOF
# PureBoot Clone Source - lighttpd configuration
# Generated automatically - do not edit

server.document-root = "${WWW_DIR}"
server.port = ${LISTEN_PORT}
server.pid-file = "${LIGHTTPD_PID}"
server.errorlog = "${ERROR_LOG}"
accesslog.filename = "${ACCESS_LOG}"

# Modules
server.modules = (
    "mod_access",
    "mod_accesslog",
    "mod_openssl"
)

# TLS/SSL configuration with mTLS
ssl.engine = "enable"
ssl.pemfile = "${CERT_DIR}/cert.pem"
ssl.privkey = "${CERT_DIR}/key.pem"
ssl.ca-file = "${CERT_DIR}/ca.pem"

# Require client certificate verification (mTLS)
ssl.verifyclient.activate = "enable"
ssl.verifyclient.enforce = "enable"
ssl.verifyclient.depth = 1

# Access log format to track transfer progress
# Format: remote_addr timestamp request status bytes_sent
accesslog.format = "%h %t \"%r\" %s %b"

# MIME types
mimetype.assign = (
    ".raw" => "application/octet-stream"
)

# Only allow GET requests to disk.raw
\$HTTP["url"] !~ "^/disk\.raw\$" {
    url.access-deny = ("")
}

# Disable directory listing
dir-listing.activate = "disable"

# Connection settings for large file transfer
server.max-read-idle = 300
server.max-write-idle = 300
EOF

log "lighttpd configuration created at ${LIGHTTPD_CONF}"

# =============================================================================
# Start lighttpd
# =============================================================================

log "Starting lighttpd server..."

# Check if lighttpd is available
if ! command -v lighttpd &>/dev/null; then
    log_error "lighttpd not found in PATH"
    report_error "lighttpd not installed" "106"
    exit 1
fi

# Start lighttpd
lighttpd -f "${LIGHTTPD_CONF}"

# Wait for lighttpd to start
sleep 1

# Verify lighttpd is running
if [[ ! -f "${LIGHTTPD_PID}" ]]; then
    log_error "lighttpd failed to start - no PID file"
    if [[ -f "${ERROR_LOG}" ]]; then
        log_error "Error log contents:"
        cat "${ERROR_LOG}" >&2
    fi
    report_error "lighttpd failed to start" "107"
    exit 1
fi

LIGHTTPD_PID_VALUE=$(cat "${LIGHTTPD_PID}")
if ! kill -0 "${LIGHTTPD_PID_VALUE}" 2>/dev/null; then
    log_error "lighttpd is not running (PID: ${LIGHTTPD_PID_VALUE})"
    report_error "lighttpd not running" "108"
    exit 1
fi

log "lighttpd started successfully (PID: ${LIGHTTPD_PID_VALUE})"
log "HTTPS server listening on https://${LOCAL_IP}:${LISTEN_PORT}/"

# =============================================================================
# Report source ready to controller
# =============================================================================

log "Reporting source ready to controller..."

SOURCE_READY_DATA=$(cat << EOF
{
    "ip": "${LOCAL_IP}",
    "port": ${LISTEN_PORT},
    "size_bytes": ${DISK_SIZE},
    "device": "${PUREBOOT_DEVICE}"
}
EOF
)

SOURCE_READY_ENDPOINT="/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/source-ready"

if api_post "${SOURCE_READY_ENDPOINT}" "${SOURCE_READY_DATA}"; then
    log "Source ready reported successfully"
else
    log_warn "Failed to report source ready to controller"
    # Queue for retry
    queue_update "${SOURCE_READY_ENDPOINT}" "${SOURCE_READY_DATA}"
fi

# =============================================================================
# Monitor transfer progress
# =============================================================================

log "Monitoring transfer progress..."
log "Waiting for target to connect and download disk image..."

LAST_BYTES_SENT=0
LAST_PROGRESS_TIME=$(date +%s)
TRANSFER_STARTED=false

while true; do
    # Check if lighttpd is still running
    if [[ -f "${LIGHTTPD_PID}" ]]; then
        CURRENT_PID=$(cat "${LIGHTTPD_PID}" 2>/dev/null)
        if [[ -n "${CURRENT_PID}" ]] && ! kill -0 "${CURRENT_PID}" 2>/dev/null; then
            log "lighttpd has stopped"
            break
        fi
    else
        log "lighttpd PID file removed"
        break
    fi

    # Parse access log to track transfer progress
    if [[ -f "${ACCESS_LOG}" ]]; then
        # Get the latest entry and extract bytes sent
        LATEST_ENTRY=$(tail -1 "${ACCESS_LOG}" 2>/dev/null)

        if [[ -n "${LATEST_ENTRY}" ]]; then
            # Extract bytes sent from log entry (last field)
            BYTES_SENT=$(echo "${LATEST_ENTRY}" | awk '{print $NF}')

            # Validate it's a number
            if [[ "${BYTES_SENT}" =~ ^[0-9]+$ ]]; then
                if [[ ${BYTES_SENT} -gt 0 ]]; then
                    if [[ "${TRANSFER_STARTED}" != "true" ]]; then
                        TRANSFER_STARTED=true
                        log "Transfer started - target is downloading disk image"
                        report_status "streaming" "Transfer started"
                    fi

                    # Calculate progress percentage
                    if [[ ${DISK_SIZE} -gt 0 ]]; then
                        PERCENT=$((BYTES_SENT * 100 / DISK_SIZE))
                        if [[ ${PERCENT} -gt 100 ]]; then
                            PERCENT=100
                        fi

                        # Report progress at intervals
                        CURRENT_TIME=$(date +%s)
                        if [[ $((CURRENT_TIME - LAST_PROGRESS_TIME)) -ge ${PROGRESS_INTERVAL} ]] && \
                           [[ ${BYTES_SENT} -ne ${LAST_BYTES_SENT} ]]; then
                            BYTES_SENT_HUMAN=$(format_bytes "${BYTES_SENT}")
                            log "Transfer progress: ${PERCENT}% (${BYTES_SENT_HUMAN} / ${DISK_SIZE_HUMAN})"
                            report_progress "${PERCENT}" "Transferred ${BYTES_SENT_HUMAN}"
                            LAST_BYTES_SENT=${BYTES_SENT}
                            LAST_PROGRESS_TIME=${CURRENT_TIME}
                        fi

                        # Check if transfer is complete
                        if [[ ${BYTES_SENT} -ge ${DISK_SIZE} ]]; then
                            log "Transfer complete: 100% (${DISK_SIZE_HUMAN})"
                            report_progress 100 "Transfer complete"
                            report_status "complete" "Disk image transfer completed"
                            log "Transfer finished successfully"
                            # Give the connection time to close gracefully
                            sleep 2
                            break
                        fi
                    fi
                fi
            fi
        fi
    fi

    # Flush any queued updates periodically
    flush_queue

    # Sleep before next check
    sleep 1
done

log "Source script completed"
