#!/bin/bash

# BioAgentOS - Biomni Environment Setup Script
# This script sets up a comprehensive bioinformatics environment with various tools and packages

# Set up colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default tools directory is the current directory
DEFAULT_TOOLS_DIR="$(pwd)/biomni_tools"
TOOLS_DIR=""

echo -e "${YELLOW}=== Biomni Environment Setup ===${NC}"
echo -e "${BLUE}This script will set up a comprehensive bioinformatics environment with various tools and packages.${NC}"

# -----------------------------
# Options
# -----------------------------
WITH_CLI=""
NON_INTERACTIVE=""

show_help() {
    cat <<'EOF'
Usage: bash setup.sh [OPTIONS]

Options:
  --with-cli            Also install external CLI tools (downloads/compiles).
  --tools-dir DIR       Install CLI tools into DIR (default: ./biomni_tools).
  --non-interactive     Do not prompt; continue on errors where applicable.
  -h, --help            Show this help.

Notes:
  - This script uses conda/micromamba for conda deps.
  - Pip deps in env YAMLs are installed via `uv pip` (inside the conda env),
    to avoid conda automatically invoking pip (which may be configured to use
    a site wheelhouse on some HPC systems).
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-cli)
            WITH_CLI=1
            shift
            ;;
        --tools-dir)
            TOOLS_DIR="${2:-}"
            shift 2
            ;;
        --non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help
            exit 2
            ;;
    esac
done

# -----------------------------
# Helpers: use uv for pip installs
# -----------------------------
# Conda will run `python -m pip install ...` automatically if an env yml contains a `pip:` block.
# We generate a temporary conda-only yml (pip block removed) and install pip deps via uv after
# the environment is activated.

make_conda_only_env_yml() {
    local env_file="$1"
    local out_file="$2"

    awk '
        function indent(s) { match(s, /^[ ]*/); return RLENGTH }
        {
            if (!skipping && $0 ~ /^[[:space:]]*-[[:space:]]pip:[[:space:]]*$/) {
                skipping = 1
                pip_indent = indent($0)
                next
            }
            if (skipping) {
                if ($0 !~ /^[[:space:]]*$/ && indent($0) <= pip_indent) {
                    skipping = 0
                } else {
                    next
                }
            }
            print $0
        }
    ' "$env_file" > "$out_file"
}

