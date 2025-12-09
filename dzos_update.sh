#!/bin/bash

echo "DZOS - UPDATE SCRIPT"
USER_DIRECTORY="$HOME"

git pull origin main

cp -r -v -f klipper "$USER_DIRECTORY"
cp -r -v -f printer_data "$USER_DIRECTORY"

echo "DZOS - UPDATED"
echo "Please reboot your entire printer to apply changes."

