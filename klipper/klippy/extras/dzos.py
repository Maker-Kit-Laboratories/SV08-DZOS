######################################################################################################################################################################################################
# DZOS: DYNAMIC Z OFFSET AND SOAK
# AUTHOR: MAKER KIT LABORATORIES
# VERSION: 0.2.05
######################################################################################################################################################################################################
import json
import os
import numpy as np

######################################################################################################################################################################################################
# PATHS
######################################################################################################################################################################################################
home_path = os.path.expanduser("~")
static_filepath = os.path.join(home_path, "printer_data/config/dzos_static_data.json")
print_data_filepath =  os.path.join(home_path, "printer_data/config/dzos_print_data.json")
######################################################################################################################################################################################################


class DZOS:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.config_name = config.get_name()
    
        self.speed = self.config.getfloat('speed', default=300)
        self.hop_z = self.config.getfloat("z_hop", default=7.5)
        self.speed_z_hop = self.config.getfloat('speed_z_hop', default=10)
        self.dzos_enabled = self.config.getint('enabled', default=0)
        self.dzos_calculated = self.config.getint('calculated', default=0)

        probe_config = self.config.getsection('probe')
        probe_offset_x = probe_config.getfloat('x_offset')
        probe_offset_y = probe_config.getfloat('y_offset')
        self.probe_offset_z = probe_config.getfloat('z_offset')
        
        self.bed_xy = list(self.config.getfloatlist("bed_xy", count=2, default=[191, 165]))
        self.pressure_nozzle_xy = list(self.config.getfloatlist("pressure_xy", count=2, default=[289, 361]))
        self.pressure_xy = [self.pressure_nozzle_xy[0] - probe_offset_x, self.pressure_nozzle_xy[1] - probe_offset_y]

        self.gcode = self.printer.lookup_object('gcode')
        self.gcode_move = self.printer.lookup_object('gcode_move')

        self.gcode.register_command("DZOS_Z_OFFSET", self.cmd_DZOS_Z_OFFSET)
        self.gcode.register_command("DZOS_Z_CALCULATE", self.cmd_DZOS_Z_CALCULATE)
        self.gcode.register_command("DZOS_Z_CAPTURE", self.cmd_DZOS_Z_CAPTURE)


    def cmd_DZOS_Z_OFFSET(self, gcmd):
        self._init_printer_objects()
        cache_static = int(gcmd.get("CACHE_STATIC", 0))
        calibration_nozzle_temperature = int(gcmd.get("NOZZLETEMP", 0))        
        calibration_bed_temperature = int(gcmd.get("BEDTEMP", 0))
        calibration_bed_type = gcmd.get("BEDTYPE", "None")
        force_soak_time = int(gcmd.get("FORCE_SOAK_TIME", 0))      
        enable = int(gcmd.get("ENABLE", -1))
        if enable == 1:
            self.global_configfile.set(self.config_name, "enabled", 1)
            gcmd.respond_info("DZOS: Now Enabled!")
            self._display_msg("DZOS: Enabled!")
            return
        elif enable == 0:
            self.global_configfile.set(self.config_name, "enabled", 0)
            gcmd.respond_info("DZOS: Now Disabled!")
            self._display_msg("DZOS: Disabled!")
            return
        if not self.dzos_enabled:
            gcmd.respond_info("DZOS: Disabled!")
            self._display_msg("DZOS: Disabled!")
            return
        if cache_static == 1:
            self._cache_static(gcmd)
            return
        if calibration_bed_temperature > 0:
            self._set_temperature(120, blocking=False, bed=False) 
            self._set_temperature(calibration_bed_temperature, blocking=True)               
        if not os.path.exists(static_filepath) or self.pressure_xy == [0,0] or self.dzos_calculated == 0:
            gcmd.respond_info("DZOS: No Static Data Found!")
            self._display_msg("DZOS: No Static!")
            return
        self._heat_soak(gcmd, force_soak_time)
        self._calculate_dynamic_offset(
            gcmd, 
            calibration_nozzle_temperature, 
            calibration_bed_temperature, 
            calibration_bed_type
        )


    def cmd_DZOS_Z_CALCULATE(self, gcmd):
        self._init_printer_objects()
        print_data = read_data(print_data_filepath)
        factor_dict = ml_linear_optimize(print_data)
        if factor_dict:
            static_data = read_data(static_filepath)
            static_data["pressure_factor"] = factor_dict["pressure_factor"]
            static_data["bed_factor"] = factor_dict["bed_factor"]
            static_data["nozzle_factor"] = factor_dict["nozzle_factor"]
            static_data["offset_factor"] = factor_dict["offset_factor"]
            write_data(static_filepath, static_data)
            self._set_z_offset(-self.probe_offset_z)
            self.global_configfile.set(self.config_name, "calculated", 1)
            gcmd.respond_info("DZOS: Stored..")
            self._display_msg("DZOS: Stored..")
        else:
            gcmd.respond_info("DZOS: Not Enough Data!")
            self._display_msg("DZOS: Not Enough Data!")



    def cmd_DZOS_Z_CAPTURE(self, gcmd):
        self._init_printer_objects()
        toolhead = self.printer.lookup_object('toolhead')
        z_position = toolhead.get_position()[2]
        gcode_position = self.gcode_move._get_gcode_position()
        z = gcode_position[2]
        z_offset = z - (z_position - self.probe_offset_z)
        gcmd.respond_info(f"DZOS: Captured Z: {z_offset}")
        print_data = read_data(print_data_filepath)
        print_data[-1]["z_offset"] = z_offset
        write_data(print_data_filepath, print_data)
        self.cmd_DZOS_Z_CALCULATE(gcmd)



    def _init_printer_objects(self):
        self.toolhead = self.printer.lookup_object('toolhead')
        self.probe_object = self.printer.lookup_object('probe')
        self.probe_pressure_object = self.printer.lookup_object('probe_pressure')
        self.display_status_object = self.printer.lookup_object('display_status')
        self.global_configfile = self.printer.lookup_object('configfile')
        self.heater_bed = self.printer.lookup_object('heater_bed')
        self.extruder = self.printer.lookup_object('extruder')


    def _init_static_data(self):
        try:
            static_data = read_data(static_filepath)
            self.static_e_pressure_nozzle = static_data["e_pressure_nozzle_z"]
            self.static_pressure_factor = static_data["pressure_factor"]
            self.static_bed_factor = static_data["bed_factor"]
            self.static_nozzle_factor = static_data["nozzle_factor"]
            self.static_offset_factor = static_data["offset_factor"]
        except:
            self.static_pressure_factor = 0
            self.static_bed_factor = 0
            self.static_nozzle_factor = 0
            self.static_offset_factor = 0

    def _cache_static(self, gcmd):
        delete_file(print_data_filepath)
        delete_file(static_filepath)
        self._display_msg("DZOS: Caching..")
        gcmd.respond_info("DZOS: Caching..")
        b_pressure_z_s1 = self._generic_z_probe(gcmd, self.probe_object, x=self.pressure_xy[0], y=self.pressure_xy[1])
        b_pressure_z_s2 = self._generic_z_probe(gcmd, self.probe_object, x=self.pressure_xy[0], y=self.pressure_xy[1])
        b_pressure_z = (b_pressure_z_s1 + b_pressure_z_s2) / 2
        self._set_z_zero(b_pressure_z)

        e_pressure_nozzle = self._generic_z_probe(gcmd, self.probe_pressure_object, x=self.pressure_nozzle_xy[0], y=self.pressure_nozzle_xy[1])
        e_bed_z_s1 = self._generic_z_probe(gcmd, self.probe_object, x=self.bed_xy[0], y=self.bed_xy[1])
        e_bed_z_s2 = self._generic_z_probe(gcmd, self.probe_object, x=self.bed_xy[0], y=self.bed_xy[1])
        e_bed_z = (e_bed_z_s1 + e_bed_z_s2) / 2
        self._set_z_zero(e_bed_z)

        data_dict = {
            "e_pressure_nozzle_z": e_pressure_nozzle
        }
        write_data(static_filepath, data_dict)


    def _calculate_dynamic_offset(self, gcmd, nozzle_temperature, bed_temperature, bed_type):
        self._display_msg("DZOS: Calc..")

        intial_z_s1 = self._generic_z_probe(gcmd, self.probe_object, x=self.bed_xy[0], y=self.bed_xy[1])
        intial_z_s2 = self._generic_z_probe(gcmd, self.probe_object, x=self.bed_xy[0], y=self.bed_xy[1])
        initial_z = (intial_z_s1 + intial_z_s2) / 2
        self._set_z_zero(initial_z)

        d_pressure_z_s1 = self._generic_z_probe(gcmd, self.probe_object, x=self.pressure_xy[0], y=self.pressure_xy[1])
        d_pressure_z_s2 = self._generic_z_probe(gcmd, self.probe_object, x=self.pressure_xy[0], y=self.pressure_xy[1])
        d_pressure_z = (d_pressure_z_s1 + d_pressure_z_s2) / 2
        self._set_z_zero(d_pressure_z)
        
        d_bed_z_s1 = self._generic_z_probe(gcmd, self.probe_object, x=self.bed_xy[0], y=self.bed_xy[1])
        d_bed_z_s2 = self._generic_z_probe(gcmd, self.probe_object, x=self.bed_xy[0], y=self.bed_xy[1])
        d_bed_z = (d_bed_z_s1 + d_bed_z_s2) / 2
        self._set_z_zero(d_bed_z)
            
        z_offset = self._calculate_z_offset(d_pressure_z, nozzle_temperature, bed_temperature, bed_type)
        print_data = self._create_data_dict(d_bed_z, d_pressure_z, nozzle_temperature, bed_temperature, bed_type)
        append_data(print_data_filepath, print_data)

        gcmd.respond_info("DZOS: Z Offset: %.3f" % z_offset)
        self._display_msg(f"DZOS: Z {z_offset:.3f}")
        
        self._set_z_offset(z_offset + self.probe_offset_z)


    def _heat_soak(self, gcmd, force_soak_time=0):
        if force_soak_time > 0:
            duration = force_soak_time
        else:
            exclude_objects = self.printer.lookup_object("exclude_object", None)
            objects = exclude_objects.get_status().get("objects", [])
            margin = 2.0
            list_of_xs = []
            list_of_ys = []
            gcmd.respond_info("Found %s objects." % (len(objects)))
            for obj in objects:
                for point in obj["polygon"]:
                    list_of_xs.append(point[0])
                    list_of_ys.append(point[1])

            print_min = [min(list_of_xs), min(list_of_ys)]
            print_max = [max(list_of_xs), max(list_of_ys)]
            margin_print_min = [x - margin for x in print_min]
            margin_print_max = [x + margin for x in print_max]

            print_max_center_size = max(abs(175 - margin_print_max[0]), abs(175 - margin_print_min[0]), abs(175 - margin_print_max[1]), abs(175 - margin_print_min[1]))
            gcmd.respond_info("DZOS: Center Offset: %.2fmm" % print_max_center_size)
            duration = max(int(print_max_center_size / 0.087) - 300, 0)
        gcmd.respond_info("DZOS: Calculated Soak Time: %is" % duration)
        iteration = 0
        while iteration < duration:
            self._display_msg(f"DZOS: Soak-{int(duration - iteration)}s")
            self.toolhead.dwell(1)
            iteration += 1
        return duration


    def _display_msg(self, msg):
        gcmd = self.gcode.create_gcode_command(f"M117 {msg}", f"M117 {msg}", {})
        self.display_status_object.cmd_M117(gcmd)


    def _calculate_z_offset(self, d_pressure_z, nozzle_temperature, bed_temperature, bed_type):
        self._init_static_data()
        if self.static_pressure_factor:
            target_z_offset = (self.static_pressure_factor * d_pressure_z) + (self.static_nozzle_factor * nozzle_temperature) + (self.static_bed_factor * bed_temperature) + self.static_offset_factor
        else:
            target_z_offset = -self.static_e_pressure_nozzle
        return -target_z_offset


    def _generic_z_probe(self, gcmd, probe_object, x, y, hop=True):
        try:
            return self._latest_z_probe(gcmd, probe_object, x, y, hop)
        except:
            return self._stock_z_probe(gcmd, probe_object, x, y, hop)


    def _stock_z_probe(self, gcmd, probe_object, x, y, hop=True):
        if hop:
            self._execute_hop_z(self.hop_z)
            self.toolhead.manual_move([x, y, None], self.speed)
        probe_z = probe_object.run_probe(gcmd)[2]
        return probe_z


    def _latest_z_probe(self, gcmd, probe_object, x, y, hop=True):
        if hop:
            self._execute_hop_z(self.hop_z)
            self.toolhead.manual_move([x, y, None], self.speed)
        probe_session = probe_object.start_probe_session(gcmd)
        probe_session.run_probe(gcmd)
        probe_z = probe_session.pull_probed_results()[0][2]
        probe_session.end_probe_session()
        return probe_z


    def _set_z_zero(self, z):
        current = list(self.toolhead.get_position())
        current[2] = current[2] - z
        self.toolhead.set_position(current)


    def _execute_hop_z(self, z):
        self.toolhead.manual_move([None, None, z], self.speed_z_hop)


    def _set_z_offset(self, offset):
        gcmd_offset = self.gcode.create_gcode_command("SET_GCODE_OFFSET", "SET_GCODE_OFFSET", {'Z': offset})
        self.gcode_move.cmd_SET_GCODE_OFFSET(gcmd_offset)


    def _save_z_offset(self):
        gcmd_probe_save = self.gcode.create_gcode_command("Z_OFFSET_APPLY_PROBE", "", {})
        self.printer.lookup_object('probe').cmd_Z_OFFSET_APPLY_PROBE(gcmd_probe_save)


    def _create_data_dict(self, d_bed_z, d_pressure_z, nozzle_temperature, bed_temperature, bed_type):
        self._init_static_data()
        data_dict = {
            "e_pressure_nozzle_z": self.static_e_pressure_nozzle,
            "d_bed_z": d_bed_z,
            "d_pressure_z": d_pressure_z,
            "nozzle_temperature": nozzle_temperature,
            "bed_temperature": bed_temperature,
            "bed_type": bed_type,
        }
        return data_dict


    def _set_temperature(self, temperature, blocking=False, bed=True):
        if bed:
            gcode_string = "M140"
        else:
            gcode_string = "M104"
        if blocking:
            if bed:
                gcode_string = "M190"
            else:
                gcode_string = "M109"
        gcmd_heater_set = self.gcode.create_gcode_command(
            gcode_string,
            gcode_string,
            {
                "S": temperature,
            }
        )
        if blocking:
            if bed:
                self.heater_bed.cmd_M190(gcmd_heater_set)
            else:
                self.extruder.cmd_M109(gcmd_heater_set)
        else:
            if bed:
                self.heater_bed.cmd_M140(gcmd_heater_set)
            else:
                self.extruder.cmd_M104(gcmd_heater_set)


    def _quad_gantry_level(self):
        gcmd_qgl = self.gcode.create_gcode_command("QUAD_GANTRY_LEVEL", "QUAD_GANTRY_LEVEL", {})
        qgl = self.printer.lookup_object('quad_gantry_level')
        qgl.cmd_QUAD_GANTRY_LEVEL(gcmd_qgl)


    def _home(self, axes="Z"):
        gcmd_home = self.gcode.create_gcode_command("G28", "G28", {axes: None})
        home = self.printer.lookup_object('homing_override')
        home.cmd_G28(gcmd_home)


