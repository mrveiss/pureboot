# PureBoot - Unified Enterprise Provisioning Platform

## Product Requirements Document (PRD)

**Version:** 2.0
**Date:** 2024
**Status:** Final
**Author:** Martins Veiss (mrveiss)

---

## 1. Executive Summary

PureBoot is a vendor-neutral, self-hosted provisioning and orchestration system designed to automate the entire lifecycle of diverse hardware platforms. It provides a unified control plane for x86 servers, enterprise laptops, virtual machines (VMs), Raspberry Pi nodes, edge devices, and integrates with major hypervisor platforms including oVirt/RHV.

### Key Value Proposition

- **Unified Provisioning:** Single platform for x86 BIOS/UEFI, ARM (Raspberry Pi), VMs, and enterprise laptops
- **Enterprise Virtualization:** Full integration with oVirt/RHV, Proxmox, VMware, Hyper-V, and KVM
- **Lightweight & Portable:** Runs on NAS devices, Raspberry Pi, or small VMs
- **Vendor Neutral:** No lock-in to specific hardware or cloud providers
- **Dual Licensing:** Free for homelab/personal use, paid for commercial deployments
- **Autonomous Post-Install:** Nodes boot from local disk after provisioning
- **Advanced Security:** Four-Eye Principle, RBAC, and comprehensive audit trails

---

## 2. Problem Statement

Modern infrastructure environments suffer from slow, manual, and inconsistent provisioning across mixed architectures. Existing solutions are frequently too complex, resource-heavy, or lack adequate support for ARM-based systems and enterprise virtualization platforms.

### Current Market Gaps

| Issue | Impact |
|-------|--------|
| Heavy/Complex Tools (MAAS, Foreman, Cobbler) | Overkill for homelabs, complex setup |
| Vendor Lock-in (SCCM, Intune) | Forces cloud/enterprise dependencies |
| Lack of ARM Support | Raspberry Pi and SBCs not supported |
| Limited Virtualization Integration | Poor hypervisor API support |
| Windows/AD Integration Gaps | Difficult to automate domain joins |
| No Unified Platform | Separate tools for different architectures |
| No Enterprise Security | Missing RBAC and audit capabilities |

### Target Pain Points

- Manual, error-prone provisioning processes
- Inconsistent deployments across hardware types
- Lack of Raspberry Pi/ARM support in enterprise tools
- Complex Windows automation requiring SCCM/MDT
- Limited hypervisor integration capabilities
- No lightweight, self-hosted alternative with enterprise features
- Missing compliance and security features

---

## 3. Target Users

### 3.1 Primary Users (Free Tier)

**Homelab Enthusiasts**
- Personal experimentation and learning
- Mixed hardware environments (servers, Pis, VMs)
- Educational use in makerspaces, schools, universities
- Research labs and robotics projects

**Edge Compute & IoT Developers**
- Raspberry Pi clusters and ARM SBC deployments
- Edge device provisioning and management
- IoT gateway and sensor network setup

### 3.2 Commercial Users (Paid Tier)

**Small & Medium Businesses**
- On-prem server and laptop provisioning
- Mixed hardware environments
- Limited IT staff requiring automation

**Managed Service Providers**
- Multi-client provisioning workflows
- Standardized deployment templates
- Client-specific configuration management

**Enterprise & Datacenters**
- Large-scale server deployments
- Hybrid cloud/on-prem environments
- Kubernetes and container host provisioning
- oVirt/RHV virtualization management

**Research & Industrial**
- Robotics labs and manufacturing edge devices
- High-performance computing clusters
- Specialized hardware deployments

---

## 4. Product Architecture

### 4.1 High-Level Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                        PureBoot Platform                        │
├─────────────────┬─────────────────┬─────────────────┬───────────┤
│  PXE/iPXE/UEFI  │  Controller API │   Web UI        │  Storage  │
│  Infrastructure │  (Workflows,    │  (Management,   │  Backend   │
│                 │   Templates,    │   Monitoring)   │           │
│                 │   Node Registry)│                 │           │
└─────────────────┴─────────────────┴─────────────────┴───────────┘
                                      │
                                      ▼
┌───────────────────────────────────────────────────────────────┐
│                        Target Devices                          │
├─────────────┬─────────────┬─────────────┬─────────────┬───────┤
│  Bare-Metal  │  Enterprise  │  Virtual    │  Raspberry  │  Edge  │
│  Servers     │  Laptops     │  Machines   │  Pi/ARM     │  IoT   │
└─────────────┴─────────────┴─────────────┴─────────────┴───────┘
                                      │
                                      ▼
