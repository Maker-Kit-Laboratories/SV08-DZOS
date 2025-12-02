#!/bin/bash

echo "DZOS - REMOVAL SCRIPT"

USER_DIRECTORY="$HOME"
KLIPPER_DIRECTORY="$USER_DIRECTORY/klipper"
PRINTER_DATA_DIRECTORY="$USER_DIRECTORY/printer_data"

find "$KLIPPER_DIRECTORY" -type f -name "*dzos*" -delete
find "$PRINTER_DATA_DIRECTORY" -type f -name "*dzos*" -delete

echo

echo "DZOS - REMOVED"
echo
echo "Please remove [include dzos.cfg] and macros from your configuration files and slicer!"
echo "Reboot after removal to apply changes."