extract_pip_requirements() {
    local env_file="$1"
    local out_reqs="$2"

    awk '
        function indent(s) { match(s, /^[ ]*/); return RLENGTH }
        BEGIN { in_pip = 0; pip_indent = -1 }
        {
            if (!in_pip && $0 ~ /^[[:space:]]*-[[:space:]]pip:[[:space:]]*$/) {
                in_pip = 1
                pip_indent = indent($0)
                next
            }
            if (in_pip) {
                if ($0 !~ /^[[:space:]]*$/ && indent($0) <= pip_indent) {
                    exit
                }
                if ($0 ~ /^[[:space:]]*-[[:space:]]/) {
                    line = $0
                    sub(/^[[:space:]]*-[[:space:]]/, "", line)
                    if (line !~ /^#/) print line
                }
            }
        }
    ' "$env_file" > "$out_reqs"
}

ensure_uv() {
    echo -e "Installing uv via conda-forge...${NC}"
    conda install -y -c conda-forge uv
    return $?
}

install_pip_with_uv_from_env_yml() {
    local env_file="$1"
    local description="$2"
    local optional=${3:-false}

    local reqs_file
    reqs_file="$(mktemp -t biomni_uv_reqs.XXXXXX.txt)"

    extract_pip_requirements "$env_file" "$reqs_file"
    if [ ! -s "$reqs_file" ]; then
        rm -f "$reqs_file"
        return 0
    fi

    echo -e "${YELLOW}Installing pip packages for $description via uv...${NC}"
    ensure_uv
    handle_error $? "Failed to install uv." $optional

    uv pip install -U -r "$reqs_file"
    handle_error $? "Failed to install pip packages for $description via uv." $optional

    rm -f "$reqs_file"
    return 0
}

# Check if conda is installed
if ! command -v conda &> /dev/null && ! command -v micromamba &> /dev/null; then
    echo -e "${RED}Error: Conda is not installed or not in PATH.${NC}"
    echo "Please install Miniconda or Anaconda first."
    echo "Visit: https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

# redirect to micromamba if needed
if ! command -v conda &> /dev/null && command -v micromamba &> /dev/null; then
    conda() {
        micromamba "$@"
    }
    export -f conda
fi

# Function to handle errors
handle_error() {
    local exit_code=$1
    local error_message=$2
    local optional=${3:-false}

    if [ $exit_code -ne 0 ]; then
        echo -e "${RED}Error: $error_message${NC}"
        if [ "$optional" = true ]; then
            echo -e "${YELLOW}Continuing with setup as this component is optional.${NC}"
            return 0
        else
            if [ -z "$NON_INTERACTIVE" ]; then
                read -p "Continue with setup? (y/n) " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    echo -e "${RED}Setup aborted.${NC}"
                    exit 1
                fi
            else
                echo -e "${YELLOW}Non-interactive mode: continuing despite error.${NC}"
            fi
        fi
    fi
    return $exit_code
}

# Function to install a specific environment file
install_env_file() {
    local env_file=$1
    local description=$2
    local optional=${3:-false}

    echo -e "\n${BLUE}=== Installing $description ===${NC}"

    if [ "$optional" = true ]; then
        if [ -z "$NON_INTERACTIVE" ]; then
            read -p "Do you want to install $description? (y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo -e "${YELLOW}Skipping $description installation.${NC}"
                return 0
            fi
        else
            echo -e "${YELLOW}Non-interactive mode: automatically installing $description.${NC}"
        fi
    fi

    echo -e "${YELLOW}Installing $description from $env_file...${NC}"

    # Avoid conda invoking pip; install pip deps via uv after env activation.
    local tmp_conda_env
    tmp_conda_env="$(mktemp -t biomni_conda_only.XXXXXX.yml)"
    make_conda_only_env_yml "$env_file" "$tmp_conda_env"

    conda env update -f "$tmp_conda_env"
    handle_error $? "Failed to install $description." $optional
    rm -f "$tmp_conda_env"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Successfully installed $description!${NC}"
    fi

    install_pip_with_uv_from_env_yml "$env_file" "$description" "$optional"
}

# Function to install CLI tools
install_cli_tools() {
    echo -e "\n${BLUE}=== Installing Command-Line Bioinformatics Tools ===${NC}"

    # Ask user for the directory to install CLI tools
    if [ -z "$NON_INTERACTIVE" ]; then
        echo -e "${YELLOW}Where would you like to install the command-line tools?${NC}"
        echo -e "${BLUE}Default: $DEFAULT_TOOLS_DIR${NC}"
        if [ -n "$TOOLS_DIR" ]; then
            user_tools_dir="$TOOLS_DIR"
            echo -e "${BLUE}Using from --tools-dir: $TOOLS_DIR${NC}"
        else
            read -p "Enter directory path (or press Enter for default): " user_tools_dir
        fi
    else
        user_tools_dir="${TOOLS_DIR:-}"
        if [ -z "$user_tools_dir" ]; then
            echo -e "${YELLOW}Non-interactive mode: using default directory $DEFAULT_TOOLS_DIR for CLI tools.${NC}"
        else
            echo -e "${YELLOW}Non-interactive mode: using directory $user_tools_dir for CLI tools.${NC}"
        fi
    fi

    if [ -z "$user_tools_dir" ]; then
        TOOLS_DIR="$DEFAULT_TOOLS_DIR"
    else
        TOOLS_DIR="$user_tools_dir"
    fi

    # Export the tools directory for the CLI tools installer
    export BIOMNI_TOOLS_DIR="$TOOLS_DIR"

    echo -e "${YELLOW}Installing command-line tools (PLINK, IQ-TREE, GCTA, etc.) to $TOOLS_DIR...${NC}"

    # Set environment variable to skip prompts in the CLI tools installer
    export BIOMNI_AUTO_INSTALL=1

    # Run the CLI tools installer
    bash install_cli_tools.sh
    handle_error $? "Failed to install CLI tools." true

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Successfully installed command-line tools!${NC}"

        # Create a setup_path.sh file in the current directory
        echo "#!/bin/bash" > setup_path.sh
        echo "# Added by biomni setup" >> setup_path.sh
        echo "# Remove any old paths first to avoid duplicates" >> setup_path.sh
        echo "PATH=\$(echo \$PATH | tr ':' '\n' | grep -v \"biomni_tools/bin\" | tr '\n' ':' | sed 's/:$//')" >> setup_path.sh
        echo "export PATH=\"$TOOLS_DIR/bin:\$PATH\"" >> setup_path.sh
        chmod +x setup_path.sh

        echo -e "${GREEN}Created setup_path.sh in the current directory.${NC}"
        echo -e "${YELLOW}You can add the tools to your PATH by running:${NC}"
        echo -e "${GREEN}source $(pwd)/setup_path.sh${NC}"

        # Also add to the current session
        # Remove any old paths first to avoid duplicates
        PATH=$(echo $PATH | tr ':' '\n' | grep -v "biomni_tools/bin" | tr '\n' ':' | sed 's/:$//')
        export PATH="$TOOLS_DIR/bin:$PATH"
    fi

    # Unset the environment variables
    unset BIOMNI_AUTO_INSTALL
    unset BIOMNI_TOOLS_DIR
}

# Main installation process
main() {
    # Step 1: Create base conda environment
    echo -e "\n${YELLOW}Step 1: Creating base environment from environment.yml...${NC}"
    # Avoid conda invoking pip from `pip:`; we will install those later via uv.
    tmp_base_env="$(mktemp -t biomni_base_conda_only.XXXXXX.yml)"
    make_conda_only_env_yml "environment.yml" "$tmp_base_env"
    conda env create -n biomni_e1 -f "$tmp_base_env"
    rm -f "$tmp_base_env"
    handle_error $? "Failed to create base conda environment."

    # Step 2: Activate the environment
    echo -e "\n${YELLOW}Step 2: Activating conda environment...${NC}"
    if command -v micromamba &> /dev/null; then
        eval "$(micromamba shell hook --shell bash)"
        micromamba activate biomni_e1
    else
        eval "$(conda shell.bash hook)"
        conda activate biomni_e1
    fi
    handle_error $? "Failed to activate biomni_e1 environment."

    # Step 2b: Install pip dependencies from environment.yml via uv
    echo -e "\n${YELLOW}Step 2b: Installing pip dependencies from environment.yml via uv...${NC}"
    install_pip_with_uv_from_env_yml "environment.yml" "base Python packages"

    # Step 3: Install core bioinformatics tools (including QIIME2)
    echo -e "\n${YELLOW}Step 3: Installing core bioinformatics tools (including QIIME2)...${NC}"
    install_env_file "bio_env.yml" "core bioinformatics tools"

    # Step 4: Install R packages
    echo -e "\n${YELLOW}Step 4: Installing R packages...${NC}"
    install_env_file "r_packages.yml" "core R packages"

    # Step 5: Install additional R packages through R's package manager
    echo -e "\n${YELLOW}Step 5: Installing additional R packages through R's package manager...${NC}"
    Rscript install_r_packages.R
    handle_error $? "Failed to install additional R packages." true

    # Step 6: Install CLI tools (optional)
    if [ -n "$WITH_CLI" ]; then
        echo -e "\n${YELLOW}Step 6: Installing command-line bioinformatics tools...${NC}"
        install_cli_tools
    else
        echo -e "\n${YELLOW}Step 6: Skipping CLI tools (run with --with-cli to install).${NC}"
    fi

    # Setup completed
    echo -e "\n${GREEN}=== Biomni Environment Setup Completed! ===${NC}"
    echo -e "You can now run the example analysis with: ${YELLOW}python bio_analysis_example.py${NC}"
    echo -e "To activate this environment in the future, run: ${YELLOW}conda activate biomni_e1${NC}"
    echo -e "To use BioAgentOS, navigate to the BioAgentOS directory and follow the instructions in the README."

    # Display CLI tools setup instructions
    if [ -n "$TOOLS_DIR" ] && [ -n "$WITH_CLI" ]; then
        echo -e "\n${BLUE}=== Command-Line Tools Setup ===${NC}"
        echo -e "The command-line tools are installed in: ${YELLOW}$TOOLS_DIR${NC}"
        echo -e "To add these tools to your PATH, run: ${YELLOW}source $(pwd)/setup_path.sh${NC}"
        echo -e "You can also add this line to your shell profile for permanent access:"
        echo -e "${GREEN}export PATH=\"$TOOLS_DIR/bin:\$PATH\"${NC}"

        # Test if tools are accessible
        echo -e "\n${BLUE}=== Testing CLI Tools ===${NC}"
        if command -v plink2 &> /dev/null; then
            echo -e "${GREEN}PLINK2 is accessible in the current PATH${NC}"
            echo -e "PLINK2 location: $(which plink2)"
        else
            echo -e "${RED}PLINK2 is not accessible in the current PATH${NC}"
            echo -e "Please run: ${YELLOW}source $(pwd)/setup_path.sh${NC} to update your PATH"
        fi

        if command -v gcta64 &> /dev/null; then
            echo -e "${GREEN}GCTA is accessible in the current PATH${NC}"
            echo -e "GCTA location: $(which gcta64)"
        else
            echo -e "${RED}GCTA is not accessible in the current PATH${NC}"
            echo -e "Please run: ${YELLOW}source $(pwd)/setup_path.sh${NC} to update your PATH"
        fi

        if command -v iqtree2 &> /dev/null; then
            echo -e "${GREEN}IQ-TREE is accessible in the current PATH${NC}"
            echo -e "IQ-TREE location: $(which iqtree2)"
        else
            echo -e "${RED}IQ-TREE is not accessible in the current PATH${NC}"
            echo -e "Please run: ${YELLOW}source $(pwd)/setup_path.sh${NC} to update your PATH"
        fi
    fi

    if [ -n "$WITH_CLI" ]; then
        PATH=$(echo $PATH | tr ':' '\n' | grep -v "biomni_tools/bin" | tr '\n' ':' | sed 's/:$//')
        export PATH="$(pwd)/biomni_tools/bin:$PATH"
    fi
}

# Run the main installation process
main