┌───────────────────────────────────────────────────────────────┐
│                    Hypervisor Platforms                        │
├─────────────────┬─────────────────┬─────────────────┬───────────┤
│  oVirt/RHV      │  Proxmox VE     │  VMware ESXi    │  Hyper-V  │
│  KVM/Libvirt    │                 │                 │           │
└─────────────────┴─────────────────┴─────────────────┴───────────┘
```

### 4.2 Core Components

**1. PXE/iPXE/UEFI Boot Infrastructure**
- TFTP server for boot files
- HTTP server for ISOs and templates
- DHCP integration (Options 66/67)
- Bootloader support (PXELINUX, GRUB2, iPXE, Raspberry Pi firmware)
- Provisioning-only DHCP mode to prevent interference with production

**2. Controller Service**
- REST API for node management
- Workflow engine with state machine
- Template storage and management
- Node registry and state tracking
- Decision logic for per-node provisioning
- oVirt/RHV integration module

**3. Web User Interface**
- Node discovery and management
- Workflow creation and editing
- Boot menu configuration
- Provisioning status monitoring
- Logs and audit trails
- Hypervisor integration dashboard

**4. Storage Backend**
- TFTP root for boot files
- HTTP repository for ISOs
- NFS/iSCSI for temporary storage
- Database for node registry and workflows
- oVirt storage domain integration

**5. Template Storage**
- Block-level templates (raw, qcow2, VHDX)
- File-level templates (WIM, tar.gz, squashfs)
- Versioned template management
- oVirt template synchronization

### 4.3 Supported Boot Methods

| Boot Method | Use Case | Supported Platforms |
|-------------|----------|---------------------|
| BIOS PXE | Legacy systems | x86 servers, older laptops |
| UEFI PXE | Modern systems | x86 servers, newer laptops |
| iPXE | Advanced scripting | All x86 platforms |
| UEFI HTTP Boot | Fast network boot | Modern UEFI systems |
| Raspberry Pi Network Boot | ARM SBCs | Raspberry Pi 3/4/5, other ARM devices |

### 4.4 Supported Bootloaders

| Bootloader | Architecture | Use Case |
|------------|--------------|----------|
| PXELINUX | BIOS | Legacy x86 systems |
| GRUB2 | UEFI | Modern x86 systems |
| iPXE | BIOS/UEFI | Advanced scripting and chainloading |
| Raspberry Pi Firmware | ARM | Raspberry Pi network boot |

---

## 5. Supported Platforms

### 5.1 Comprehensive Platform Support Matrix

| Platform Category | Specific Platforms | Boot Method | OS Support |
|-------------------|--------------------|-------------|------------|
| **Bare-Metal Servers** | x86 servers, workstations | BIOS/UEFI PXE | Ubuntu, Debian, Fedora, Rocky/Alma, Arch, Windows |
| **Enterprise Laptops** | Dell, HP, Lenovo, etc. | BIOS/UEFI PXE | Windows (with AD join), Linux |
| **Hyper-V VMs** | Generation 1 & 2 | PXE boot | Windows, Linux |
| **VMware ESXi** | ESXi hosts | PXE/kickstart | ESXi installation |
| **Proxmox VE** | Proxmox hosts | PXE/preseed | Proxmox installation |
| **KVM/Libvirt** | Virtual machines | PXE boot | Linux, Windows |
| **oVirt/RHV VMs** | oVirt managed VMs | API-driven | Linux, Windows |
| **Docker Hosts** | Container hosts | PXE boot | Linux with Docker/containerd |
| **Kubernetes Nodes** | Worker nodes | PXE → kubeadm | Linux distributions |
| **Raspberry Pi** | Pi 3/4/5, Compute Modules | Network boot | Raspberry Pi OS, Ubuntu ARM |
| **ARM SBCs** | Other ARM boards | Network boot | ARM64 Linux |
| **OpenWrt Routers** | x86 routers | PXE boot | OpenWrt |
| **Thin Clients** | IGEL, HP ThinPro | PXE boot | Thin client OS |
| **UEFI HTTP Boot** | Modern hardware | HTTP boot | Windows, Linux |
| **Edge/IoT Devices** | Industrial devices | Network boot | Custom Linux |

---

## 6. Node Lifecycle Management

### 6.1 State Machine

```
┌───────────────────────────────────────────────────────────────┐
│                        PureBoot State Machine                   │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐       ┌─────────────┐       ┌─────────────┐  │
│  │  discovered  │──────▶│   pending    │──────▶│  installing  │  │
│  └─────────────┘       └─────────────┘       └─────────────┘  │
│         ▲                     │                     │         │
│         │                     ▼                     ▼         │
│  ┌─────────────┐       ┌─────────────┐       ┌─────────────┐  │
│  │   retired    │◀─────│   active     │◀─────│  installed   │  │
│  └─────────────┘       └─────────────┘       └─────────────┘  │
│         ▲                     │                             │
│         │                     ▼                             │
│  ┌─────────────┐       ┌─────────────┐                       │
│  │ deprovision │◀─────│  migrating  │                       │
│  └─────────────┘       └─────────────┘                       │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### 6.2 State Definitions

**discovered**
- Node appears via PXE request
- Controller identifies by MAC address/serial
- No workflow assigned
- Node waits for admin action

**pending**
- Admin assigns workflow (Windows install, Linux install, etc.)
- Node ready for next PXE boot
- Configuration prepared but not executed

**installing**
- Node boots via PXE
- Controller serves installation instructions
- OS installs to local disk
- Domain join/cloud-init/scripts execute
- Progress tracked and logged

**installed**
- Controller marks node as complete
- PXE requests now return "boot from disk"
- Node prepared for first local boot
- Final configuration applied

**active**
- Node boots from local disk
- No PXE involvement
- Managed by external systems (AD, Ansible, Salt, etc.)
- Regular health checks and monitoring

**reprovision**
- Admin triggers reinstall
- Controller resets node state
- Next PXE boot starts fresh installation
- Previous configuration archived

**retired**
- Node removed from active inventory
- PXE requests ignored or blocked
- Configuration archived
- Resources released

**deprovisioning** *(NEW)*
- Secure data erasure before repurposing
- Uses `blkdiscard` for SSD or `shred` for HDD
- Compliance with data security requirements
- Prevents data leakage on hardware reuse

**migrating** *(NEW)*
- 1:1 hardware replacement workflow
- Snapshots source disk to temporary iSCSI LUN
- Restores to target device
- Maintains system configuration and data integrity

### 6.3 Boot Behavior Rules

**Rule A:** PXE boot is mandatory only during the installation phase.

**Rule B (Post-Install):** After installation, the PXE server must return a "boot from local disk" command:
- PXELINUX: `LOCALBOOT 0`
- iPXE: `sanboot --drive 0x80`
- GRUB: `chainloader (hd0)+1`

**Rule C:** Reinstallations occur only if explicitly requested by an admin.

**Rule D (Offline Resilience):** If the network or controller is offline, nodes must still be able to boot from their local disks normally.

**Rule E (Provisioning-Only DHCP):** *(NEW)* DHCP leases are only assigned to nodes in provisioning states (discovered, pending, installing) to prevent interference with production systems.

---

## 7. Provisioning Workflows

