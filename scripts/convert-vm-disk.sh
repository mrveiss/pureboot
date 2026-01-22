#!/bin/bash
# Convert VM disk files to raw format for PureBoot deployment
# Supports: VMDK, VHD, VHDX, QCOW2, OVA

set -e

usage() {
    cat << EOF
Usage: $0 <input-file> [output-file]

Convert VM disk files to compressed raw format for PureBoot deployment.

Supported input formats:
  - VMDK (VMware)
  - VHD/VHDX (Hyper-V)
  - QCOW2 (QEMU/KVM)
  - OVA (extracts and converts the disk)
  - RAW/IMG (just compresses)

Output will be compressed with gzip (.raw.gz)

Examples:
  $0 ubuntu.vmdk                    # Creates ubuntu.raw.gz
  $0 windows.vhdx windows-base.raw.gz
  $0 template.ova

Requirements:
  - qemu-img (apt install qemu-utils)
  - tar (for OVA extraction)
  - gzip or pigz (for compression)
EOF
    exit 1
}

# Check dependencies
check_deps() {
    local missing=""
    command -v qemu-img >/dev/null 2>&1 || missing="$missing qemu-utils"
    command -v tar >/dev/null 2>&1 || missing="$missing tar"

    if [ -n "$missing" ]; then
        echo "ERROR: Missing dependencies:$missing"
        echo "Install with: apt install$missing"
        exit 1
    fi
}

# Detect input format
detect_format() {
    local file="$1"
    case "${file,,}" in
        *.vmdk) echo "vmdk" ;;
        *.vhd)  echo "vpc" ;;   # qemu-img uses "vpc" for VHD
        *.vhdx) echo "vhdx" ;;
        *.qcow2) echo "qcow2" ;;
        *.raw|*.img) echo "raw" ;;
        *.ova) echo "ova" ;;
        *)
            # Try to detect from file content
            local magic
            magic=$(file "$file" 2>/dev/null || echo "")
            case "$magic" in
                *VMDK*) echo "vmdk" ;;
                *QCOW*) echo "qcow2" ;;
                *"Microsoft Disk Image"*) echo "vpc" ;;
                *) echo "raw" ;;
            esac
            ;;
    esac
}

# Extract disk from OVA
extract_ova() {
    local ova="$1"
    local workdir="$2"

    echo "Extracting OVA..."
    tar -xf "$ova" -C "$workdir"

    # Find the disk file (usually .vmdk)
    local disk
    disk=$(find "$workdir" -name "*.vmdk" -o -name "*.vhd" -o -name "*.qcow2" | head -1)

    if [ -z "$disk" ]; then
        echo "ERROR: No disk file found in OVA"
        exit 1
    fi

    echo "Found disk: $disk"
    echo "$disk"
}

# Convert and compress
convert_disk() {
    local input="$1"
    local output="$2"
    local format="$3"

    local tmpraw="${output%.gz}"
    [ "$tmpraw" = "$output" ] && tmpraw="${output}.tmp"

    echo ""
    echo "Input:  $input"
    echo "Format: $format"
    echo "Output: $output"
    echo ""

    if [ "$format" = "raw" ]; then
        echo "Input is already raw, compressing..."
        compress_file "$input" "$output"
    else
        echo "Converting $format to raw..."
        qemu-img convert -p -f "$format" -O raw "$input" "$tmpraw"

        echo "Compressing..."
        compress_file "$tmpraw" "$output"
        rm -f "$tmpraw"
    fi
}

# Compress with best available tool
compress_file() {
    local input="$1"
    local output="$2"

    # Use pigz for parallel compression if available
    if command -v pigz >/dev/null 2>&1; then
        echo "Using pigz for parallel compression..."
        pigz -c -9 "$input" > "$output"
    else
        echo "Using gzip..."
        gzip -c -9 "$input" > "$output"
    fi
}

# Main
main() {
    [ $# -lt 1 ] && usage

    check_deps

    local input="$1"
    local output="${2:-}"

    if [ ! -f "$input" ]; then
        echo "ERROR: Input file not found: $input"
        exit 1
    fi

    # Generate output filename if not provided
    if [ -z "$output" ]; then
        local basename="${input%.*}"
        output="${basename}.raw.gz"
    fi

    local format
    format=$(detect_format "$input")
    echo "Detected format: $format"

    # Handle OVA specially
    if [ "$format" = "ova" ]; then
        local workdir
        workdir=$(mktemp -d)
        trap "rm -rf '$workdir'" EXIT

        local disk
        disk=$(extract_ova "$input" "$workdir")
        format=$(detect_format "$disk")
        input="$disk"
    fi

    # Get disk info
    echo ""
    echo "=== Disk Information ==="
    qemu-img info "$input" 2>/dev/null || true
    echo ""

    convert_disk "$input" "$output" "$format"

    echo ""
    echo "=== Conversion Complete ==="
    echo "Output: $output"
    ls -lh "$output"
    echo ""
    echo "To deploy this image, create a workflow:"
    echo ""
    echo '{'
    echo '  "id": "my-image",'
    echo '  "name": "My OS Image",'
    echo '  "install_method": "image",'
    echo "  \"image_url\": \"http://your-server/images/$(basename "$output")\","
    echo '  "target_device": "/dev/sda"'
    echo '}'
}

main "$@"
