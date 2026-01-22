# PureBoot Bootloaders

Pre-built bootloader binaries stored in the repository to ensure reproducible deployments without external dependencies.

## Files

### UEFI

- `uefi/ipxe.efi` - netboot.xyz-snponly.efi with IMAGE_BZIMAGE support
  - Source: https://boot.netboot.xyz/ipxe/netboot.xyz-snponly.efi
  - Required for booting Linux kernels in UEFI mode (Hyper-V Gen2, modern hardware)
  - SNP = Simple Network Protocol, no embedded scripts (boots via DHCP)

### BIOS

- `bios/undionly.kpxe` - Standard iPXE BIOS bootloader
  - Source: https://boot.ipxe.org/undionly.kpxe
  - For legacy BIOS PXE boot

## Updating Bootloaders

To update these files:

```bash
# UEFI (with bzImage support)
curl -fsSL -o bootloaders/uefi/ipxe.efi "https://boot.netboot.xyz/ipxe/netboot.xyz-snponly.efi"

# BIOS
curl -fsSL -o bootloaders/bios/undionly.kpxe "https://boot.ipxe.org/undionly.kpxe"
```

## Why Store in Repo?

1. **Reproducibility** - Same binaries across all deployments
2. **Offline Install** - No internet required during setup
3. **Version Control** - Track changes to boot infrastructure
4. **No External Dependencies** - ipxe.org/netboot.xyz availability doesn't affect deployments