### 7.1 Linux Provisioning Workflow

```
┌───────────────────────────────────────────────────────────────┐
│                        Linux Provisioning                      │
├───────────────────────────────────────────────────────────────┤
│ 1. PXE Boot → Kernel/Initrd Load                             │
│ 2. Autoinstall/Cloud-init Configuration                      │
│ 3. Disk Partitioning                                         │
│ 4. OS Installation                                           │
│ 5. Post-Install Scripts                                      │
│ 6. Reboot → Local Disk                                       │
└───────────────────────────────────────────────────────────────┘
```

**Supported Linux Distributions:**
- Ubuntu (autoinstall)
- Debian (preseed)
- Fedora/Rocky/Alma (kickstart)
- Arch Linux (bootstrap)
- Raspberry Pi OS (ARM-specific)

### 7.2 Windows Enterprise Provisioning Workflow

```
┌───────────────────────────────────────────────────────────────┐
│                    Windows Provisioning                        │
├───────────────────────────────────────────────────────────────┤
│ 1. PXE Boot → WinPE                                          │
│ 2. WinPE Contacts Controller                                 │
│ 3. Controller Provides:                                      │
│    - Windows Image (WIM)                                     │
│    - autounattend.xml                                        │
│    - Drivers                                                 │
│    - Domain Join Method                                      │
│ 4. Windows Installation                                      │
│ 5. Domain Join (Online or Offline)                           │
│ 6. Reboot → Local Disk                                       │
│ 7. GPO & Software Deployment (AD-managed)                     │
└───────────────────────────────────────────────────────────────┘
```

**Domain Join Methods:**

**Online Domain Join:**
```xml
<Identification>
    <JoinDomain>corp.example.com</JoinDomain>
    <Credentials>
        <Domain>corp.example.com</Domain>
        <Username>joinaccount</Username>
        <Password>...</Password>
    </Credentials>
</Identification>
```

**Offline Domain Join (ODJ):**
```bash
# Controller generates:
djoin.exe /provision /domain corp.example.com /machine LAPTOP123 /savefile odjblob.txt

# WinPE applies:
djoin.exe /requestodj /loadfile odjblob.txt /windowspath C:\Windows /localos
```

**Post-Install Features:**
- BitLocker enablement
- Driver injection
- PowerShell script execution
- Software package installation
- Security baseline application

### 7.3 Raspberry Pi Provisioning Workflow

```
┌───────────────────────────────────────────────────────────────┐
│                    Raspberry Pi Provisioning                   │
├───────────────────────────────────────────────────────────────┤
│ 1. Network Boot via Pi Firmware                              │
│ 2. Per-Node Identity via Serial Number                       │
│ 3. NFS/iSCSI Root Filesystem                                 │
│ 4. ARM64 Template Application                                │
│ 5. Post-Boot Configuration                                   │
│ 6. Cluster Integration (if applicable)                       │
└───────────────────────────────────────────────────────────────┘
```

**Raspberry Pi Specifics:**
- Uses Pi's built-in network boot firmware
- Requires specific boot files (bootcode.bin, start4.elf, etc.)
- Supports per-device configuration via serial number
- NFS/iSCSI root filesystem support
- ARM64 Linux distribution support

### 7.4 oVirt/RHV VM Provisioning Workflow *(NEW)*

```
┌───────────────────────────────────────────────────────────────┐
│                    oVirt/RHV Provisioning                      │
├───────────────────────────────────────────────────────────────┤
│ 1. PureBoot API Request                                      │
│ 2. oVirt Template Selection                                  │
│ 3. VM Creation via oVirt API                                 │
│ 4. Resource Allocation (CPU, Memory, Storage)                │
│ 5. Network Configuration                                     │
│ 6. Disk Attachment (Template + Additional Disks)             │
│ 7. VM Start and Monitoring                                   │
│ 8. Post-Provisioning Configuration                           │
└───────────────────────────────────────────────────────────────┘
```

**oVirt Integration Features:**
- REST API v4 integration
- Template-based VM provisioning
- Dynamic resource allocation
- Storage domain management
- Live migration capabilities
- High availability configuration

---

## 8. Controller API Design

### 8.1 REST API Endpoints

**Node Management:**
```http
GET    /api/v1/nodes                  # List all nodes
GET    /api/v1/nodes/{id}             # Get node details
POST   /api/v1/nodes                  # Register new node
PATCH  /api/v1/nodes/{id}             # Update node
PATCH  /api/v1/nodes/{id}/state       # Transition state (with validation)
DELETE /api/v1/nodes/{id}             # Retire node
POST   /api/v1/nodes/{id}/approve     # Four-Eye Principle approval
```

**Workflow Management:**
```http
GET    /api/v1/workflows              # List available workflows
GET    /api/v1/workflows/{id}         # Get workflow details
POST   /api/v1/workflows              # Create new workflow
PATCH  /api/v1/workflows/{id}         # Update workflow
DELETE /api/v1/workflows/{id}         # Delete workflow
```

**Hypervisor Integration *(NEW)*:**
```http
GET    /api/v1/hypervisors            # List connected hypervisors
POST   /api/v1/hypervisors            # Add new hypervisor connection
GET    /api/v1/hypervisors/{id}/vms   # List VMs on hypervisor
POST   /api/v1/hypervisors/{id}/vms   # Create VM on hypervisor
POST   /api/v1/hypervisors/{id}/sync  # Sync templates with hypervisor
```

**Provisioning API:**
```http
GET    /api/v1/next?mac={mac}         # Get next instructions
POST   /api/v1/report                 # Node status reporting
POST   /api/v1/deprovision            # Secure data erasure
POST   /api/v1/migrate                # Hardware migration
```

**Template Management:**
```http
GET    /api/v1/templates              # List templates
GET    /api/v1/templates/{id}         # Get template
POST   /api/v1/templates              # Upload template
DELETE /api/v1/templates/{id}         # Delete template
POST   /api/v1/templates/sync         # Sync with hypervisors
```

