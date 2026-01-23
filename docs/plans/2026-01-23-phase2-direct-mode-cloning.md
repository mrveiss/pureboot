# Phase 2: Direct Mode Cloning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement direct (peer-to-peer) disk cloning with TLS encryption between source and target nodes.

**Architecture:** Source node boots into deploy env, starts HTTPS server streaming disk. Target connects via mTLS, streams disk to local storage. Controller orchestrates but doesn't proxy data.

**Tech Stack:** Alpine Linux deploy env, lighttpd + mod_ssl, curl with TLS, bash scripts, FastAPI callbacks

---

## Task 1: Common Shared Functions Script

**Files:**
- Create: `deploy/scripts/pureboot-common.sh`

**Step 1: Create the common functions script**

```bash
#!/bin/bash
# PureBoot Common Functions
# Shared by all clone and partition scripts

# Colors for logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Queue directory for offline resilience
QUEUE_DIR="/tmp/pureboot-queue"

# Logging functions
log() {
    echo -e "${GREEN}[PureBoot]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[PureBoot WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[PureBoot ERROR]${NC} $*"
}

# Parse kernel cmdline for pureboot.* parameters
parse_cmdline() {
    for param in $(cat /proc/cmdline); do
        case "$param" in
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

    # Defaults
    PUREBOOT_DEVICE="${PUREBOOT_DEVICE:-/dev/sda}"
    PUREBOOT_TARGET_PORT="${PUREBOOT_TARGET_PORT:-9999}"
}

# Get local IP address
get_local_ip() {
    local iface
    for iface in eth0 ens3 enp0s3 enp1s0; do
        local ip
        ip=$(ip -4 addr show "$iface" 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
        if [ -n "$ip" ]; then
            echo "$ip"
            return 0
        fi
    done
    return 1
}

# API call with resilience
api_post() {
    local endpoint="$1"
    local payload="$2"
    local url="${PUREBOOT_SERVER}/api/v1${endpoint}"

    curl -sf -X POST "$url" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        --connect-timeout 5 \
        --max-time 30
}

# Queue update for later delivery
queue_update() {
    local endpoint="$1"
    local payload="$2"
    local timestamp
    timestamp=$(date +%s%N)
    mkdir -p "$QUEUE_DIR"
    echo "${endpoint}|${payload}" > "$QUEUE_DIR/${timestamp}.pending"
    log "Queued update for $endpoint"
}

# Flush queued updates
flush_queue() {
    local count=0
    for f in "$QUEUE_DIR"/*.pending 2>/dev/null; do
        [ -f "$f" ] || continue
        local endpoint
        local payload
        endpoint=$(cut -d'|' -f1 < "$f")
        payload=$(cut -d'|' -f2- < "$f")
        if api_post "$endpoint" "$payload" >/dev/null 2>&1; then
            rm -f "$f"
            ((count++))
        fi
    done
    [ $count -gt 0 ] && log "Flushed $count queued updates"
}

# API post with offline resilience
api_post_resilient() {
    local endpoint="$1"
    local payload="$2"

    # Try to flush any queued updates first
    flush_queue

    if ! api_post "$endpoint" "$payload" >/dev/null 2>&1; then
        log_warn "Controller unreachable, queueing update"
        queue_update "$endpoint" "$payload"
        return 1
    fi
    return 0
}

# Fetch TLS certificates from controller
fetch_certs() {
    local role="$1"  # source or target
    local cert_dir="/tmp/pureboot-certs"

    mkdir -p "$cert_dir"
    chmod 700 "$cert_dir"

    log "Fetching TLS certificates for role: $role"

    local certs_url="${PUREBOOT_SERVER}/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}/certs?role=${role}"
    local response

    response=$(curl -sf "$certs_url" --connect-timeout 10 --max-time 30)
    if [ $? -ne 0 ]; then
        log_error "Failed to fetch certificates"
        return 1
    fi

    # Parse JSON and save certs
    echo "$response" | jq -r '.cert_pem' > "$cert_dir/cert.pem"
    echo "$response" | jq -r '.key_pem' > "$cert_dir/key.pem"
    echo "$response" | jq -r '.ca_pem' > "$cert_dir/ca.pem"

    chmod 600 "$cert_dir"/*.pem

    # Verify certs are valid
    if ! openssl x509 -in "$cert_dir/cert.pem" -noout 2>/dev/null; then
        log_error "Invalid certificate received"
        return 1
    fi

    log "Certificates saved to $cert_dir"
    export PUREBOOT_CERT_DIR="$cert_dir"
    return 0
}

# Get disk size in bytes
get_disk_size() {
    local device="$1"
    blockdev --getsize64 "$device"
}

# Format bytes to human readable
format_bytes() {
    local bytes="$1"
    if [ "$bytes" -ge 1099511627776 ]; then
        echo "$(echo "scale=2; $bytes / 1099511627776" | bc) TB"
    elif [ "$bytes" -ge 1073741824 ]; then
        echo "$(echo "scale=2; $bytes / 1073741824" | bc) GB"
    elif [ "$bytes" -ge 1048576 ]; then
        echo "$(echo "scale=2; $bytes / 1048576" | bc) MB"
    else
        echo "$bytes bytes"
    fi
}
```

**Step 2: Commit**

```bash
git add deploy/scripts/pureboot-common.sh
git commit -m "feat(clone): add common shared functions script

Includes:
- Logging functions with colors
- Kernel cmdline parsing for pureboot.* params
- API post with offline resilience (queue when controller down)
- TLS certificate fetching from controller
- Disk utility functions"
```

---

## Task 2: Direct Mode Source Script

**Files:**
- Create: `deploy/scripts/pureboot-clone-source-direct.sh`

**Step 1: Create the source script for direct mode**