def load_config(config):
    return DZOS(config)




######################################################################################################################################################################################################
# UTILS
######################################################################################################################################################################################################


def write_data(file_path, data):
    with open(file_path, "w") as file:
        json.dump(data, file, indent=4)


def append_data(file_path, data):
    if not os.path.exists(file_path):
        write_data(file_path, [])
    loaded_data: list = read_data(file_path)
    loaded_data.append(data)
    with open(file_path, "w") as file:
        json.dump(loaded_data, file, indent=4)


def read_data(file_path):
    with open(file_path, "r") as file:
        data = json.load(file)
    return data

def delete_file(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)

######################################################################################################################################################################################################
# ML
# - Add bed type to learning
######################################################################################################################################################################################################



def ml_linear_optimize(print_data_list):
    pressure_list = []
    bed_list = []
    nozzle_list = []
    z_list = []
    for entry in print_data_list:
        pressure = entry.get('d_pressure_z')
        bed_temperature = entry.get('bed_temperature')
        nozzle_temperature = entry.get('nozzle_temperature')
        z_offset = entry.get('z_offset')
        if not z_offset:
            continue
        pressure_list.append(float(pressure))
        bed_list.append(float(bed_temperature))
        nozzle_list.append(float(nozzle_temperature))
        z_list.append(float(z_offset))
    if len(z_list) < 2:
        return

    data = np.column_stack([
        np.array(pressure_list, dtype=float),
        np.array(bed_list, dtype=float),
        np.array(nozzle_list, dtype=float),
        np.ones(len(z_list), dtype=float)
    ])
    target = np.array(z_list, dtype=float)

    result = np.linalg.lstsq(data, target, rcond=None)
    p_factor, b_factor, n_factor, offset = result[0]

    factor_dict = {
        "pressure_factor": float(p_factor),
        "bed_factor": float(b_factor),
        "nozzle_factor": float(n_factor),
        "offset_factor": float(offset),
    }
    return factor_dict