### 8.2 Authentication & Security

- **Token-based authentication** (JWT)
- **Role-based access control** (Admin, Operator, Auditor, User)
- **Secure credential storage** (encrypted, access-controlled)
- **Four-Eye Principle** for critical operations
- **Audit logging** for all sensitive operations
- **API rate limiting** to prevent abuse

### 8.3 Example API Flow

**Node Discovery & Provisioning:**

1. **Node PXE boots and contacts controller:**
```http
GET /api/v1/next?mac=AA:BB:CC:DD:EE:FF
```

2. **Controller responds with workflow:**
```json
{
  "workflow": "ubuntu-2404-server",
  "kernel": "http://pureboot.local/tftp/ubuntu/vmlinuz",
  "initrd": "http://pureboot.local/tftp/ubuntu/initrd",
  "autoinstall": "http://pureboot.local/templates/ubuntu-2404.yaml",
  "post_install": ["http://pureboot.local/scripts/setup.sh"],
  "hypervisor": "ovirt",
  "template": "ubuntu-2404-template"
}
```

3. **Node reports progress:**
```http
POST /api/v1/report
{
  "node_id": "node-123",
  "status": "installing",
  "progress": 75,
  "logs": ["Partitioning complete", "Package installation in progress"]
}
```

---

## 9. Workflow Engine

### 9.1 Core Features

- **State Machine Driven:** Manages node lifecycle transitions with validation
- **Conditional Logic:** Per-node decision making based on hardware, location, etc.
- **Task Orchestration:** Sequences installation steps and post-install actions
- **Error Handling:** Retry logic and fallback mechanisms
- **Four-Eye Principle:** Dual approval for critical operations
- **Logging & Auditing:** Comprehensive activity tracking

### 9.2 Supported Task Types

| Task Type | Description | Example |
|-----------|-------------|---------|
| **PXE Boot** | Serve boot files | GRUB/PXELINUX/iPXE |
| **Image Deploy** | Deploy OS image | WIM, ISO, tar.gz |
| **Disk Wipe** | Secure disk erasure | dd, blkdiscard, shred |
| **Partition** | Disk partitioning | parted, fdisk |
| **Domain Join** | AD integration | Online/Offline join |
| **Script Run** | Custom scripts | Bash, PowerShell |
| **Package Install** | Software packages | apt, yum, choco |
| **Reboot** | System restart | Immediate/delayed |
| **Chain Boot** | Bootloader chain | LOCALBOOT, sanboot |
| **oVirt VM Create** | *(NEW)* | VM provisioning via API |
| **Template Sync** | *(NEW)* | Hypervisor template sync |
| **Live Migrate** | *(NEW)* | VM migration between hosts |

### 9.3 Workflow Examples

**Ubuntu Server Workflow:**
```yaml
name: ubuntu-2404-server
description: Ubuntu 24.04 LTS Server Installation
tasks:
  - type: pxe_boot
    bootloader: grub
    kernel: /tftp/ubuntu/vmlinuz
    initrd: /tftp/ubuntu/initrd
    cmdline: "ip=dhcp url=http://pureboot.local/ubuntu-2404.iso"
  
  - type: image_deploy
    image: /templates/ubuntu-2404.tar.gz
    target: /dev/sda
    
  - type: script_run
    script: /scripts/post-install.sh
    
  - type: reboot
    delay: 10
    
  - type: chain_boot
    method: grub
    target: (hd0)+1
```

**oVirt VM Provisioning Workflow *(NEW)*:**
```yaml
name: ovirt-ubuntu-vm
description: oVirt Ubuntu VM Provisioning
tasks:
  - type: ovirt_vm_create
    template: ubuntu-2404-template
    cluster: Default
    memory: 4096
    cores: 2
    disks:
      - size: 20GB
        storage_domain: data
        interface: virtio
    networks:
      - name: ovirtmgmt
        profile: default
    
  - type: ovirt_vm_start
    wait_for_ip: true
    
  - type: ovirt_vm_configure
    cloud_init:
      hostname: pureboot-node-{{ node_id }}
      users:
        - name: admin
          ssh_authorized_keys: ["ssh-rsa ..."]
      packages: ["qemu-guest-agent", "openssh-server"]
```

---

## 10. Storage & Template Management

### 10.1 ISO Handling

- **Centralized Repository:** Controller downloads and caches ISOs
- **Automatic Extraction:** Kernel/initrd or WIM files extracted
- **HTTP Serving:** Installation media served via web server
- **Version Management:** Multiple versions supported

### 10.2 Temporary Storage

**iSCSI LUNs:**
- Temporary storage for large files
- Per-node unique LUNs
- Used for ISO staging, WIM files, driver injection
- Destroyed after provisioning complete

**NFS Shares:**
- Raspberry Pi root filesystems
- Shared storage for cluster nodes
- Read-only templates

**oVirt Storage Domains *(NEW)*:**
- Integration with oVirt storage domains
- Template synchronization
- Disk management via oVirt API
- Storage migration capabilities

### 10.3 Template Types

**Block-Level Templates:**
- Formats: raw, qcow2, VHDX
- Fast cloning to local disk (under 5 minutes)
- Ideal for identical deployments
- Versioned and immutable

**File-Level Templates:**
- Formats: WIM, tar.gz, squashfs
- Extracted during provisioning
- Customizable per-node
- Smaller storage footprint

**oVirt Templates *(NEW)*:**
- Pre-configured VM templates in oVirt
- Cloud-init integration
- Synchronized with PureBoot template library
- Version control and management

---

## 11. Hypervisor Integration

### 11.1 Supported Hypervisors

