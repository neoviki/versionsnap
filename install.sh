#!/bin/bash

UTILITY_NAME="src/versionsnap"
INSTALL_DIR="/usr/bin"

get_installation_directory() {
    echo "[ status   ] Identifying Host System"
    local system_name
    system_name=$(uname -s)

    if [[ "$system_name" == "Linux" ]]; then
        echo "[ status   ] Linux System detected"
        INSTALL_DIR="/usr/local/bin"
    elif [[ "$system_name" == "Darwin" ]]; then
        echo "[ status   ] Mac System detected"
        INSTALL_DIR="/opt/local/bin"
    else
        echo "[ warning  ] Unknown system: $system_name. Installation dir set to [ /usr/bin ]"
    fi
}

install_util() {
    echo "[ status   ] Installing $UTILITY_NAME to $INSTALL_DIR"

    chmod +x "./$UTILITY_NAME"

    if command -v sudo &> /dev/null; then
        sudo cp "./$UTILITY_NAME" "$INSTALL_DIR/"
    else
        cp "./$UTILITY_NAME" "$INSTALL_DIR/"
    fi
}

check_installation_status() {
    if [ "$1" -eq 0 ]; then
        echo "[ success  ] $UTILITY_NAME installation is successful"
    else
        echo "[ failure  ] $UTILITY_NAME installation failed. You might need sudo or root access."
    fi
}

# Main execution
get_installation_directory
install_util
check_installation_status $?

