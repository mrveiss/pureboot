FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    liblzma-dev \
    isolinux \
    mtools \
    && rm -rf /var/lib/apt/lists/*

# Clone iPXE source
RUN git clone https://github.com/ipxe/ipxe.git /ipxe

WORKDIR /ipxe/src

# Enable PNG support and HTTPS
RUN sed -i 's/#undef\tDOWNLOAD_PROTO_HTTPS/#define DOWNLOAD_PROTO_HTTPS/' config/general.h && \
    sed -i 's/\/\/#define IMAGE_PNG/#define IMAGE_PNG/' config/general.h

# Default command
CMD ["make", "bin/undionly.kpxe"]