| Hypervisor | Integration Level | Capabilities |
|------------|-------------------|--------------|
| **Hyper-V** | Full API | VM creation, PXE boot, template cloning |
| **Proxmox VE** | Full API | VM/container creation, template management |
| **KVM/Libvirt** | Full API | VM lifecycle, storage management |
| **VMware ESXi** | Partial API | VM creation, basic management |
| **XCP-ng** | Optional | VM lifecycle management |
| **oVirt/RHV** | Full API | Enterprise virtualization, HA, live migration, storage domains |

### 11.2 Hypervisor Capabilities

- **VM Creation:** Instantiate new virtual machines
- **Template Cloning:** Fast deployment from golden images
- **Storage Management:** Attach/detach disks and ISOs
- **Network Configuration:** Configure virtual networks
- **Power Management:** Start/stop/reset VMs
- **PXE Boot Triggering:** Force VMs to PXE boot
- **Resource Allocation:** CPU/RAM configuration
- **Live Migration:** Migrate running VMs between hosts *(oVirt/RHV)*
- **High Availability:** Configure HA policies *(oVirt/RHV)*
- **Storage Migration:** Move disks between storage domains *(oVirt/RHV)*

### 11.3 oVirt/RHV Specific Features *(NEW)*

**Enterprise Virtualization:**
- Full API support for oVirt/RHV 4.4+
- Template-based VM provisioning
- Storage domain management
- Live migration capabilities
- High availability configuration
- Software-defined networking
- Resource optimization and QoS

**Integration Benefits:**
- Unified management of physical and virtual resources
- Automated VM provisioning workflows
- Template synchronization between PureBoot and oVirt
- Advanced storage management
- High availability for critical workloads
- Live migration for maintenance without downtime

### 11.4 Benefits of Hypervisor Integration

- **On-Demand Compute:** Rapid VM provisioning
- **Template-Based Deployment:** Consistent environments
- **Unified Lifecycle:** Physical + virtual management
- **Kubernetes Ready:** Easy cluster node provisioning
- **CI/CD Integration:** Test environment automation
- **Enterprise Features:** HA, live migration, advanced networking
- **Resource Optimization:** Dynamic resource allocation

---

## 12. Security Architecture

### 12.1 Critical Security Considerations

**1. Risk of Data Loss/Downtime:**
- Strict safeguards against accidental reprovisioning
- RBAC with approval workflows
- Confirmation prompts for destructive actions
- Four-Eye Principle for critical operations

**2. Credential Management:**
- Encrypted credential storage
- Integration with external vaults (HashiCorp, Azure Key Vault)
- Automated credential rotation
- Audit logging of credential access

**3. Approval & Audit Trails:**
- Explicit approval for sensitive operations
- Comprehensive audit logging
- Immutable logs for compliance
- Detailed activity tracking

**4. Fail-Safe Mechanisms:**
- Dry-run/simulation modes
- Multi-step confirmation for critical actions
- Rollback capabilities
- State validation before transitions

**5. Network Security:**
- Isolation of provisioning networks
- Firewall segmentation
- TLS for all communications
- Provisioning-only DHCP mode

**6. Monitoring & Alerting:**
- Real-time activity monitoring
- Anomaly detection
- Alerting for unauthorized actions
- Integration with SIEM systems

**7. Backup & Recovery:**
- Regular configuration backups
- Disaster recovery procedures
- Configuration versioning
- Database replication

### 12.2 Four-Eye Principle Implementation

**Requirements:**
- Critical actions require dual approval
- Clear audit trail of initiators and approvers
- Role separation (requester vs. approver)
- Time-limited approval windows

**Critical Actions Requiring Dual Approval:**
- Node reprovisioning (wiping and reinstalling)
- Credential changes
- System-wide configuration modifications
- Audit log clearing
- Emergency access requests
- Deprovisioning (secure data erasure)
- Hardware migration operations

**Example Workflow:**
```
1. Admin requests node reprovisioning → System pending approval
2. Second admin reviews request details
3. Second admin approves action → Action executed
4. Both actions logged with timestamps and identities
```

### 12.3 Legal Protection Framework

**Terms of Service:**
- User responsibility for correct configuration
- Provider not liable for misconfiguration damages
- "As-is" provisioning without outcome warranties

**End User License Agreement:**
- Free for homelab/personal use
- Commercial use requires paid license
- Support and updates included in commercial tier

**User Responsibility:**
- Acknowledge risks before use
- Follow documented best practices
- Regular training and certification recommended

---

## 13. Licensing Model

### 13.1 Dual Licensing Structure

**Free Tier (Homelab/Personal):**
- Unlimited nodes
- All features enabled
- No license keys or tracking
- Community support only
- No commercial use allowed

**Paid Tier (Commercial):**
- Required for business/enterprise use
- Priority support included
- Advanced features (RBAC, audit logs, multi-site)
- SLA options available
- Volume licensing discounts
- oVirt/RHV integration support

### 13.2 Use Case Definitions

**Homelab Use:**
- Personal, non-commercial use
- Educational institutions
- Hobbyist projects
- Research and development (non-revenue)

**Commercial Use:**
- Business environments
- Revenue-generating activities
- Enterprise deployments
- Managed service providers
- Government and public sector

### 13.3 Pricing Strategy

**Subscription Model:**
- Monthly/Annual subscriptions
- Tiered based on node count and features
- Includes support and updates

**Perpetual License:**
- One-time purchase
- Optional maintenance contract
- Major version upgrades may require new license

**Enterprise Custom:**
- Tailored pricing for large deployments
- Volume discounts
- Custom feature development
- Dedicated support

---

## 14. Roadmap

### 14.1 Phase 1 - Core MVP (3-6 months)

**Objectives:**
- Basic PXE infrastructure (TFTP, HTTP, DHCP integration)
- Controller API with node management
- Simple workflow engine
- Basic web UI for node monitoring
- Node registry and state tracking
- Linux provisioning (Ubuntu/Debian)
- Windows basic provisioning
- Provisioning-only DHCP mode

**Deliverables:**
- Functional PXE boot environment
- REST API for node management
- Minimal web interface
- Basic provisioning workflows
- Documentation and examples

