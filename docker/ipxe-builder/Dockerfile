# iPXE Builder Docker Image
# Builds custom PureBoot iPXE binaries with embedded scripts
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    liblzma-dev \
    isolinux \
    mtools \
    xz-utils \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Clone iPXE source
RUN git clone --depth 1 https://github.com/ipxe/ipxe.git /ipxe

WORKDIR /ipxe/src

# Enable features for PureBoot:
# - HTTPS for secure boot scripts
# - PNG for logo display
# - Console commands for resolution
# - Color commands for branded display
# - Framebuffer for graphics
RUN sed -i 's/#undef\tDOWNLOAD_PROTO_HTTPS/#define DOWNLOAD_PROTO_HTTPS/' config/general.h && \
    sed -i 's/\/\/#define IMAGE_PNG/#define IMAGE_PNG/' config/general.h && \
    sed -i 's/\/\/#define CONSOLE_CMD/#define CONSOLE_CMD/' config/general.h && \
    sed -i 's/\/\/#define COLOUR_CMD/#define COLOUR_CMD/' config/general.h && \
    sed -i 's/\/\/#define CPAIR_CMD/#define CPAIR_CMD/' config/general.h && \
    sed -i 's/\/\/#define CONSOLE_FRAMEBUFFER/#define CONSOLE_FRAMEBUFFER/' config/console.h || true

# Use shell as entrypoint so we can run complex commands
ENTRYPOINT ["/bin/sh", "-c"]
CMD ["make bin/undionly.kpxe"]
