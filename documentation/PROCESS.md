
![LOGO](./images/dzos_logo.png)

# DZOS: Dynamic Z Offset and Soaking

## PRE-REQUISITES:
1. SV08 3D Printer with an inductive sensor.
2. File transfer software (examples below):
    - [FileZilla](https://filezilla-project.org/)
    - [winSCP](https://winscp.net/)
3. Slicer Config: 
    - Configure your slicer to pass `NOZZLETEMP=<###>` `BEDTEMP=<##>` to `START_PRINT`.
    - Configure your slicer to pass `DZOS_END_PRINT` after your existing `END_PRINT`.
4. Ensure your hotend/nozzle is tight! Loose components move more during heat change.

## INSTALL:
1. Access the SV08 filesystem. (`user: sovol` - `password: sovol`)
2. Transfer folders to `/home/sovol/...`. Overwrite.
3. Restart Klipper service or hard reboot printer.
4. Edit `printer.cfg`:
    - Add `[include dzos.cfg]` to your `printer.cfg` after other `[include]` lines.
5. Save `printer.cfg` changes and restart.

## CONFIGURATION (OPTIONAL):
1. The `dzos.cfg` overrides your `START_PRINT`. This is default but optional.
2. If you want to adjust your own `START_PRINT` read the following: 
    - Make sure you're using the base adaptive bed mesh.
    - Add the DZOS call: `_DZOS_PRINT NOZZLETEMP=<###> BEDTEMP=<##>` just before: `BED_MESH_CALIBRATE_BASE ADAPTIVE=1`. 
    - Ensure you slicer is passing the temperature to your `START_PRINT`.
    - Remove the included `START_PRINT` from the provided `dzos.cfg` macro.

## SETUP:
1. The setup for DZOS only needs to be done when required. If you change your nozzle dimensions or probe you need to re-run.
2. IMPORTANT: Wait for your printer to be `cold and at room temperature` for setup.
3. Remove your toolhead cover for better visibility.
4. Navigate to the web interface for your printer.
5. Under the MACRO section press: `DZOS Enable`. Once pressed hit `SAVE CONFIG` and wait for your printer to restart.
6. Now select: `DZOS INIT SETUP`.
7. The setup is in the form of a guided 2-part PLA print. Use the web interface or device screen to view the real-time instructions.
    ### Guided print overview:
    - **PREP:** Clean your nozzle of filament. Load PLA.
    - **A:** Printer probe samples at room temperature.
    - **B:** Temperature rises to 65C.
    - **C:** Printer probe samples.
    - **D:** Adaptive bed mesh and then a test print begins.
    - **E:** `BEEP - USER INTERACTION - BEEP:` Adjust z offset to your desired z offset as the print prints.
    - **F:** Automatic capture of user input z offset.
    - **G:** `BEEP - USER INTERACTION - BEEP:` Clean finished print either immediately or during the next step.
    - **H:** 1000 second heat soak at 65C.
    - **I:** Repeat of C -> F.
    - **J:** Setup is finished. Printer will reboot.

## USAGE:
1. Print as normal. The Z offset and soak time will calculate per print. Any adjustments made will help DZOS learn.
2. Happy testing!

## DISABLE/RE-ENABLE:
1. `DZOS Disable` macro will stop the code from running. No other changes required.
2. `DZOS Enable` macro will re-enable usage. You do not have to re-run the setup.

## UNINSTALL:
1. Remove `/home/sovol/printer_data/config/dzos.cfg`
2. Remove `/home/sovol/printer_data/config/dzos_print_data.json`
3. Remove `/home/sovol/printer_data/config/dzos_static_data.json`
4. Remove `/home/sovol/printer_data/gcodes/dzos_test_*.gcode`
5. Remove `/home/sovol/klipper/klippy/extras/dzos.py`
6. Ensure your `printer.cfg`'s saved variables related to `[dzos]` are removed.

## ISSUES:
- May not work properly with pause/resume. Untested.