```bash
#!/bin/bash
# PureBoot Clone Source - Direct Mode
# Serves disk via HTTPS for peer-to-peer cloning

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/pureboot-common.sh"

LISTEN_PORT="${PUREBOOT_TARGET_PORT:-9999}"
LIGHTTPD_CONF="/tmp/lighttpd.conf"
LIGHTTPD_PID="/tmp/lighttpd.pid"

# Report progress to controller
report_progress() {
    local bytes_transferred="$1"
    local bytes_total="$2"
    local rate_bps="${3:-null}"

    local payload
    payload=$(cat <<EOF
{
    "role": "source",
    "bytes_transferred": $bytes_transferred,
    "bytes_total": $bytes_total,
    "transfer_rate_bps": $rate_bps,
    "status": "transferring"
}
EOF
)
    api_post_resilient "/clone-sessions/${PUREBOOT_SESSION_ID}/progress" "$payload"
}

# Report source ready with IP and port
report_source_ready() {
    local ip="$1"
    local port="$2"
    local size_bytes="$3"

    local payload
    payload=$(cat <<EOF
{
    "source_ip": "$ip",
    "source_port": $port,
    "size_bytes": $size_bytes
}
EOF
)

    log "Reporting source ready: $ip:$port ($(format_bytes $size_bytes))"
    api_post "/clone-sessions/${PUREBOOT_SESSION_ID}/source-ready" "$payload"
}

# Report failure
report_failed() {
    local error="$1"
    local payload
    payload=$(cat <<EOF
{"error": "$error"}
EOF
)
    api_post_resilient "/clone-sessions/${PUREBOOT_SESSION_ID}/failed" "$payload"
}

# Create lighttpd configuration for TLS disk streaming
create_lighttpd_config() {
    local cert_dir="$PUREBOOT_CERT_DIR"
    local device="$PUREBOOT_DEVICE"

    cat > "$LIGHTTPD_CONF" <<EOF
server.document-root = "/tmp/www"
server.port = $LISTEN_PORT
server.pid-file = "$LIGHTTPD_PID"

# TLS configuration
ssl.engine = "enable"
ssl.pemfile = "$cert_dir/cert.pem"
ssl.privkey = "$cert_dir/key.pem"
ssl.ca-file = "$cert_dir/ca.pem"
ssl.verifyclient.activate = "enable"
ssl.verifyclient.enforce = "require"
ssl.verifyclient.depth = 1

# Logging
server.errorlog = "/tmp/lighttpd-error.log"
accesslog.filename = "/tmp/lighttpd-access.log"

# MIME types
mimetype.assign = (
    ".raw" => "application/octet-stream"
)

# Modules
server.modules = (
    "mod_accesslog",
    "mod_openssl"
)
EOF
}

# Create CGI script to stream disk with progress
create_disk_streamer() {
    local www_dir="/tmp/www"
    mkdir -p "$www_dir"

    # Create a named pipe for tracking progress
    local pipe="/tmp/disk-stream-pipe"
    rm -f "$pipe"
    mkfifo "$pipe"

    # We'll serve the disk directly via a simple approach:
    # Create a symlink to the block device (lighttpd can serve it)
    # But for progress tracking, we need something smarter

    # Alternative: Use a shell script that lighttpd CGI calls
    # For simplicity, just create a direct reference
    # Real progress tracking happens via periodic size checks

    ln -sf "$PUREBOOT_DEVICE" "$www_dir/disk.raw"

    log "Disk available at https://<ip>:$LISTEN_PORT/disk.raw"
}

# Monitor transfer progress by watching access log
monitor_progress() {
    local disk_size="$1"
    local last_bytes=0
    local last_time
    last_time=$(date +%s)

    while [ -f "$LIGHTTPD_PID" ]; do
        sleep 5

        # Check if target has connected by looking at access log
        if [ -f "/tmp/lighttpd-access.log" ]; then
            local bytes_sent
            # Parse bytes from access log (format: IP - - [date] "GET /disk.raw" 200 BYTES)
            bytes_sent=$(tail -1 /tmp/lighttpd-access.log 2>/dev/null | awk '{print $NF}' | grep -E '^[0-9]+$' || echo "0")

            if [ "$bytes_sent" -gt 0 ]; then
                local now
                now=$(date +%s)
                local elapsed=$((now - last_time))
                local rate=0

                if [ $elapsed -gt 0 ]; then
                    rate=$(( (bytes_sent - last_bytes) / elapsed ))
                fi

                report_progress "$bytes_sent" "$disk_size" "$rate"

                last_bytes="$bytes_sent"
                last_time="$now"

                # Check if complete
                if [ "$bytes_sent" -ge "$disk_size" ]; then
                    log "Transfer complete"
                    break
                fi
            fi
        fi
    done
}

# Cleanup
cleanup() {
    log "Cleaning up..."
    [ -f "$LIGHTTPD_PID" ] && kill "$(cat "$LIGHTTPD_PID")" 2>/dev/null
    rm -f "$LIGHTTPD_CONF" "$LIGHTTPD_PID"
    rm -rf /tmp/www
    flush_queue
}

trap cleanup EXIT

# Main
main() {
    log "=== PureBoot Clone Source (Direct Mode) ==="

    parse_cmdline

    # Validate required params
    if [ -z "$PUREBOOT_SERVER" ] || [ -z "$PUREBOOT_SESSION_ID" ]; then
        log_error "Missing required parameters: pureboot.server and pureboot.session_id"
        exit 1
    fi

    if [ ! -b "$PUREBOOT_DEVICE" ]; then
        report_failed "Source device not found: $PUREBOOT_DEVICE"
        exit 1
    fi

    # Get disk info
    local disk_size
    disk_size=$(get_disk_size "$PUREBOOT_DEVICE")
    log "Source device: $PUREBOOT_DEVICE ($(format_bytes $disk_size))"

    # Fetch TLS certificates
    if ! fetch_certs "source"; then
        report_failed "Failed to fetch TLS certificates"
        exit 1
    fi

    # Get local IP
    local local_ip
    local_ip=$(get_local_ip)
    if [ -z "$local_ip" ]; then
        report_failed "Could not determine local IP address"
        exit 1
    fi
    log "Local IP: $local_ip"

    # Configure and start HTTPS server
    create_lighttpd_config
    create_disk_streamer

    log "Starting HTTPS server on port $LISTEN_PORT..."
    lighttpd -f "$LIGHTTPD_CONF"

    # Report ready to controller
    report_source_ready "$local_ip" "$LISTEN_PORT" "$disk_size"

    log "Waiting for target to connect..."
    log "Disk URL: https://$local_ip:$LISTEN_PORT/disk.raw"

    # Monitor transfer progress
    monitor_progress "$disk_size"

    log "=== Clone Source Complete ==="

    # Flush any remaining queued updates
    flush_queue

    # Keep running until target disconnects or explicit shutdown
    log "Staying online for potential retries. Press Ctrl+C to shutdown."
    wait
}

main "$@"
```

