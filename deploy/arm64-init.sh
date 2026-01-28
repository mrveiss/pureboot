#!/bin/sh
# PureBoot ARM64 Init Script
# Runs as /init in the initramfs for Raspberry Pi boot

# Mount essential filesystems
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts

# Enable kernel messages on console
echo 1 > /proc/sys/kernel/printk

echo ""
echo "====================================="
echo "   PureBoot ARM64 Deploy Environment"
echo "====================================="
echo ""

# Wait for storage devices to settle
echo "Waiting for devices..."
sleep 2

# Trigger udev if available
if [ -x /sbin/udevd ]; then
    /sbin/udevd --daemon
    udevadm trigger
    udevadm settle --timeout=10
fi

# Bring up loopback
ip link set lo up

# Wait for ethernet interface
echo "Waiting for network interface..."
for i in $(seq 1 30); do
    if ip link show eth0 2>/dev/null | grep -q "state UP"; then
        break
    fi
    if ip link show end0 2>/dev/null | grep -q "state UP"; then
        break
    fi
    # Try to bring up interface
    for iface in eth0 end0; do
        ip link set "$iface" up 2>/dev/null || true
    done
    sleep 1
done

# Get IP via DHCP
echo "Getting IP address via DHCP..."
for iface in eth0 end0; do
    if ip link show "$iface" 2>/dev/null; then
        udhcpc -i "$iface" -t 10 -n 2>/dev/null && break
    fi
done

# Show network config
echo ""
echo "Network configuration:"
ip addr show | grep -E "^[0-9]|inet " | head -10
echo ""

# Run PureBoot Pi deploy dispatcher
if [ -x /usr/local/bin/pureboot-pi-deploy.sh ]; then
    exec /usr/local/bin/pureboot-pi-deploy.sh
else
    echo "ERROR: Deploy script not found"
    echo "Dropping to shell..."
    exec /bin/sh
fi
