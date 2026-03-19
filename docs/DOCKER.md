# Docker Development Guide

## Overview

The E.C.H.O. simulation framework provides a development container with Python and a C toolchain pre-installed. This supports:

- **Python development**: all three simulation layers (Device, Network, Platform)
- **C HAL development**: gcc and cmake for HAL header compilation and C mock implementations (Phase 2-3)
- **Testing**: pytest with coverage support

## Quick Start

```bash
# Build the development image
docker build -f Dockerfile.dev -t echo-dev .

# Run tests (default command)
docker run --rm echo-dev

# Interactive development shell
docker run --rm -it echo-dev bash

# Run tests with coverage
docker run --rm echo-dev pytest tests/ --cov=simulation
```

## Available Dockerfiles

| Dockerfile | Platform | Purpose |
|------------|----------|---------|
| `Dockerfile.dev` | x86/x64 | Development and testing — Python + C toolchain |

> **Note**: Unlike service components (M.I.R.A.G.E., D.A.W.N., S.T.A.T.), the simulation framework does not have Jetson or Raspberry Pi Dockerfiles. It runs on the developer's machine, not on target hardware.

## Development Workflow

### Mount Source for Live Editing

```bash
docker run --rm -it -v "$(pwd)":/opt/echo echo-dev bash
```

Changes to source files on the host are immediately reflected inside the container.

### Layer-Specific Installation

If you only need a subset of layers:

```bash
# Inside the container
pip install -e "."           # Device layer only (no external deps)
pip install -e ".[layer1]"   # + Network layer
pip install -e ".[all]"      # All layers
```

### C HAL Development

The container includes `gcc`, `g++`, and `cmake` for C HAL header compilation:

```bash
# Inside the container
cd /opt/echo
mkdir -p build && cd build
cmake ..
make -j$(nproc)
```

## Non-Containerized Alternative

For development without Docker, use a Python virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows
pip install -e ".[all,dev]"
pytest tests/
```

See `docs/guide.md` for full installation instructions.