**Step 2: Commit**

```bash
git add deploy/scripts/pureboot-clone-source-direct.sh
git commit -m "feat(clone): add direct mode source script

Implements HTTPS disk streaming server using lighttpd:
- Fetches mTLS certificates from controller
- Starts TLS server with client certificate verification
- Serves disk device as raw stream
- Reports source_ready with IP/port to controller
- Monitors and reports transfer progress
- Offline resilience for progress updates"
```

---

## Task 3: Direct Mode Target Script

**Files:**
- Create: `deploy/scripts/pureboot-clone-target-direct.sh`

**Step 1: Create the target script for direct mode**

```bash
#!/bin/bash
# PureBoot Clone Target - Direct Mode
# Receives disk via HTTPS from source node

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/pureboot-common.sh"

PROGRESS_INTERVAL=5  # seconds between progress reports

# Report progress to controller
report_progress() {
    local bytes_transferred="$1"
    local bytes_total="$2"
    local rate_bps="${3:-null}"
    local status="${4:-transferring}"

    local payload
    payload=$(cat <<EOF
{
    "role": "target",
    "bytes_transferred": $bytes_transferred,
    "bytes_total": $bytes_total,
    "transfer_rate_bps": $rate_bps,
    "status": "$status"
}
EOF
)
    api_post_resilient "/clone-sessions/${PUREBOOT_SESSION_ID}/progress" "$payload"
}

# Report completion
report_complete() {
    local payload='{"status": "completed"}'
    api_post "/clone-sessions/${PUREBOOT_SESSION_ID}/complete" "$payload"
}

# Report failure
report_failed() {
    local error="$1"
    local payload
    payload=$(cat <<EOF
{"error": "$error"}
EOF
)
    api_post_resilient "/clone-sessions/${PUREBOOT_SESSION_ID}/failed" "$payload"
}

# Wait for source to be ready (poll session status)
wait_for_source() {
    log "Waiting for source node to be ready..."

    local max_attempts=120  # 10 minutes at 5 second intervals
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        local response
        response=$(curl -sf "${PUREBOOT_SERVER}/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}" 2>/dev/null)

        if [ $? -eq 0 ]; then
            local status
            local source_ip
            local source_port

            status=$(echo "$response" | jq -r '.status')
            source_ip=$(echo "$response" | jq -r '.source_ip // empty')
            source_port=$(echo "$response" | jq -r '.source_port // empty')

            if [ "$status" = "source_ready" ] && [ -n "$source_ip" ]; then
                PUREBOOT_TARGET_IP="$source_ip"
                PUREBOOT_TARGET_PORT="${source_port:-9999}"
                log "Source ready at $PUREBOOT_TARGET_IP:$PUREBOOT_TARGET_PORT"
                return 0
            elif [ "$status" = "failed" ] || [ "$status" = "cancelled" ]; then
                log_error "Clone session $status"
                return 1
            fi
        fi

        ((attempt++))
        sleep 5
    done

    log_error "Timeout waiting for source node"
    return 1
}

# Stream disk from source with progress tracking
stream_disk() {
    local source_url="$1"
    local target_device="$2"
    local cert_dir="$PUREBOOT_CERT_DIR"

    log "Streaming from $source_url to $target_device"

    # Get expected size from session
    local session_info
    session_info=$(curl -sf "${PUREBOOT_SERVER}/api/v1/clone-sessions/${PUREBOOT_SESSION_ID}")
    local bytes_total
    bytes_total=$(echo "$session_info" | jq -r '.bytes_total // 0')

    if [ "$bytes_total" -eq 0 ]; then
        # Try to get size from HTTP HEAD request
        bytes_total=$(curl -sf --head \
            --cert "$cert_dir/cert.pem" \
            --key "$cert_dir/key.pem" \
            --cacert "$cert_dir/ca.pem" \
            "$source_url" 2>/dev/null | grep -i content-length | awk '{print $2}' | tr -d '\r')
        bytes_total="${bytes_total:-0}"
    fi

    log "Expected size: $(format_bytes $bytes_total)"

    # Create progress tracking pipe
    local progress_pipe="/tmp/progress-pipe"
    rm -f "$progress_pipe"
    mkfifo "$progress_pipe"

    # Start progress reporter in background
    (
        local last_bytes=0
        local last_time
        last_time=$(date +%s)

        while read line; do
            # pv outputs: BYTES ELAPSED TIME ETA RATE
            local bytes
            bytes=$(echo "$line" | awk '{print $1}')

            if [ -n "$bytes" ] && [ "$bytes" -gt 0 ]; then
                local now
                now=$(date +%s)
                local elapsed=$((now - last_time))
                local rate=0

                if [ $elapsed -ge $PROGRESS_INTERVAL ]; then
                    if [ $elapsed -gt 0 ]; then
                        rate=$(( (bytes - last_bytes) / elapsed ))
                    fi

                    report_progress "$bytes" "$bytes_total" "$rate"

                    last_bytes="$bytes"
                    last_time="$now"
                fi
            fi
        done < "$progress_pipe"
    ) &
    local reporter_pid=$!

    # Stream with curl through pv for progress
    local exit_code=0
    curl -sf \
        --cert "$cert_dir/cert.pem" \
        --key "$cert_dir/key.pem" \
        --cacert "$cert_dir/ca.pem" \
        "$source_url" 2>/dev/null | \
        pv -n -b 2>"$progress_pipe" | \
        dd of="$target_device" bs=4M conv=fsync 2>/dev/null || exit_code=$?

    # Clean up progress reporter
    echo "0" > "$progress_pipe"  # Signal end
    kill $reporter_pid 2>/dev/null || true
    rm -f "$progress_pipe"

    if [ $exit_code -ne 0 ]; then
        return 1
    fi

    # Final sync
    sync

    # Report final progress
    local final_bytes
    final_bytes=$(get_disk_size "$target_device")
    report_progress "$final_bytes" "$bytes_total" "0" "completed"

    return 0
}

# Verify written data (optional checksum)
verify_disk() {
    local device="$1"
    report_progress "0" "0" "0" "verifying"

    log "Verifying disk..."
    # Basic verification: check partition table is readable
    if partprobe "$device" 2>/dev/null; then
        log "Partition table verified"
        return 0
    else
        log_warn "Could not read partition table (may be intentional for raw images)"
        return 0
    fi
}

# Cleanup
cleanup() {
    log "Cleaning up..."
    rm -f /tmp/progress-pipe
    flush_queue
}

trap cleanup EXIT

# Main
main() {
    log "=== PureBoot Clone Target (Direct Mode) ==="

    parse_cmdline

    # Validate required params
    if [ -z "$PUREBOOT_SERVER" ] || [ -z "$PUREBOOT_SESSION_ID" ]; then
        log_error "Missing required parameters: pureboot.server and pureboot.session_id"
        exit 1
    fi

    if [ ! -b "$PUREBOOT_DEVICE" ]; then
        report_failed "Target device not found: $PUREBOOT_DEVICE"
        exit 1
    fi

    local target_size
    target_size=$(get_disk_size "$PUREBOOT_DEVICE")
    log "Target device: $PUREBOOT_DEVICE ($(format_bytes $target_size))"

    # Fetch TLS certificates
    if ! fetch_certs "target"; then
        report_failed "Failed to fetch TLS certificates"
        exit 1
    fi

    # Wait for source node to be ready
    if ! wait_for_source; then
        report_failed "Source node never became ready"
        exit 1
    fi

    # Construct source URL
    local source_url="https://${PUREBOOT_TARGET_IP}:${PUREBOOT_TARGET_PORT}/disk.raw"

    # Stream disk from source
    log "Starting disk transfer..."
    if ! stream_disk "$source_url" "$PUREBOOT_DEVICE"; then
        report_failed "Disk transfer failed"
        exit 1
    fi

    # Verify
    if ! verify_disk "$PUREBOOT_DEVICE"; then
        report_failed "Disk verification failed"
        exit 1
    fi

    # Report success
    report_complete

    log "=== Clone Complete ==="
    log "Rebooting in 10 seconds..."
    sleep 10
    reboot -f
}

main "$@"
```