### 14.2 Phase 2 - Automation (6-12 months)

**Objectives:**
- Advanced workflow engine
- Script runner with templating
- Cluster join workflows (Kubernetes)
- Post-install orchestration
- Hypervisor API integrations (Proxmox, KVM)
- Template management system
- Four-Eye Principle implementation

**Deliverables:**
- Full workflow automation
- Hypervisor integration plugins
- Kubernetes provisioning workflows
- Advanced scripting capabilities
- Template versioning and management
- Security and compliance features

### 14.3 Phase 3 - ARM & Pi Support (12-18 months)

**Objectives:**
- Raspberry Pi network boot support
- ARM SBC provisioning workflows
- Pi cluster management
- ARM64 template support
- Edge device provisioning
- oVirt/RHV integration

**Deliverables:**
- Raspberry Pi boot firmware serving
- ARM-specific provisioning workflows
- Pi cluster orchestration
- Edge device templates
- ARM64 OS support
- oVirt API integration

### 14.4 Phase 4 - Commercial Features (18-24 months)

**Objectives:**
- Role-based access control
- Comprehensive audit logging
- Multi-site management
- Support portal and ticketing
- Enterprise authentication (LDAP, SAML)
- Advanced reporting and analytics
- oVirt advanced features (HA, live migration)

**Deliverables:**
- Full RBAC implementation
- Audit trail system
- Multi-site orchestration
- Customer support portal
- Enterprise authentication integrations
- Reporting dashboard
- oVirt deep integration

---

## 15. Success Metrics

### 15.1 Adoption Metrics

- **Homelab Adoption:** Number of GitHub stars, community contributions
- **Community Growth:** Forum activity, Discord/Slack members, contributions
- **Documentation Usage:** Views, feedback, translation contributions
- **Social Media Engagement:** Followers, mentions, shares

### 15.2 Commercial Metrics

- **License Sales:** Number of commercial licenses sold
- **Revenue Growth:** Monthly/Annual recurring revenue
- **Customer Retention:** Renewal rates, churn analysis
- **Support Tickets:** Volume, resolution time, satisfaction scores

### 15.3 Technical Metrics

- **Nodes Provisioned:** Total nodes provisioned per month
- **Deployment Time:** Average time saved per deployment
- **Success Rate:** Percentage of successful provisioning attempts
- **Error Rate:** Frequency and types of provisioning failures
- **Performance:** API response times, UI load times

### 15.4 Ecosystem Metrics

- **Integration Adoption:** Number of hypervisor integrations used
- **Template Usage:** Popular templates and workflows
- **Plugin Development:** Community-developed plugins and extensions
- **Partner Ecosystem:** Number of MSPs and integrators

---

## 16. Technical Requirements

### 16.1 System Requirements

**Minimum (Homelab):**
- CPU: 2 cores
- RAM: 4GB
- Storage: 50GB (SSD recommended)
- OS: Ubuntu 22.04 LTS or equivalent

**Recommended (Production):**
- CPU: 4+ cores
- RAM: 8GB+
- Storage: 100GB+ (SSD recommended)
- OS: Ubuntu 22.04/24.04 LTS
- Network: Gigabit Ethernet

**oVirt Integration Requirements *(NEW)*:**
- oVirt Engine 4.4+
- Python 3.8+
- ovirtsdk4 package
- Network connectivity to oVirt Engine (port 443)

### 16.2 Supported Technologies

**Boot Methods:**
- BIOS PXE, UEFI PXE, iPXE, UEFI HTTP Boot, Raspberry Pi Network Boot

**Operating Systems:**
- Ubuntu, Debian, Fedora, Rocky/Alma, Arch, Windows (all versions), Raspberry Pi OS

**Hypervisors:**
- Hyper-V, VMware ESXi, Proxmox VE, KVM/Libvirt, XCP-ng, oVirt/RHV

**Container Platforms:**
- Docker, containerd, Podman

**Orchestration:**
- Kubernetes, Nomad, Swarm

**Configuration Management:**
- Ansible, SaltStack, Puppet, Chef

**Authentication:**
- Local, LDAP, Active Directory, SAML, OAuth2

### 16.3 Database Requirements

**Supported Databases:**
- SQLite (embedded, for small deployments)
- PostgreSQL (recommended for production)
- MySQL/MariaDB (optional)

**Schema Requirements:**
- Nodes table (MAC, serial, state, metadata)
- Workflows table (definition, version, active status)
- Tasks table (workflow steps, parameters)
- Logs table (timestamp, level, message, context)
- Hypervisors table (connection details, credentials)
- Indexes on frequently queried fields

---

## 17. Unique Features & Differentiators

### 17.1 Extended Lifecycle States

**Deprovisioning State:**
- Secure data erasure before hardware repurposing
- Compliance with data security requirements
- Audit trail of wiping operations
- Uses `blkdiscard` (SSD) or `shred` (HDD)

**Migrating State:**
- 1:1 hardware replacement workflow
- Disk snapshot to temporary iSCSI LUN
- Restore to target device
- Maintains system configuration and data integrity

### 17.2 Advanced DHCP Features

**Provisioning-Only Mode:**
- DHCP leases only for nodes in provisioning states
- Prevents interference with production servers
- Avoids IP conflicts and accidental PXE boot loops
- Improves network security

### 17.3 Storage Innovations

**Temporary iSCSI Storage:**
- Per-node LUNs for large installation files
- Handles files >4GB that exceed TFTP limits
- High-speed block-level access
- Automatic cleanup after provisioning

**Template Storage System:**
- Block-level (qcow2, VHDX) and file-level (WIM, tar.gz) templates
- 75-90% reduction in deployment time
- Versioned and immutable templates
- Synchronization with hypervisor platforms

### 17.4 Windows Enterprise Support

**Complete Windows Workflow:**
- WinPE via PXE boot
- Online and Offline Domain Join (ODJ)
- Driver injection
- BitLocker enablement
- GPO takeover via Active Directory

