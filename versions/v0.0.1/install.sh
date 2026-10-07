#!/bin/bash

if pipx list | grep -q "package versionsnap"; then
    read -r -p "A previous installation of versionsnap exists and will be removed. Do you wish to continue? [y/n]: " answer

    if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
        echo "Installation cancelled."
        exit 0
    fi

    pipx uninstall versionsnap 2>/dev/null 1>/dev/null
fi

pipx install .