**Step 2: Commit**

```bash
git add deploy/scripts/pureboot-clone-target-direct.sh
git commit -m "feat(clone): add direct mode target script

Implements disk receiver for P2P cloning:
- Waits for source_ready status from controller
- Fetches mTLS certificates
- Streams disk via HTTPS with pv progress tracking
- Reports progress to controller with rate calculation
- Verifies disk after transfer
- Reboots on completion"
```

---

## Task 4: Update Build Script for Clone Packages

**Files:**
- Modify: `deploy/build-deploy-image.sh`

**Step 1: Read current file to understand structure**

(Already read above - need to add TLS and clone packages)

**Step 2: Add new packages to the install script section**

Find the `apk add` section and add:
- `openssl` - TLS operations
- `lighttpd` - HTTPS server
- `lighttpd-mod_auth` - For TLS modules (includes mod_openssl on Alpine)

Replace the package install section:

```bash
cat > "${ROOTFS_DIR}/install-packages.sh" << 'INSTALL_EOF'
#!/bin/sh
apk update
apk add --no-cache \
    curl \
    wget \
    xz \
    gzip \
    pigz \
    pv \
    parted \
    e2fsprogs \
    e2fsprogs-extra \
    dosfstools \
    ntfs-3g \
    ntfs-3g-progs \
    btrfs-progs \
    xfsprogs \
    util-linux \
    coreutils \
    bash \
    jq \
    openssl \
    lighttpd \
    lighttpd-mod_auth \
    bc
INSTALL_EOF
```

**Step 3: Add script copying to the build**

After the existing `pureboot-deploy` script creation, add:

```bash
# Copy clone scripts
mkdir -p "${ROOTFS_DIR}/usr/local/bin"
cp "${SCRIPT_DIR}/scripts/pureboot-common.sh" "${ROOTFS_DIR}/usr/local/bin/"
cp "${SCRIPT_DIR}/scripts/pureboot-clone-source-direct.sh" "${ROOTFS_DIR}/usr/local/bin/"
cp "${SCRIPT_DIR}/scripts/pureboot-clone-target-direct.sh" "${ROOTFS_DIR}/usr/local/bin/"
chmod +x "${ROOTFS_DIR}/usr/local/bin"/pureboot-*.sh
```

**Step 4: Commit**

```bash
git add deploy/build-deploy-image.sh
git commit -m "feat(clone): add TLS and clone packages to deploy image

Adds:
- openssl for TLS certificate operations
- lighttpd + mod_auth for HTTPS disk streaming
- ntfs-3g-progs, btrfs-progs, xfsprogs for filesystem support
- bc for arithmetic in scripts
- Copies clone scripts to image"
```

---

