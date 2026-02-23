FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# =============================================================================
# File system layout:
#
#   /opt/conda/                        -- Miniconda installation
#   /opt/conda/envs/biomni_e1/         -- conda environment (Python, R, bio tools)
#   /opt/biomni_tools/                  -- standalone CLI tools (PLINK2, IQ-TREE, etc.)
#   /opt/biomni_tools/bin/              -- symlinks to CLI tool binaries
#   /workspace/                         -- agent working directory (writable at runtime)
#
# Your package is NOT baked in — bind-mount it at runtime, e.g.:
#   apptainer exec --bind /path/to/your_pkg:/opt/your_pkg \
#                  --bind /path/to/workdir:/workspace \
#                  biomni.sif python /opt/your_pkg/run.py
# =============================================================================

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    git \
    build-essential \
    gcc \
    make \
    zlib1g-dev \
    unzip \
    jq \
    perl \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    libfontconfig1-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libfreetype6-dev \
    libpng-dev \
    libtiff5-dev \
    libjpeg-dev \
    libgit2-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Miniconda
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/conda \
    && rm /tmp/miniconda.sh \
    && /opt/conda/bin/conda init

# Accept conda ToS (required since conda 24.x)
RUN /opt/conda/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main || true \
    && /opt/conda/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r || true

# Add conda to PATH for build steps
ENV PATH="/opt/conda/bin:${PATH}"

# Set working directory for build
WORKDIR /tmp/biomni_build

# Copy environment and config files needed for build
COPY environment.yml bio_env.yml r_packages.yml ./
COPY install_r_packages.R install_cli_tools.sh cli_tools_config.json ./

# Step 1: Create base conda environment
RUN conda env create -n biomni_e1 -f environment.yml

# Use conda env for subsequent build steps
SHELL ["conda", "run", "-n", "biomni_e1", "/bin/bash", "-c"]

# Step 2: Install core bioinformatics tools (BLAST, samtools, scanpy, etc.)
RUN conda env update -n biomni_e1 -f bio_env.yml

# Step 3a: Install R dependency libraries and other packages
RUN conda install -y -n biomni_e1 -c conda-forge -c bioconda \
    libgit2 xz libnetcdf graphviz nlopt weasyprint \
    r-lme4 bioconductor-rgraphviz

# Step 3b: Install R packages via conda
RUN conda env update -n biomni_e1 -f r_packages.yml

# Step 4: Install additional R/Bioconductor packages (DESeq2, WGCNA, etc.)
RUN Rscript install_r_packages.R || true

# Step 5: Install standalone CLI tools (PLINK2, IQ-TREE, GCTA, BWA, etc.)
ENV BIOMNI_TOOLS_DIR="/opt/biomni_tools"
ENV BIOMNI_AUTO_INSTALL=1
ENV NON_INTERACTIVE=1
RUN chmod +x install_cli_tools.sh && bash install_cli_tools.sh --auto || true

# Clean up conda caches and build dir to reduce image size
RUN conda clean -afy
SHELL ["/bin/bash", "-c"]
RUN rm -rf /tmp/biomni_build

# Create workspace directory for the agent
RUN mkdir -p /workspace

# ---------------------------------------------------------------------------
# Activate conda environment via ENV (works in both Docker and Apptainer)
# This avoids needing `conda activate` or an ENTRYPOINT wrapper.
# ---------------------------------------------------------------------------
ENV CONDA_DEFAULT_ENV="biomni_e1"
ENV CONDA_PREFIX="/opt/conda/envs/biomni_e1"
ENV PATH="/opt/biomni_tools/bin:/opt/conda/envs/biomni_e1/bin:/opt/conda/bin:${PATH}"

WORKDIR /workspace