### 17.5 oVirt/RHV Integration

**Enterprise Virtualization:**
- Full API support for oVirt/RHV 4.4+
- Template-based VM provisioning
- Storage domain management
- Live migration capabilities
- High availability configuration
- Advanced networking features

### 17.6 Security & Compliance

**Four-Eye Principle:**
- Dual approval for critical operations
- Clear audit trail
- Role separation
- Time-limited approval windows

**Comprehensive RBAC:**
- Admin, Operator, Auditor, User roles
- Fine-grained permissions
- Role inheritance and hierarchy

### 17.7 Comparison with Existing Solutions

| Feature | PureBoot | MAAS | Foreman | WDS/MDT |
|---------|----------|------|---------|---------|
| **Multi-Architecture** | ✅ (x86, ARM) | ❌ (x86 only) | ✅ (x86) | ❌ (Windows only) |
| **Lightweight** | ✅ (Runs on Pi) | ❌ (Heavy) | ❌ (Heavy) | ❌ (Windows Server) |
| **ARM Support** | ✅ (Raspberry Pi) | ❌ | ❌ | ❌ |
| **Windows AD Join** | ✅ (Online/Offline) | ❌ | ✅ | ✅ |
| **Hypervisor Integration** | ✅ (Multi) | ❌ | ✅ (Limited) | ❌ |
| **oVirt/RHV Support** | ✅ (Full API) | ❌ | ❌ | ❌ |
| **Template System** | ✅ (Block & File) | ✅ (File) | ✅ (File) | ✅ (WIM) |
| **Deprovisioning** | ✅ (Secure Wipe) | ❌ | ❌ | ❌ |
| **Migration Support** | ✅ (1:1 Replace) | ❌ | ❌ | ❌ |
| **DHCP Provisioning-Only** | ✅ | ❌ | ❌ | ❌ |
| **Four-Eye Principle** | ✅ | ❌ | ❌ | ❌ |
| **Performance** | ✅ (<5 min deploy) | ❌ (20-40 min) | ❌ (20-40 min) | ❌ (30-60 min) |

---

## 18. Implementation Considerations

### 18.1 Development Stack

**Backend:**
- Language: Python (primary), Go (alternative)
- Framework: FastAPI (Python), Gin (Go)
- Database: PostgreSQL with SQLAlchemy
- oVirt Integration: ovirtsdk4

**Frontend:**
- Framework: React
- UI Library: Tailwind CSS
- State Management: Redux Toolkit

**Infrastructure:**
- Containerization: Docker
- Orchestration: Kubernetes or Docker Compose
- CI/CD: GitHub Actions, GitLab CI

### 18.2 Deployment Options

**Homelab Deployment:**
- Docker Compose on Raspberry Pi or small VM
- SQLite database
- Minimal resource requirements

**Production Deployment:**
- Kubernetes cluster
- PostgreSQL database
- Load balancing and redundancy
- Monitoring and alerting

**Cloud Deployment:**
- AWS EKS, Azure AKS, or GCP GKE
- Managed database services
- Auto-scaling capabilities

**oVirt Integration Deployment:**
- PureBoot controller with oVirt SDK
- API connection to oVirt Engine
- Template synchronization service
- Monitoring and status reporting

### 18.3 Integration Points

**Hypervisor APIs:**
- Hyper-V: PowerShell, REST
- Proxmox: REST API
- VMware: vSphere API
- KVM: Libvirt API
- oVirt/RHV: REST API v4

**Configuration Management:**
- Ansible: Inventory integration
- SaltStack: Minion auto-registration
- Puppet/Chef: Node classification

**Monitoring:**
- Prometheus: Metrics collection
- Grafana: Dashboards
- ELK Stack: Log aggregation

---

## 19. Risk Analysis & Mitigation

### 19.1 Market Risks

| Risk | Impact | Mitigation Strategy |
|------|--------|---------------------|
| Competition from established tools | Medium | Focus on lightweight + Pi support, better UX |
| PXE complexity intimidates users | High | Provide templates, defaults, guided setup |
| Mixed hardware compatibility | High | Use open bootloaders, extensive testing |
| License enforcement challenges | Medium | Simple "commercial use requires license" model |
| Community adoption slow | Medium | Active engagement, documentation, examples |
| oVirt integration complexity | Medium | Step-by-step guides, API examples |

### 19.2 Technical Risks

| Risk | Impact | Mitigation Strategy |
|------|--------|---------------------|
| Bootloader compatibility issues | High | Comprehensive testing matrix, fallback options |
| Network boot reliability | High | Retry logic, timeout handling, monitoring |
| Windows provisioning complexity | Medium | Modular design, clear documentation |
| Raspberry Pi firmware changes | Medium | Version-specific templates, update mechanism |
| oVirt API changes | Medium | Version detection, backward compatibility |
| Security vulnerabilities | Critical | Regular audits, dependency updates, CVE monitoring |

### 19.3 Business Risks

| Risk | Impact | Mitigation Strategy |
|------|--------|---------------------|
| Revenue model sustainability | High | Clear value proposition for commercial tier |
| Support burden | Medium | Tiered support, community-driven first line |
| Enterprise adoption barriers | High | Compliance certifications, case studies |
| Open source governance | Medium | Clear contribution guidelines, code of conduct |
| oVirt ecosystem changes | Medium | Active community participation |

---

## 20. Future Considerations

### 20.1 Advanced Features

- **AI-Powered Provisioning:** Predictive failure detection, automated remediation
- **Multi-Cloud Integration:** AWS, Azure, GCP provisioning workflows
- **Bare-Metal as a Service:** Self-service provisioning portal
- **Compliance Automation:** CIS benchmarks, security hardening
- **Disaster Recovery:** Automated backup and restore workflows
- **oVirt Advanced Integration:** Storage migration, network automation

### 20.2 Ecosystem Expansion