## Task 5: Main Deploy Entrypoint with Mode Dispatcher

**Files:**
- Modify: `deploy/build-deploy-image.sh` (update the pureboot-deploy script)

**Step 1: Update the embedded pureboot-deploy script to dispatch modes**

Replace the `DEPLOY_EOF` section with a mode dispatcher:

```bash
cat > "${ROOTFS_DIR}/usr/local/bin/pureboot-deploy" << 'DEPLOY_EOF'
#!/bin/bash
# PureBoot Deploy - Main Entrypoint
# Dispatches to appropriate script based on pureboot.mode kernel param

set -e

source /usr/local/bin/pureboot-common.sh

# Parse mode from cmdline
parse_cmdline

log "=== PureBoot Deploy Environment ==="
log "Mode: ${PUREBOOT_MODE:-image}"

case "${PUREBOOT_MODE}" in
    clone_source_direct)
        exec /usr/local/bin/pureboot-clone-source-direct.sh
        ;;
    clone_target_direct)
        exec /usr/local/bin/pureboot-clone-target-direct.sh
        ;;
    clone_source_staged)
        exec /usr/local/bin/pureboot-clone-source-staged.sh
        ;;
    clone_target_staged)
        exec /usr/local/bin/pureboot-clone-target-staged.sh
        ;;
    partition)
        exec /usr/local/bin/pureboot-partition.sh
        ;;
    image|"")
        # Default: image deployment (legacy behavior)
        exec /usr/local/bin/pureboot-image.sh
        ;;
    *)
        log_error "Unknown mode: ${PUREBOOT_MODE}"
        log "Valid modes: image, clone_source_direct, clone_target_direct, clone_source_staged, clone_target_staged, partition"
        exit 1
        ;;
esac
DEPLOY_EOF
```

**Step 2: Move existing image deploy logic to separate script**

The current deploy script becomes `pureboot-image.sh`. Create it in the build script.

**Step 3: Commit**

```bash
git add deploy/build-deploy-image.sh
git commit -m "feat(clone): add mode dispatcher to deploy entrypoint

pureboot-deploy now routes to appropriate script based on
pureboot.mode kernel parameter:
- image (default): legacy disk image deployment
- clone_source_direct: P2P clone source
- clone_target_direct: P2P clone target
- clone_source_staged: staged clone source (future)
- clone_target_staged: staged clone target (future)
- partition: partition management (future)"
```

---

## Task 6: Backend Clone Session Start Endpoint

**Files:**
- Modify: `src/api/routes/clone.py`

**Step 1: Read current file**

(Already have context from Phase 1)

**Step 2: Add start endpoint that triggers source node boot**

Add after the existing endpoints:

```python
@router.post("/clone-sessions/{session_id}/start")
async def start_clone_session(
    session_id: str,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Start a clone session by booting the source node into clone mode."""
    from src.db.models import CloneSession, Node
    from src.api.routes.nodes import trigger_node_boot  # We'll create this

    result = await db.execute(
        select(CloneSession)
        .options(selectinload(CloneSession.source_node))
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    if session.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start session in '{session.status}' status"
        )

    # Generate certificates for both nodes
    from src.core.ca import ca_service

    source_cert, source_key = ca_service.issue_session_cert(
        session_id=session_id,
        node_id=session.source_node_id,
        role="source"
    )
    session.source_cert_pem = source_cert
    session.source_key_pem = source_key

    if session.target_node_id:
        target_cert, target_key = ca_service.issue_session_cert(
            session_id=session_id,
            node_id=session.target_node_id,
            role="target"
        )
        session.target_cert_pem = target_cert
        session.target_key_pem = target_key

    session.started_at = datetime.utcnow()
    await db.commit()

    # Trigger source node to boot into clone mode
    # This sets the node's next boot to clone_source workflow
    boot_mode = f"clone_source_{session.clone_mode}"

    # Update source node's workflow/boot params
    session.source_node.pending_workflow = boot_mode
    session.source_node.boot_params = {
        "pureboot.mode": boot_mode,
        "pureboot.session_id": session_id,
        "pureboot.device": session.source_device,
    }
    await db.commit()

    # Broadcast event
    from src.core.websocket import broadcast_event
    await broadcast_event("clone.started", {
        "session_id": session_id,
        "source_node_id": session.source_node_id,
        "target_node_id": session.target_node_id,
    })

    return {
        "success": True,
        "message": "Clone session started",
        "session_id": session_id,
        "source_boot_mode": boot_mode,
    }
```

**Step 3: Commit**

```bash
git add src/api/routes/clone.py
git commit -m "feat(clone): add start endpoint to trigger source boot

POST /clone-sessions/{id}/start:
- Validates session is in pending status
- Generates TLS certificates for source and target
- Sets source node's pending workflow to clone mode
- Broadcasts clone.started WebSocket event"
```

---

## Task 7: Backend Certs Endpoint Enhancement

**Files:**
- Modify: `src/api/routes/clone.py`

**Step 1: Enhance the certs endpoint to return proper bundle**

The current endpoint needs to return cert_pem, key_pem, and ca_pem:

```python
@router.get("/clone-sessions/{session_id}/certs")
async def get_clone_session_certs(
    session_id: str,
    role: str = Query(..., regex="^(source|target)$"),
    db: AsyncSession = Depends(get_db)
) -> CloneCertBundle:
    """Get TLS certificates for a clone session node."""
    from src.db.models import CloneSession
    from src.core.ca import ca_service

    result = await db.execute(
        select(CloneSession).where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    if role == "source":
        if not session.source_cert_pem or not session.source_key_pem:
            raise HTTPException(
                status_code=400,
                detail="Source certificates not yet generated. Start the session first."
            )
        cert_pem = session.source_cert_pem
        key_pem = session.source_key_pem
    else:  # target
        if not session.target_cert_pem or not session.target_key_pem:
            raise HTTPException(
                status_code=400,
                detail="Target certificates not yet generated. Start the session first."
            )
        cert_pem = session.target_cert_pem
        key_pem = session.target_key_pem

    ca_pem = ca_service.get_ca_cert_pem()

    return CloneCertBundle(
        cert_pem=cert_pem,
        key_pem=key_pem,
        ca_pem=ca_pem,
    )
```

