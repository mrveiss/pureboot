#!/bin/bash
# Build Unified Kernel Image (UKI) for PureBoot deploy environment
#
# A UKI bundles kernel + initrd + cmdline into a single EFI binary,
# allowing iPXE EFI to boot it directly (no bzImage support needed).
#
# Usage: ./build-uki.sh [output_dir]

set -e

OUTPUT_DIR="${1:-/opt/pureboot/tftp/deploy}"
KERNEL="$OUTPUT_DIR/vmlinuz-virt"
INITRD="$OUTPUT_DIR/initramfs-virt"

# Default cmdline - PureBoot will append node-specific params
CMDLINE="ip=dhcp console=ttyS0 console=tty0"

# Check dependencies
if ! command -v objcopy &> /dev/null; then
    echo "Installing binutils for objcopy..."
    apt-get update && apt-get install -y binutils
fi

# Check for systemd-stub or create minimal EFI stub
STUB=""
for stub_path in \
    /usr/lib/systemd/boot/efi/linuxx64.efi.stub \
    /usr/lib/gummiboot/linuxx64.efi.stub \
    /boot/efi/EFI/systemd/systemd-bootx64.efi; do
    if [ -f "$stub_path" ]; then
        STUB="$stub_path"
        break
    fi
done

if [ -z "$STUB" ]; then
    echo "No EFI stub found. Installing systemd-boot-efi..."
    apt-get update && apt-get install -y systemd-boot-efi || {
        echo "ERROR: Could not find or install EFI stub"
        echo "Manual install: apt-get install systemd-boot-efi"
        exit 1
    }
    STUB="/usr/lib/systemd/boot/efi/linuxx64.efi.stub"
fi

if [ ! -f "$KERNEL" ] || [ ! -f "$INITRD" ]; then
    echo "ERROR: Kernel or initrd not found"
    echo "  Kernel: $KERNEL"
    echo "  Initrd: $INITRD"
    exit 1
fi

echo "Building Unified Kernel Image..."
echo "  Kernel: $KERNEL"
echo "  Initrd: $INITRD"
echo "  Cmdline: $CMDLINE"
echo "  Stub: $STUB"

# Create cmdline file (null-terminated)
CMDLINE_FILE=$(mktemp)
echo -n "$CMDLINE" > "$CMDLINE_FILE"

# Build UKI using objcopy
# Sections: .cmdline, .linux (kernel), .initrd
UKI_OUTPUT="$OUTPUT_DIR/pureboot-deploy.efi"

objcopy \
    --add-section .cmdline="$CMDLINE_FILE" --change-section-vma .cmdline=0x30000 \
    --add-section .linux="$KERNEL" --change-section-vma .linux=0x2000000 \
    --add-section .initrd="$INITRD" --change-section-vma .initrd=0x3000000 \
    "$STUB" "$UKI_OUTPUT"

rm -f "$CMDLINE_FILE"

# Verify
if [ -f "$UKI_OUTPUT" ]; then
    SIZE=$(stat -c%s "$UKI_OUTPUT")
    echo ""
    echo "SUCCESS: Built $UKI_OUTPUT"
    echo "  Size: $SIZE bytes ($(numfmt --to=iec $SIZE))"
    echo ""
    echo "To use: chain http://server/tftp/deploy/pureboot-deploy.efi"
else
    echo "ERROR: Failed to create UKI"
    exit 1
fi
