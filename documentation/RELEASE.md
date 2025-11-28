
# DZOS: Dynamic Z Offset and Soaking

### 0.2.07
- Fixed issue with init.
- Added more intelligent soaking.

### 0.2.06
- Fixed macro issue not clearing bed mesh.

### 0.2.05
- WARNING: INIT MUST BE RE-RUN.
- Changed calculation method and parameters.
- Added machine learning. Printer will learn from manual adjustments.

### 0.2.01
- Bug fixed.

### 0.2.00
- Added automatic dynamic soaking.
- Added plate offsets.

### 0.1.45
- Improved INIT SETUP guided print. Re-added G28 Z and QUAD_GANTRY_LEVEL_BASE to improve accuracy.
- Imporved support for various klipper/firmware versions.

### 0.1.44
- Renamed test files.
- Updated test prints with more accurate soak times.
- Improved some elements of INIT SETUP.

### 0.1.43
- Fixed issue that required setting the stored z_offset to 0.0 before running the INIT SETEP.
- Updated gcode file. Removed redundant actions during the INIT SETUP.
- Fixed bug with double G28 in _DZOS_PRINT.
- Improved initial safe Z that auto sets when performing the INIT SETUP.
- Confirmed mainline support.
- Added test prints. PLA - Stock SV08 profile.

### 0.1.42
- Fixed double G28 in START_PRINT example macro if using stock printer profile.

### 0.1.41
- Added new _DZOS_PRINT macro for handing printing.
- Added configurable soak time macro DZOS_SOAK_TIME. Temporarily caches a soak time that will be accessed at print.

### 0.1.40
- Added simple START_PRINT macro for optimized usage.
- Documentation clarifications.

### 0.1.39
- Fixed pathing to be relative.
- Removed hiding "." from beginning of dzos_test_combined.gcode.
- Should now support mainline. Untested.

### 0.1.38
- Possible improved support for mainline. Fixed issue with pressure_probe. Untested.

### 0.1.37
- Possible improved support for mainline. Fixed issue with missing argument. Untested.

### 0.1.36
- Improved UX, documentation and code.
- Initial hacky support for mainline/stock sv08 klipper. Untested.

### 0.1.34
- Initial release. Tested on stock sv08.














## SPECIAL THANKS:
- Scott
- Mike @ MK3D
- Bgoat96
- ZarkHowler
- ovrCaffeinatd
- dwmcqueen