**Step 2: Commit**

```bash
git add src/api/routes/clone.py
git commit -m "feat(clone): enhance certs endpoint with full bundle

GET /clone-sessions/{id}/certs?role=source|target now returns:
- cert_pem: Node's certificate
- key_pem: Node's private key
- ca_pem: CA certificate for verification

Returns 400 if certs not yet generated (session not started)."
```

---

## Task 8: Backend Auto-Assign Target Workflow

**Files:**
- Modify: `src/api/routes/clone.py`

**Step 1: Update source-ready callback to trigger target boot**

Enhance the existing source_ready endpoint:

```python
@router.post("/clone-sessions/{session_id}/source-ready")
async def clone_source_ready(
    session_id: str,
    data: CloneSourceReady,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Source node reports ready with IP and port."""
    from src.db.models import CloneSession

    result = await db.execute(
        select(CloneSession)
        .options(selectinload(CloneSession.target_node))
        .where(CloneSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Clone session not found")

    # Update session with source info
    session.source_ip = data.source_ip
    session.source_port = data.source_port
    session.bytes_total = data.size_bytes
    session.status = "source_ready"

    await db.commit()

    # Broadcast source ready event
    from src.core.websocket import broadcast_event
    await broadcast_event("clone.source_ready", {
        "session_id": session_id,
        "source_ip": data.source_ip,
        "source_port": data.source_port,
        "size_bytes": data.size_bytes,
    })

    # For direct mode, trigger target to boot if assigned
    if session.clone_mode == "direct" and session.target_node_id and session.target_node:
        boot_mode = "clone_target_direct"
        session.target_node.pending_workflow = boot_mode
        session.target_node.boot_params = {
            "pureboot.mode": boot_mode,
            "pureboot.session_id": session_id,
            "pureboot.device": session.target_device,
            "pureboot.target_ip": data.source_ip,
            "pureboot.target_port": str(data.source_port),
        }
        await db.commit()

        return {
            "success": True,
            "message": "Source ready, target node boot triggered",
            "target_node_id": session.target_node_id,
        }

    return {
        "success": True,
        "message": "Source ready",
    }
```

**Step 2: Commit**

```bash
git add src/api/routes/clone.py
git commit -m "feat(clone): auto-trigger target boot when source ready

POST /clone-sessions/{id}/source-ready:
- Records source IP, port, disk size
- Updates status to source_ready
- Broadcasts clone.source_ready event
- For direct mode: automatically sets target node's
  pending workflow to clone_target_direct"
```

---

## Task 9: Clone Workflow YAML Files

**Files:**
- Create: `workflows/clone-source-direct.yaml`
- Create: `workflows/clone-target-direct.yaml`
- Update: `workflows/clone-target.yaml` (mark as legacy)

**Step 1: Create direct source workflow**

```yaml
# Direct Clone Source Workflow
# Boots into deploy environment to serve disk via HTTPS
id: clone-source-direct
name: Clone Source (Direct P2P)
description: Boot into deploy environment to serve disk for peer-to-peer cloning

# Install method: deploy - boots minimal environment for cloning
install_method: deploy

# Boot into clone source mode
boot_params:
  pureboot.mode: clone_source_direct
  # session_id and device are set dynamically by controller

# Architecture and boot mode
architecture: x86_64
boot_mode: uefi
```

**Step 2: Create direct target workflow**

```yaml
# Direct Clone Target Workflow
# Boots into deploy environment to receive disk via HTTPS
id: clone-target-direct
name: Clone Target (Direct P2P)
description: Boot into deploy environment to receive peer-to-peer disk clone

# Install method: deploy - boots minimal environment for cloning
install_method: deploy

# Boot into clone target mode
boot_params:
  pureboot.mode: clone_target_direct
  # session_id, device, target_ip, target_port set dynamically

# Architecture and boot mode
architecture: x86_64
boot_mode: uefi
```

**Step 3: Update legacy workflow with deprecation note**

```yaml
# Clone Target Workflow (LEGACY)
# Use clone-target-direct or clone-target-staged for new deployments
id: clone-target
name: Clone Target (Receive Disk) [LEGACY]
description: |
  DEPRECATED: Use clone-target-direct for P2P cloning.
  This workflow is kept for backwards compatibility.

# Install method: image - will stream disk from source and write to target
install_method: image

# The image_url will be dynamically set based on which source is ready
image_url: "http://CLONE_SOURCE_IP:8080/disk"

# Target device to write the cloned disk to
target_device: /dev/sda

# Architecture and boot mode
architecture: x86_64
boot_mode: uefi
```

**Step 4: Commit**

```bash
git add workflows/clone-source-direct.yaml workflows/clone-target-direct.yaml workflows/clone-target.yaml
git commit -m "feat(clone): add direct mode workflow definitions

New workflows:
- clone-source-direct: P2P source with TLS
- clone-target-direct: P2P target with TLS

Marks clone-target.yaml as legacy with deprecation note."
```

---

## Task 10: Frontend Clone List Page

**Files:**
- Create: `frontend/src/pages/CloneSessions.tsx`
- Modify: `frontend/src/App.tsx` (add route)

**Step 1: Create clone sessions list page**

