![LOGO](./images/dzos_logo.png)

# DZOS: Dynamic Z Offset and Soaking

## PRE-REQUISITES:
1. SV08 3D Printer with an `inductive` or `eddy` sensor and the stock pressure/load cell working.
2. Terminal / Powershell
3. Slicer Config: 
    - Configure your slicer to pass `NOZZLETEMP=<###>` `BEDTEMP=<##>` `BEDTYPE=<Slicer Bed Type>` to `START_PRINT`.
    - OrcaSlicer Example: `START_PRINT NOZZLETEMP=[nozzle_temperature_initial_layer] BEDTEMP=[bed_temperature_initial_layer_single] BEDTYPE="[curr_bed_type]"`
4. Ensure your hotend/nozzle is tight! Loose components move more during heat change.

## INSTALL:
1. Access the SV08 via SSH. ( `ssh sovol@<your sv08 ip>` )
2. `git clone https://github.com/Maker-Kit-Laboratories/SV08-DZOS.git`
3. `cd SV08-DZOS`
4. `chmod +x dzos_install.sh`
5. `./dzos_install.sh`
6. Restart your entire printer.

## UPDATE:
1. Access the SV08 via SSH. ( `ssh sovol@<your sv08 ip>` )
2. `cd SV08-DZOS`
3. `chmod +x dzos_update.sh`
4. `./dzos_update.sh`
5. Restart your entire printer.

## UNINSTALL:
1. Access the SV08 via SSH. ( `ssh sovol@<your sv08 ip>` )
2. `cd SV08-DZOS`
3. `chmod +x dzos_install.sh`
4. `./dzos_remove.sh` 
5. Ensure your `printer.cfg` saved variables related to `[dzos]` are removed.
6. Restart your entire printer.

## SETUP (IMPORTANT):
0. READ `dzos.cfg` comments first.
1. If using an eddy type probe, set `eddy` to `True` in `dzos.cfg`.
2. Set the `sensor_name` to match your eddy probe temperature sensor. If not using an eddy sensor, set sensor_name to your toolhead temperature sensor.
3. Set your current `z-offset` to `0.0` in your `printer.cfg` saved section.
4. In `dzos.cfg` you must set eddy to `True` if using an eddy. The eddy must be minimally calibrated prior to DZOS use.
5. The INIT for DZOS only needs to be done when required. If you change your nozzle dimensions or probe you need to re-run.
6. IMPORTANT: Wait for your printer to be `cold and at room temperature` for setup.
7. Remove your toolhead cover for better visibility.
8. Navigate to the web interface for your printer.
9. Under the MACRO section press: `DZOS Enable`. Once pressed hit `SAVE CONFIG` and wait for your printer to restart.
10. Now select: `DZOS INIT SETUP`.
11. The setup is in the form of a guided 2-part PLA print. Use the web interface or device screen to view the real-time instructions.
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
    - **I:** Printer will repeat C -> F printing again.
    - **J:** Setup is finished.

## CONFIGURATION (OPTIONAL):
- NOTE: The `dzos.cfg` overrides your `START_PRINT`. This is default but optional.
1. If you want to adjust your own `START_PRINT` read the following: 
    - Make sure you're using the base adaptive bed mesh.
    - In your current start print record your current bed temperature as `INPUT_CURRENT_BEDTEMP` before you do any bed heating.
    - Then add the DZOS call: `_DZOS_PRINT NOZZLETEMP=<###> BEDTEMP=<##> CURRENT_BEDTEMP=INPUT_CURRENT_BEDTEMP BEDTYPE=<Textured PEI Plate...>` just before: `BED_MESH_CALIBRATE_BASE ADAPTIVE=1`. 
    - Ensure you slicer is passing the temperature to your `START_PRINT`.
    - Remove the included `START_PRINT` from the provided `dzos.cfg` macro.
2. DZOS has a few addition configurtation options if you want to experiment:
    - sensor_name - `none` : Name of your chamber, toolhead, or eddy temperature sensor.
    - eddy - `False | True` : True if using an eddy current probe of any kind.
    - soak_xy - `x,y,z` : The location of the toolhead during heat soaking. If your printer isn't enclosed, centering it more can help.
    - soak_multiplier - `1.0` : Multiplier to lengthen or shorten soak duration.
    - outlier_sample_min - `20` : Minimum number of samples required before outliers are removed.
    - outlier_deviation - `3.0` : Threshold for outlier removal.
    - polynomial - `True | False` : Uses a polynomial fit for calculcation.
    - polynomial_sample_min - `10` : Minimum number of samples required for polynomial fit.
3. DZOS understands the default bed plate types from OrcaSlicer and will learn from there usage.
    - Too keep track of what print is associated with what bed plate, use a name in the gcode file.

## USAGE:
1. Print as normal. The Z offset and soak time will predict per print. Manual Z adjustments made will help DZOS learn.
2. If you change your nozzle to a different sized one, use `DZOS_NOZZLE_RESET` and print as normal.
3. Happy testing!

## DISABLE/RE-ENABLE:
1. `DZOS Disable` macro will stop the code from running. No other changes required.
2. `DZOS Enable` macro will re-enable usage. You do not have to re-run the setup.

## ISSUES:
- Training takes a few prints per context. IE. A bed type or different filament. Doing a few one layer prints with the materials and beds you use helps speed it up.