#!/bin/bash

echo "DZOS - UPDATE SCRIPT"
USER_DIRECTORY="$HOME"

git pull origin main

cp -r -v klipper "$USER_DIRECTORY"
cp -r -v printer_data "$USER_DIRECTORY"

echo "DZOS - UPDATED"
echo "Please reboot to apply changes."

