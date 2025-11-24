#!/bin/bash

echo "DZOS - INSTALLATION SCRIPT"

USER_DIRECTORY="$HOME"

cp -r -v klipper "$USER_DIRECTORY"
cp -r -v printer_data "$USER_DIRECTORY"

echo "DZOS - INSTALLED"
echo
echo "Please add [include dzos.cfg] and read instructions!"