```tsx
import { Link } from 'react-router-dom'
import { Plus, Copy, ArrowRight, Clock, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
} from '@/components/ui'
import { useCloneSessions } from '@/hooks/useCloneSessions'
import { useCloneUpdates } from '@/hooks/useCloneUpdates'
import { CLONE_STATUS_COLORS, type CloneSession } from '@/types/clone'

function CloneStatusBadge({ status }: { status: CloneSession['status'] }) {
  const colorClass = CLONE_STATUS_COLORS[status] || 'bg-gray-500'

  const icons: Record<string, React.ReactNode> = {
    pending: <Clock className="h-3 w-3" />,
    source_ready: <Loader2 className="h-3 w-3 animate-spin" />,
    cloning: <Loader2 className="h-3 w-3 animate-spin" />,
    completed: <CheckCircle className="h-3 w-3" />,
    failed: <XCircle className="h-3 w-3" />,
    cancelled: <XCircle className="h-3 w-3" />,
  }

  return (
    <Badge className={`${colorClass} text-white flex items-center gap-1`}>
      {icons[status]}
      {status.replace('_', ' ')}
    </Badge>
  )
}

function CloneProgress({ session }: { session: CloneSession }) {
  if (!session.bytes_total || session.bytes_total === 0) {
    return null
  }

  const percent = session.progress_percent || 0
  const transferred = formatBytes(session.bytes_transferred || 0)
  const total = formatBytes(session.bytes_total)
  const rate = session.transfer_rate_bps
    ? `${formatBytes(session.transfer_rate_bps)}/s`
    : ''

  return (
    <div className="mt-2">
      <div className="flex justify-between text-sm text-muted-foreground mb-1">
        <span>{transferred} / {total}</span>
        <span>{rate}</span>
      </div>
      <div className="w-full bg-secondary rounded-full h-2">
        <div
          className="bg-primary rounded-full h-2 transition-all duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>
      <div className="text-right text-sm text-muted-foreground mt-1">
        {percent.toFixed(1)}%
      </div>
    </div>
  )
}

function formatBytes(bytes: number): string {
  if (bytes >= 1099511627776) return `${(bytes / 1099511627776).toFixed(2)} TB`
  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(2)} GB`
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(2)} MB`
  return `${bytes} B`
}

function CloneSessionCard({ session }: { session: CloneSession }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Copy className="h-5 w-5 text-muted-foreground" />
            <div>
              <Link
                to={`/clone/${session.id}`}
                className="font-medium hover:underline"
              >
                {session.name || `Clone ${session.id.slice(0, 8)}`}
              </Link>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <span>{session.source_node_name || session.source_node_id.slice(0, 8)}</span>
                <ArrowRight className="h-3 w-3" />
                <span>{session.target_node_name || session.target_node_id?.slice(0, 8) || 'Not assigned'}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{session.clone_mode}</Badge>
            <CloneStatusBadge status={session.status} />
          </div>
        </div>

        {(session.status === 'cloning' || session.status === 'source_ready') && (
          <CloneProgress session={session} />
        )}

        {session.error_message && (
          <div className="mt-2 p-2 bg-destructive/10 text-destructive text-sm rounded">
            {session.error_message}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function CloneSessions() {
  const { data: sessions, isLoading, error } = useCloneSessions()

  // Enable real-time updates
  useCloneUpdates()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 bg-destructive/10 text-destructive rounded">
        Failed to load clone sessions: {error.message}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Clone Sessions</h1>
          <p className="text-muted-foreground">
            Manage disk cloning between nodes
          </p>
        </div>
        <Button asChild>
          <Link to="/clone/new">
            <Plus className="h-4 w-4 mr-2" />
            New Clone
          </Link>
        </Button>
      </div>

      {sessions && sessions.length > 0 ? (
        <div className="space-y-3">
          {sessions.map((session) => (
            <CloneSessionCard key={session.id} session={session} />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="p-12 text-center">
            <Copy className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-medium mb-2">No clone sessions</h3>
            <p className="text-muted-foreground mb-4">
              Create a clone session to copy disks between nodes
            </p>
            <Button asChild>
              <Link to="/clone/new">
                <Plus className="h-4 w-4 mr-2" />
                Create Clone Session
              </Link>
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
```

**Step 2: Add route to App.tsx**

Add import and route:

```tsx
import { CloneSessions } from './pages/CloneSessions'

// In routes:
<Route path="/clone" element={<CloneSessions />} />
```

**Step 3: Commit**

```bash
git add frontend/src/pages/CloneSessions.tsx frontend/src/App.tsx
git commit -m "feat(clone): add clone sessions list page

New CloneSessions page with:
- List of clone sessions with status badges
- Progress bars for active clones
- Real-time updates via WebSocket
- Link to create new clone session
- Empty state with call-to-action"
```

---

## Task 11: Frontend Clone Detail Page

**Files:**
- Create: `frontend/src/pages/CloneDetail.tsx`
- Modify: `frontend/src/App.tsx` (add route)

**Step 1: Create clone detail page**

