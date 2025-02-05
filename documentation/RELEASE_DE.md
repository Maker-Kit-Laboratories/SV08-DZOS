# DZOS: Dynamischer Z-Versatz und Temperatur-Soaking

## RELEASE NOTES:
- Updates machen bestehende Setups oder gespeicherte Daten nicht ungültig.

### 0.1.45
- Verbesserte geführte INIT SETUP-Druckroutine. `G28 Z` und `QUAD_GANTRY_LEVEL_BASE` wieder hinzugefügt, um die Genauigkeit zu erhöhen.
- Verbesserte Unterstützung für verschiedene Klipper-/Firmware-Versionen.

### 0.1.44
- Testdateien umbenannt.
- Testdrucke mit genaueren Soak-Zeiten aktualisiert.
- Einige Elemente der INIT SETUP verbessert.

### 0.1.43
- Problem behoben, das erforderte, den gespeicherten `z_offset` auf `0.0` zu setzen, bevor INIT SETUP ausgeführt wurde.
- Gcode-Datei aktualisiert. Überflüssige Aktionen während INIT SETUP entfernt.
- Fehler mit doppeltem `G28` in `_DZOS_PRINT` behoben.
- Verbesserte anfängliche sichere Z-Höhe, die automatisch bei INIT SETUP gesetzt wird.
- Hauptzweig-Kompatibilität bestätigt.
- Testdrucke hinzugefügt. PLA – Standard-SV08-Profil.

### 0.1.42
- Doppeltes `G28` im `START_PRINT`-Beispielmakro entfernt, wenn das Standarddruckerprofil verwendet wird.

### 0.1.41
- Neues `_DZOS_PRINT`-Makro für den Druckprozess hinzugefügt.
- Konfigurierbares Soak-Zeit-Makro `DZOS_SOAK_TIME` hinzugefügt. Speichert temporär eine Soak-Zeit, die beim Druck abgerufen wird.

### 0.1.40
- Einfaches `START_PRINT`-Makro für optimierte Nutzung hinzugefügt.
- Dokumentation präzisiert.

### 0.1.39
- Pfade auf relative Pfadangaben umgestellt.
- Versteckte `.` am Anfang von `dzos_test_combined.gcode` entfernt.
- Sollte nun Hauptzweig unterstützen. Nicht getestet.

### 0.1.38
- Mögliche verbesserte Unterstützung für Hauptzweig. Problem mit `pressure_probe` behoben. Nicht getestet.

### 0.1.37
- Mögliche verbesserte Unterstützung für Hauptzweig. Problem mit fehlendem Argument behoben. Nicht getestet.

### 0.1.36
- Verbesserte Benutzerführung (UX), Dokumentation und Code.
- Erste experimentelle Unterstützung für Hauptzweig/Standard-SV08-Klipper. Nicht getestet.

### 0.1.34
- Erstveröffentlichung. Getestet auf Standard-SV08.
