#!/bin/bash
#
# iMac Fan Control Suite - Installation Script
#
# This script installs the fan control utilities on:
# - openSUSE Tumbleweed
# - RaspberryOS (Debian-based)
# - Other Debian/Ubuntu derivatives
#
# Target hardware: iMac 27" Late 2009 (iMac11,1)
#
# Usage: sudo ./install.sh [options]
#
# Options:
#   --headless     Install headless service only (no GUI)
#   --gui          Install GUI only (default: both)
#   --uninstall    Remove installed files and service
#   --help         Show this help
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Defaults
INSTALL_DIR="/opt/imac-fan-control"
REPO_URL="https://github.com/BirgerKo/imac-fan-control.git"
INSTALL_GUI=true
INSTALL_HEADLESS=true
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

is_root() {
    [ "$(id -u)" -eq 0 ]
}

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS="$ID"
        OS_VERSION="$VERSION_ID"
    elif type lsb_release >/dev/null 2>&1; then
        OS=$(lsb_release -si | tr '[:upper:]' '[:lower:]')
        OS_VERSION=$(lsb_release -sr)
    else
        OS=$(uname -s)
        OS_VERSION=$(uname -r)
    fi
    echo "$OS"
}

detect_platform() {
    # Check for iMac hardware
    if grep -qi "imac" /sys/firmware/devicetree/base/model 2>/dev/null || \
       dmidecode -s system-product-name 2>/dev/null | grep -qi "imac"; then
        echo "imac"
    else
        echo "unknown"
    fi
}

# ---------------------------------------------------------------------------
# Kernel module functions
# ---------------------------------------------------------------------------

check_applesmc_loaded() {
    lsmod | grep -q applesmc
}

check_applesmc_sysfs() {
    [ -d "/sys/devices/platform/applesmc.768" ]
}

load_applesmc() {
    local os_type=$(detect_os)
    
    log_header "Installing applesmc kernel module"
    
    if check_applesmc_loaded; then
        log_info "applesmc module is already loaded"
        return 0
    fi
    
    # Try to load directly
    if modprobe applesmc 2>/dev/null; then
        log_info "applesmc module loaded successfully"
        return 0
    fi
    
    # Module not available, need to install/build
    log_warn "applesmc module not found, attempting to install..."
    
    case "$os_type" in
        opensuse*|suse*)
            log_info "Detected openSUSE"
            if zypper search applesmc-dkms >/dev/null 2>&1; then
                log_info "Installing applesmc-dkms from repository"
                sudo zypper install -y applesmc-dkms
            else
                log_warn "applesmc-dkms not in repositories, building from source"
                install_applesmc_from_source
            fi
            ;;
        debian|ubuntu|raspbian)
            log_info "Detected Debian-based system (RaspberryOS)"
            if apt-cache search applesmc-dkms >/dev/null 2>&1; then
                log_info "Installing applesmc-dkms from repository"
                sudo apt-get update
                sudo apt-get install -y applesmc-dkms
            else
                log_warn "applesmc-dkms not in repositories, building from source"
                install_applesmc_from_source
            fi
            ;;
        *)
            log_warn "Unknown OS type: $os_type, building applesmc from source"
            install_applesmc_from_source
            ;;
    esac
    
    # Try to load again
    if ! modprobe applesmc 2>/dev/null; then
        log_error "Failed to load applesmc module"
        return 1
    fi
    
    log_info "applesmc module loaded successfully"
    return 0
}

install_applesmc_from_source() {
    log_info "Building applesmc from source..."
    
    # Install build dependencies
    local os_type=$(detect_os)
    case "$os_type" in
        opensuse*|suse*)
            sudo zypper install -y git gcc make kernel-devel
            ;;
        debian|ubuntu|raspbian)
            sudo apt-get install -y git build-essential
            ;;
        *)
            sudo apt-get install -y git build-essential 2>/dev/null || \
            sudo zypper install -y git gcc make 2>/dev/null || \
            log_error "Cannot install build dependencies"
            ;;
    esac
    
    # Clone and build
    local tmp_dir=$(mktemp -d)
    trap "rm -rf $tmp_dir" EXIT
    
    cd "$tmp_dir"
    if ! git clone https://github.com/guillaumevincent/applesmc.git 2>/dev/null; then
        log_error "Failed to clone applesmc repository"
        return 1
    fi
    
    cd applesmc
    make 2>/dev/null
    sudo make install 2>/dev/null
    
    if ! modprobe applesmc 2>/dev/null; then
        log_error "Failed to build/install applesmc module"
        return 1
    fi
    
    log_info "applesmc module built and installed from source"
    return 0
}