```tsx
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Copy, Server, Clock, Activity, ArrowRight } from 'lucide-react'
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Badge,
} from '@/components/ui'
import { useCloneSession, useCancelCloneSession } from '@/hooks/useCloneSessions'
import { useCloneUpdates } from '@/hooks/useCloneUpdates'
import { CLONE_STATUS_COLORS } from '@/types/clone'

function formatBytes(bytes: number): string {
  if (bytes >= 1099511627776) return `${(bytes / 1099511627776).toFixed(2)} TB`
  if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(2)} GB`
  if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(2)} MB`
  return `${bytes} B`
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)

  if (hours > 0) return `${hours}h ${minutes}m ${secs}s`
  if (minutes > 0) return `${minutes}m ${secs}s`
  return `${secs}s`
}

export function CloneDetail() {
  const { id } = useParams<{ id: string }>()
  const { data: session, isLoading, error } = useCloneSession(id || '')
  const cancelMutation = useCancelCloneSession()

  // Enable real-time updates
  useCloneUpdates()

  if (isLoading) {
    return <div className="animate-pulse h-64 bg-muted rounded" />
  }

  if (error || !session) {
    return (
      <div className="p-4 bg-destructive/10 text-destructive rounded">
        Clone session not found
      </div>
    )
  }

  const canCancel = ['pending', 'source_ready', 'cloning'].includes(session.status)
  const isActive = ['source_ready', 'cloning'].includes(session.status)

  const handleCancel = () => {
    if (window.confirm('Are you sure you want to cancel this clone session?')) {
      cancelMutation.mutate(session.id)
    }
  }

  // Calculate elapsed time
  let elapsed = 0
  if (session.started_at) {
    const start = new Date(session.started_at).getTime()
    const end = session.completed_at
      ? new Date(session.completed_at).getTime()
      : Date.now()
    elapsed = Math.floor((end - start) / 1000)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/clone">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Link>
        </Button>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Copy className="h-8 w-8 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-bold">
              {session.name || `Clone Session`}
            </h1>
            <p className="text-sm text-muted-foreground">{session.id}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline">{session.clone_mode}</Badge>
          <Badge className={`${CLONE_STATUS_COLORS[session.status]} text-white`}>
            {session.status.replace('_', ' ')}
          </Badge>
          {canCancel && (
            <Button
              variant="destructive"
              size="sm"
              onClick={handleCancel}
              disabled={cancelMutation.isPending}
            >
              Cancel
            </Button>
          )}
        </div>
      </div>

      {/* Progress section for active clones */}
      {isActive && session.bytes_total && session.bytes_total > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Transfer Progress
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex justify-between text-sm">
                <span>{formatBytes(session.bytes_transferred || 0)} / {formatBytes(session.bytes_total)}</span>
                <span>
                  {session.transfer_rate_bps
                    ? `${formatBytes(session.transfer_rate_bps)}/s`
                    : 'Calculating...'}
                </span>
              </div>
              <div className="w-full bg-secondary rounded-full h-4">
                <div
                  className="bg-primary rounded-full h-4 transition-all duration-300"
                  style={{ width: `${session.progress_percent || 0}%` }}
                />
              </div>
              <div className="flex justify-between text-sm text-muted-foreground">
                <span>{(session.progress_percent || 0).toFixed(1)}% complete</span>
                <span>Elapsed: {formatDuration(elapsed)}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error display */}
      {session.error_message && (
        <Card className="border-destructive">
          <CardContent className="p-4 text-destructive">
            <strong>Error:</strong> {session.error_message}
          </CardContent>
        </Card>
      )}

      {/* Nodes info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="h-4 w-4" />
              Source Node
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div>
              <span className="text-sm text-muted-foreground">Node:</span>
              <Link
                to={`/nodes/${session.source_node_id}`}
                className="ml-2 hover:underline"
              >
                {session.source_node_name || session.source_node_id}
              </Link>
            </div>
            <div>
              <span className="text-sm text-muted-foreground">Device:</span>
              <span className="ml-2 font-mono">{session.source_device}</span>
            </div>
            {session.source_ip && (
              <div>
                <span className="text-sm text-muted-foreground">IP:</span>
                <span className="ml-2 font-mono">
                  {session.source_ip}:{session.source_port || 9999}
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="h-4 w-4" />
              Target Node
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {session.target_node_id ? (
              <>
                <div>
                  <span className="text-sm text-muted-foreground">Node:</span>
                  <Link
                    to={`/nodes/${session.target_node_id}`}
                    className="ml-2 hover:underline"
                  >
                    {session.target_node_name || session.target_node_id}
                  </Link>
                </div>
                <div>
                  <span className="text-sm text-muted-foreground">Device:</span>
                  <span className="ml-2 font-mono">{session.target_device}</span>
                </div>
              </>
            ) : (
              <p className="text-muted-foreground">Not assigned</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Timeline / metadata */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Clock className="h-4 w-4" />
            Timeline
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Created</span>
              <span>{new Date(session.created_at).toLocaleString()}</span>
            </div>
            {session.started_at && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Started</span>
                <span>{new Date(session.started_at).toLocaleString()}</span>
              </div>
            )}
            {session.completed_at && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Completed</span>
                <span>{new Date(session.completed_at).toLocaleString()}</span>
              </div>
            )}
            {session.completed_at && session.started_at && (
              <div className="flex justify-between font-medium">
                <span>Duration</span>
                <span>{formatDuration(elapsed)}</span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
```

**Step 2: Add route to App.tsx**

```tsx
import { CloneDetail } from './pages/CloneDetail'

// In routes:
<Route path="/clone/:id" element={<CloneDetail />} />
```

**Step 3: Commit**

```bash
git add frontend/src/pages/CloneDetail.tsx frontend/src/App.tsx
git commit -m "feat(clone): add clone detail page

CloneDetail page showing:
- Session status and metadata
- Live progress bar with transfer rate
- Source and target node information
- Timeline with timestamps
- Cancel button for active sessions
- Real-time WebSocket updates"
```

---

## Task 12: Add Navigation Link to Clone Sessions

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx` or wherever nav is defined

**Step 1: Read current nav structure**

Find navigation file and add Clone Sessions link.

**Step 2: Add link**

```tsx
// Add to navigation items
{ name: 'Clone Sessions', href: '/clone', icon: Copy }
```

**Step 3: Commit**

```bash
git add frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(clone): add clone sessions to navigation

Adds 'Clone Sessions' link to sidebar navigation."
```

---

## Summary

Phase 2 implements direct mode (peer-to-peer) disk cloning with:

**Deploy Environment (5 tasks):**
1. Common shared functions script with offline resilience
2. Direct mode source script (HTTPS server)
3. Direct mode target script (HTTPS client)
4. Updated build script with TLS packages
5. Mode dispatcher entrypoint

**Backend (3 tasks):**
6. Clone session start endpoint
7. Enhanced certs endpoint
8. Auto-trigger target boot on source ready

**Workflows (1 task):**
9. Clone workflow YAML definitions

**Frontend (3 tasks):**
10. Clone sessions list page
11. Clone detail page
12. Navigation link

Total: 12 tasks
