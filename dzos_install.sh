#!/bin/bash

echo "DZOS - INSTALLATION SCRIPT"

USER_DIRECTORY="$HOME"

cp -r -v -f klipper "$USER_DIRECTORY"
cp -r -v -f printer_data "$USER_DIRECTORY"

echo "DZOS - INSTALLED"
echo
echo "Please add [include dzos.cfg] and read instructions!"
echo "Please reboot your entire printer to apply changes."