- **Marketplace:** Community templates and workflows
- **Plugin System:** Extensible architecture for custom integrations
- **Certification Program:** Partner training and certification
- **Hardware Partnerships:** Pre-configured appliances
- **Cloud Marketplace:** AWS/Azure/GCP marketplace listings
- **oVirt Certification:** Official oVirt integration certification

### 20.3 Technology Evolution

- **UEFI HTTP Boot:** Enhanced support for modern hardware
- **Secure Boot:** Full Secure Boot chain support
- **TPM Integration:** Trusted Platform Module utilization
- **Immutable Infrastructure:** Container-based provisioning
- **Edge Computing:** 5G and IoT device support
- **oVirt 5.0+ Features:** New API capabilities integration

---

## 21. Appendix

### 21.1 Glossary

- **PXE (Preboot eXecution Environment):** Network boot standard
- **iPXE:** Enhanced PXE with scripting capabilities
- **UEFI HTTP Boot:** Modern network boot over HTTP
- **WIM (Windows Imaging Format):** Windows installation image format
- **ODJ (Offline Domain Join):** Domain join without network connectivity
- **RBAC (Role-Based Access Control):** Permission management system
- **NFS (Network File System):** Distributed file system protocol
- **iSCSI (Internet Small Computer System Interface):** Block storage over IP
- **SLA (Service Level Agreement):** Commitment to service availability
- **oVirt/RHV:** Open-source virtualization management platform
- **Storage Domain:** oVirt's logical storage unit
- **HA (High Availability):** Automatic recovery from hardware failures

### 21.2 References

- PXE Specification: https://www.pix.net/software/pxeboot/archive/pxespec.pdf
- iPXE Documentation: https://ipxe.org/
- UEFI Specification: https://uefi.org/specifications
- Windows ADK: https://learn.microsoft.com/en-us/windows-hardware/get-started/adk-install
- Ubuntu Autoinstall: https://ubuntu.com/server/docs/install/autoinstall
- Raspberry Pi Network Boot: https://www.raspberrypi.com/documentation/computers/remote-access.html
- oVirt Documentation: https://www.ovirt.org/documentation/
- oVirt API Guide: https://www.ovirt.org/develop/release-management/features/sdk/python-sdk.html

### 21.3 Example Configurations

**Basic PXE Configuration (PXELINUX):**
```
DEFAULT menu.c32
PROMPT 0
TIMEOUT 50

LABEL ubuntu
  MENU LABEL Install Ubuntu 24.04
  KERNEL ubuntu/vmlinuz
  INITRD ubuntu/initrd
  APPEND ip=dhcp url=http://pureboot.local/ubuntu-2404.iso

LABEL local
  MENU LABEL Boot from local disk
  LOCALBOOT 0
```

**GRUB Configuration (UEFI):**
```
set default=0
set timeout=5

menuentry "Install Ubuntu 24.04" {
    linux /ubuntu/vmlinuz ip=dhcp url=http://pureboot.local/ubuntu-2404.iso
    initrd /ubuntu/initrd
}

menuentry "Boot from local disk" {
    chainloader (hd0)+1
}
```

**oVirt VM Creation (Python):**
```python
import ovirtsdk4 as sdk

# Connect to oVirt engine
connection = sdk.Connection(
    url='https://ovirt-engine.example.com/ovirt-engine/api',
    username='admin@internal',
    password='password',
    insecure=True
)

# Create VM from template
vms_service = connection.system_service().vms_service()
vm = vms_service.add(
    vm=sdk.Vm(
        name='pureboot-node-01',
        cluster=sdk.Cluster(name='Default'),
        template=sdk.Template(name='ubuntu-2404-template'),
        memory=4294967296,  # 4GB
        cpu=sdk.Cpu(topology=sdk.CpuTopology(cores=2, sockets=1))
    )
)

# Start the VM
vms_service.vm_service(vm.id).start()
connection.close()
```

**Windows AutoUnattend.xml Example:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
    <settings pass="windowsPE">
        <component name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <UserData>
                <ProductKey>
                    <Key>XXXXX-XXXXX-XXXXX-XXXXX-XXXXX</Key>
                </ProductKey>
                <AcceptEula>true</AcceptEula>
            </UserData>
            <ImageInstall>
                <OSImage>
                    <InstallFrom>
                        <MetaData wcm:action="add">
                            <Key>/IMAGE/NAME</Key>
                            <Value>Windows Server 2022 SERVERDATACENTER</Value>
                        </MetaData>
                    </InstallFrom>
                    <InstallTo>
                        <DiskID>0</DiskID>
                        <PartitionID>1</PartitionID>
                    </InstallTo>
                </OSImage>
            </ImageInstall>
        </component>
    </settings>
</unattend>
```

---

## 22. Conclusion

PureBoot represents a significant advancement in provisioning technology by addressing the critical gaps in existing solutions. With comprehensive oVirt/RHV integration, advanced security features, and extended lifecycle management, PureBoot provides:

1. **Unified Provisioning:** Single platform for physical and virtual resources
2. **Enterprise Virtualization:** Full oVirt/RHV integration with HA and live migration
3. **Advanced Security:** Four-Eye Principle, RBAC, and comprehensive audit trails
4. **Extended Lifecycle:** Deprovisioning and migration states for complete hardware management
5. **Performance Optimization:** Template-based rapid deployment (<5 minutes)
6. **Compliance Ready:** Secure data erasure, audit logging, and access control

The dual licensing model ensures accessibility for personal use while providing a sustainable business model for commercial deployments. With its focus on autonomy, reliability, security, and ease of use, PureBoot is positioned to become the standard for modern provisioning workflows across a wide range of use cases from homelab to enterprise data centers.

---

**Document Status:** Final
**Last Updated:** 2024
**Version:** 2.0
**Author:** Martins Veiss (mrveiss)

*This consolidated document includes all features from the original PRD, additional unique features, and comprehensive oVirt/RHV integration.*