# ---------------------------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------------------------

install_python_deps() {
    local os_type=$(detect_os)
    
    log_header "Installing Python dependencies"
    
    # Check for Python 3
    if ! command -v python3 >/dev/null 2>&1; then
        log_error "Python 3 is not installed"
        return 1
    fi
    
    # Install Tkinter for GUI
    if [ "$INSTALL_GUI" = true ]; then
        case "$os_type" in
            opensuse*|suse*)
                sudo zypper install -y python3-tk
                ;;
            debian|ubuntu|raspbian)
                sudo apt-get install -y python3-tk
                ;;
            *)
                sudo apt-get install -y python3-tk 2>/dev/null || \
                sudo zypper install -y python3-tk 2>/dev/null || \
                log_warn "Could not install python3-tk, GUI will not work"
                ;;
        esac
    fi
    
    log_info "Python dependencies installed"
    return 0
}

# ---------------------------------------------------------------------------
# Installation functions
# ---------------------------------------------------------------------------

do_install() {
    local platform=$(detect_platform)
    
    if [ "$platform" != "imac" ]; then
        log_error "This script is designed for iMac hardware only"
        log_error "Detected platform: $platform"
        return 1
    fi
    
    log_header "iMac Fan Control Suite Installation"
    
    # Step 1: Load kernel modules
    if ! load_applesmc; then
        log_error "Failed to set up applesmc kernel module"
        return 1
    fi
    
    # Verify sysfs is available
    if ! check_applesmc_sysfs; then
        log_error "applesmc sysfs not found at /sys/devices/platform/applesmc.768/"
        log_error "Make sure the applesmc kernel module is loaded"
        return 1
    fi
    
    log_info "applesmc sysfs found at /sys/devices/platform/applesmc.768/"
    
    # Step 2: Install Python dependencies
    if ! install_python_deps; then
        log_warn "Python dependencies may not be fully installed"
    fi
    
    # Step 3: Create installation directory
    log_header "Setting up installation directory"
    log_info "Installing to: $INSTALL_DIR"
    
    sudo mkdir -p "$INSTALL_DIR"
    sudo chown $(id -u):$(id -g) "$INSTALL_DIR"
    
    # Copy files
    log_info "Copying project files..."
    sudo cp -r "$SCRIPT_DIR"/imac_fan_control.py "$INSTALL_DIR/"
    sudo cp -r "$SCRIPT_DIR"/imac_fan_control_headless.py "$INSTALL_DIR/"
    sudo cp -r "$SCRIPT_DIR"/*.service "$INSTALL_DIR/"
    sudo cp -r "$SCRIPT_DIR"/*.desktop "$INSTALL_DIR/"
    sudo cp -r "$SCRIPT_DIR"/README.md "$INSTALL_DIR/"
    sudo cp -r "$SCRIPT_DIR"/LICENSE "$INSTALL_DIR/"
    
    # Set permissions
    sudo chmod 755 "$INSTALL_DIR"/imac_fan_control.py
    sudo chmod 755 "$INSTALL_DIR"/imac_fan_control_headless.py
    sudo chmod 644 "$INSTALL_DIR"/*.service
    sudo chmod 644 "$INSTALL_DIR"/*.desktop
    
    # Step 4: Update paths in service and desktop files
    log_header "Updating paths in configuration files"
    
    # Update service files
    for service_file in "$INSTALL_DIR"/*.service; do
        [ -f "$service_file" ] || continue
        sudo sed -i \
            -e "s|/home/birger/Downloads/|$INSTALL_DIR/|g" \
            -e "s|/home/birger/Code/iMac fan control/|$INSTALL_DIR/|g" \
            "$service_file"
        # Add WorkingDirectory if not present
        if ! grep -q "WorkingDirectory" "$service_file"; then
            sudo sed -i "/^\[Service\]/a WorkingDirectory=$INSTALL_DIR" "$service_file"
        fi
    done
    
    # Update desktop file
    if [ -f "$INSTALL_DIR"/imac-fan-control.desktop ]; then
        sudo sed -i \
            -e "s|/home/birger/Downloads/|$INSTALL_DIR/|g" \
            -e "s|/home/birger/Code/iMac fan control/|$INSTALL_DIR/|g" \
            "$INSTALL_DIR"/imac-fan-control.desktop
    fi
    
    # Step 5: Install headless service
    if [ "$INSTALL_HEADLESS" = true ]; then
        log_header "Installing headless service"
        
        sudo cp "$INSTALL_DIR"/imac-fan-control-headless.service /etc/systemd/system/
        sudo systemctl daemon-reload
        sudo systemctl enable imac-fan-control-headless.service
        
        log_info "Headless service installed and enabled"
        log_info "To start: sudo systemctl start imac-fan-control-headless.service"
    fi
    
    # Step 6: Set up GUI autostart
    if [ "$INSTALL_GUI" = true ]; then
        log_header "Setting up GUI autostart"
        
        local autostart_dir="$HOME/.config/autostart"
        sudo mkdir -p "$autostart_dir"
        sudo cp "$INSTALL_DIR"/imac-fan-control.desktop "$autostart_dir/"
        sudo chmod +x "$autostart_dir"/imac-fan-control.desktop
        
        log_info "GUI autostart configured"
        log_info "Log out and back in to activate"
    fi
    
    log_header "Installation Complete!"
    log_info "Project installed to: $INSTALL_DIR"
    log_info ""
    log_info "To run GUI manually:"
    log_info "  sudo python3 $INSTALL_DIR/imac_fan_control.py"
    log_info ""
    log_info "To start headless service:"
    log_info "  sudo systemctl start imac-fan-control-headless.service"
    log_info ""
    log_info "To check status:"
    log_info "  sudo systemctl status imac-fan-control-headless.service"
    log_info "  sudo journalctl -u imac-fan-control-headless.service -f"
    
    return 0
}

do_uninstall() {
    log_header "Uninstalling iMac Fan Control Suite"
    
    # Stop and disable service
    if systemctl list-unit-files | grep -q imac-fan-control-headless; then
        sudo systemctl stop imac-fan-control-headless.service 2>/dev/null || true
        sudo systemctl disable imac-fan-control-headless.service 2>/dev/null || true
        sudo rm -f /etc/systemd/system/imac-fan-control-headless.service
        sudo systemctl daemon-reload
        log_info "Headless service stopped and disabled"
    fi
    
    # Remove autostart
    if [ -f "$HOME/.config/autostart/imac-fan-control.desktop" ]; then
        rm -f "$HOME/.config/autostart/imac-fan-control.desktop"
        log_info "GUI autostart removed"
    fi
    
    # Remove installation directory
    if [ -d "$INSTALL_DIR" ]; then
        sudo rm -rf "$INSTALL_DIR"
        log_info "Installation directory removed: $INSTALL_DIR"
    fi
    
    log_info "Uninstallation complete"
    return 0
}

show_help() {
    cat <<EOF
Usage: sudo ./install.sh [options]

Options:
  --headless        Install headless service only (no GUI)
  --gui             Install GUI only
  --uninstall       Remove installed files and service
  --help, -h        Show this help message
  --install-dir DIR Specify installation directory (default: /opt/imac-fan-control)

Examples:
  sudo ./install.sh                    # Install both GUI and headless
  sudo ./install.sh --headless         # Install headless only
  sudo ./install.sh --gui             # Install GUI only
  sudo ./install.sh --uninstall        # Remove everything
  sudo ./install.sh --install-dir /home/pi/fan-control

Note: This script requires root privileges for installation.
EOF
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Parse arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --headless)
            INSTALL_GUI=false
            ;;
        --gui)
            INSTALL_HEADLESS=false
            ;;
        --uninstall)
            do_uninstall
            exit 0
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        --install-dir)
            INSTALL_DIR="$2"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
    shift
done

# Check for root
if ! is_root; then
    log_error "This script must be run as root (use sudo)"
    exit 1
fi

# Detect platform
platform=$(detect_platform)
if [ "$platform" != "imac" ]; then
    log_warn "Warning: This script is designed for iMac hardware"
    log_warn "Detected platform: $platform"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Run installation
do_install
