# Guides

This directory contains user and developer guides for PureBoot.

## Contents

### User Guides

- [getting-started.md](getting-started.md) - Quick start guide
- [installation.md](installation.md) - Installation instructions
- [configuration.md](configuration.md) - Configuration reference

### Developer Guides

- [development.md](development.md) - Development setup and workflow
- [contributing.md](contributing.md) - Contribution guidelines
- [testing.md](testing.md) - Testing strategies and requirements

## Quick Start

### Prerequisites

- Python 3.8+
- Docker and Docker Compose
- PostgreSQL (production) or SQLite (development)

### Installation

```bash
# Clone repository
git clone https://github.com/mrveiss/pureboot.git
cd pureboot

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Start database
docker-compose up -d db

# Run migrations
python -m scripts.migrate

# Start development server
uvicorn main:app --reload
```

### First Steps

1. Access the web UI at `http://localhost:8000`
2. Create your first workflow
3. PXE boot a test node
4. Assign the workflow to the discovered node
5. Watch the provisioning process

See individual guide files for detailed instructions.
