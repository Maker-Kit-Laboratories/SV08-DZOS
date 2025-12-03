######################################################################################################################################################################################################
# DZOS: DYNAMIC Z OFFSET AND SOAK
# AUTHOR: MAKER KIT LABORATORIES
# VERSION: 0.4.00
######################################################################################################################################################################################################
import json
import os
import numpy as np
import time
import math

######################################################################################################################################################################################################
# PATHS
######################################################################################################################################################################################################
HOME_PATH = os.path.expanduser("~")
STATIC_FILEPATH = os.path.join(HOME_PATH, "printer_data/config/dzos_static_data.json")
PRINT_DATA_FILEPATH =  os.path.join(HOME_PATH, "printer_data/config/dzos_print_data.json")
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

        self.plate_thickness_dict = {
            "none": self.config.getfloat('default_plate', default=0.000),
            "smooth cool plate": self.config.getfloat('smooth_cool', default=0.000),
            "high temp plate": self.config.getfloat('high_temp', default=0.000),
            "engineering plate": self.config.getfloat('engineering', default=0.000),
            "textured pei plate": self.config.getfloat('textured_pei', default=0.000),
            "textured cool plate": self.config.getfloat('textured_cool', default=0.000),
            "cool plate (supertack)": self.config.getfloat('cool_super_tack', default=0.000),
        }

        self.polynomial = self.config.getboolean('polynomial', default=False)
        self.advanced_sample_min = self.config.getint('advanced_sample_min', default=20)
        if self.polynomial:
            print_data = read_data(PRINT_DATA_FILEPATH)
            if not print_data:
                self.polynomial = False
            else:
                samples = len(print_data)
                self.polynomial = True if samples >= self.advanced_sample_min else False
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
        current_bed_temperature = float(gcmd.get("CURRENT_BEDTEMP", 0))
        force_soak_time = int(gcmd.get("FORCE_SOAK_TIME", 0))
        nozzle_reset = int(gcmd.get("NOZZLE_RESET", 0))
        enable = int(gcmd.get("ENABLE", -1))
        if enable == 1:
            self.global_configfile.set(self.config_name, "enabled", 1)
            gcmd.respond_info("DZOS: Enabled!")
            self._display_msg("DZOS: Enabled!")
            return
        elif enable == 0:
            self.global_configfile.set(self.config_name, "enabled", 0)
            gcmd.respond_info("DZOS: Disabled!")
            self._display_msg("DZOS: Disabled!")
            return
        if not self.dzos_enabled:
            gcmd.respond_info("DZOS: Disabled!")
            self._display_msg("DZOS: Disabled!")
            return
        if cache_static == 1:
            self._cache_static(gcmd)
            return
        if nozzle_reset == 1:
            self._nozzle_reset(gcmd)
            return
        if calibration_bed_temperature > 0:
            self._set_temperature(calibration_bed_temperature, blocking=True)               
        if not os.path.exists(STATIC_FILEPATH) or self.pressure_xy == [0,0]:
            gcmd.respond_info("DZOS: No Static Data Found!")
            self._display_msg("DZOS: No Static!")
            return
        gcmd.respond_info(f"DZOS: Bed Type: {calibration_bed_type}")
        self._display_msg(f"DZOS: Bed {calibration_bed_type}")
        self._heat_soak(gcmd, current_bed_temperature, calibration_bed_temperature, force_soak_time)
        self._calculate_dynamic_offset(
            gcmd, 
            calibration_nozzle_temperature,
            calibration_bed_temperature, 
            calibration_bed_type,
            self.polynomial,
        )


    def cmd_DZOS_Z_CALCULATE(self, gcmd):
        statistics = int(gcmd.get("STATISTICS", 0)) 
        self._init_printer_objects()
        gcmd.respond_info("DZOS: Calc...")
        self._display_msg("DZOS: Calc...")       
        print_data = read_data(PRINT_DATA_FILEPATH)
        if not print_data:
            gcmd.respond_info("DZOS: No Print Data Found!")
            self._display_msg("DZOS: No Print!")
            return
        if self.polynomial:
            factor_dict = ml_polynomial_optimize(print_data, self.plate_thickness_dict, self.advanced_sample_min) 
        else:
            factor_dict = ml_linear_optimize(print_data, self.plate_thickness_dict, self.advanced_sample_min)
        if factor_dict:
            static_data = read_data(STATIC_FILEPATH)
            if not static_data:
                gcmd.respond_info("DZOS: No Static Data Found!")
                self._display_msg("DZOS: No Static!")
                return                
            static_data["nozzle_factor"] = factor_dict["nozzle_factor"]
            static_data["nozzle_temperature_factor"] = factor_dict["nozzle_temperature_factor"]
            static_data["bed_factor"] = factor_dict["bed_factor"]
            if self.polynomial:
                static_data["bed_factor2"] = factor_dict["bed_factor2"]
            static_data["bed_temperature_factor"] = factor_dict["bed_temperature_factor"]
            if self.polynomial:
                static_data["bed_temperature_factor2"] = factor_dict["bed_temperature_factor2"]
            static_data["bed_thickness_factor"] = factor_dict["bed_thickness_factor"]    
            static_data["offset_factor"] = factor_dict["offset_factor"]
            static_data["statistics"] = factor_dict["statistics"]
            write_data(STATIC_FILEPATH, static_data) 
            if statistics:
                gcmd.respond_info(f"DZOS: Type: {'Polynomial' if self.polynomial else 'Linear'}")
                gcmd.respond_info(f"DZOS: Samples: {factor_dict['statistics']['samples']}") 
                gcmd.respond_info(f"DZOS: Outliers: {factor_dict['statistics']['outliers']}")
                gcmd.respond_info(f"DZOS: Error: ±{factor_dict['statistics']['error']:.3f}")
                gcmd.respond_info(f"DZOS: Nozzle Z: {factor_dict['statistics']['nozzle']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Nozzle Temperature: {factor_dict['statistics']['nozzle_temperature']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Z: {factor_dict['statistics']['bed']['mean']:.3f}")
                if self.polynomial:
                    gcmd.respond_info(f"DZOS: Bed² Z: {factor_dict['statistics']['bed2']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Temperature: {factor_dict['statistics']['bed_temperature']['mean']:.3f}")
                if self.polynomial:
                    gcmd.respond_info(f"DZOS: Bed Temperature²: {factor_dict['statistics']['bed_temperature2']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Thickness: {factor_dict['statistics']['bed_thickness']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Offset: {factor_dict['statistics']['offset']['mean']:.3f}")
            else:
                self._set_z_offset(-self.probe_offset_z)
                gcmd.respond_info("DZOS: Complete!")
        else:
            gcmd.respond_info("DZOS: Not Enough Data!")
            self._display_msg("DZOS: Data!")


    def cmd_DZOS_Z_CAPTURE(self, gcmd):
        self._init_printer_objects()
        toolhead = self.printer.lookup_object('toolhead')
        z_position = toolhead.get_position()[2]
        gcode_position = self.gcode_move._get_gcode_position()
        z = gcode_position[2]
        z_offset = z - (z_position - self.probe_offset_z)
        gcmd.respond_info(f"DZOS: Captured Z: {z_offset}")
        print_data = read_data(PRINT_DATA_FILEPATH)
        print_data[-1]["z_offset"] = z_offset
        print_data[-1]["timestamp"] = time.time()
        write_data(PRINT_DATA_FILEPATH, print_data)
        self.cmd_DZOS_Z_CALCULATE(gcmd)


    def _init_printer_objects(self):
        self.toolhead = self.printer.lookup_object('toolhead')
        self.probe_object = self.printer.lookup_object('probe')
        self.probe_pressure_object = self.printer.lookup_object('probe_pressure')
        self.display_status_object = self.printer.lookup_object('display_status')
        self.global_configfile = self.printer.lookup_object('configfile')
        self.heater_bed = self.printer.lookup_object('heater_bed')
        self.extruder = self.printer.lookup_object('extruder')
        self.heaters = self.printer.lookup_object('heaters')


    def _init_static_data(self):
        static_data = read_data(STATIC_FILEPATH)
        if not static_data:
            static_data = {}
        self.static_e_pressure_nozzle = static_data.get("e_pressure_nozzle_z", 0)
        self.static_nozzle_factor = static_data.get("nozzle_factor", 0)
        self.static_nozzle_temperature_factor = static_data.get("nozzle_temperature_factor", 0)
        self.static_bed_factor = static_data.get("bed_factor", 0)
        self.static_bed_factor2 = static_data.get("bed_factor2", 0)
        self.static_bed_temperature_factor = static_data.get("bed_temperature_factor", 0)
        self.static_bed_temperature_factor2 = static_data.get("bed_temperature_factor2", 0)
        self.static_bed_thickness_factor = static_data.get("bed_thickness_factor", 0)
        self.static_offset_factor = static_data.get("offset_factor", 0)




    def _cache_static(self, gcmd):
        self._display_msg("DZOS: Caching..")
        gcmd.respond_info("DZOS: Caching..")

        backup_file(STATIC_FILEPATH)
        backup_file(PRINT_DATA_FILEPATH)
        delete_file(STATIC_FILEPATH)
        delete_file(PRINT_DATA_FILEPATH)

        self._generic_z_probe(gcmd, self.probe_object, x=self.pressure_xy[0], y=self.pressure_xy[1])
        b_pressure_z = self._generic_z_probe(gcmd, self.probe_object, x=self.pressure_xy[0], y=self.pressure_xy[1])
        self._set_z_zero(b_pressure_z)
        
        self._generic_z_probe(gcmd, self.probe_pressure_object, x=self.pressure_nozzle_xy[0], y=self.pressure_nozzle_xy[1])
        e_pressure_nozzle = self._generic_z_probe(gcmd, self.probe_pressure_object, x=self.pressure_nozzle_xy[0], y=self.pressure_nozzle_xy[1])
        
        self._generic_z_probe(gcmd, self.probe_object, x=self.bed_xy[0], y=self.bed_xy[1])
        e_bed_z = self._generic_z_probe(gcmd, self.probe_object, x=self.bed_xy[0], y=self.bed_xy[1]) 
        self._set_z_zero(e_bed_z)

        data_dict = {
            "e_pressure_nozzle_z": e_pressure_nozzle,
        }
        write_data(STATIC_FILEPATH, data_dict)


    def _nozzle_reset(self, gcmd):
        self._display_msg("DZOS: Nozzle..")
        gcmd.respond_info("DZOS: Nozzle Reset..")
        
        d_pressure_z_s1 = self._generic_z_probe(gcmd, self.probe_object, x=self.pressure_xy[0], y=self.pressure_xy[1])
        d_pressure_z_s2 = self._generic_z_probe(gcmd, self.probe_object, x=self.pressure_xy[0], y=self.pressure_xy[1])
        d_pressure_z = (d_pressure_z_s1 + d_pressure_z_s2) / 2.0
        self._set_z_zero(d_pressure_z)
        
        self._generic_z_probe(gcmd, self.probe_pressure_object, x=self.pressure_nozzle_xy[0], y=self.pressure_nozzle_xy[1])
        e_pressure_nozzle = self._generic_z_probe(gcmd, self.probe_pressure_object, x=self.pressure_nozzle_xy[0], y=self.pressure_nozzle_xy[1])

        data_dict = {
            "e_pressure_nozzle_z": e_pressure_nozzle,
        }
        write_data(STATIC_FILEPATH, data_dict)
        self.cmd_DZOS_Z_CALCULATE(gcmd)


    def _calculate_dynamic_offset(self, gcmd, nozzle_temperature, bed_temperature, bed_type, polynomial):
        self._display_msg("DZOS: Calc..")

        initial_z = self._generic_z_probe(gcmd, self.probe_object, x=self.bed_xy[0], y=self.bed_xy[1])
        self._set_z_zero(initial_z)

        d_pressure_z_s1 = self._generic_z_probe(gcmd, self.probe_object, x=self.pressure_xy[0], y=self.pressure_xy[1])
        d_pressure_z_s2 = self._generic_z_probe(gcmd, self.probe_object, x=self.pressure_xy[0], y=self.pressure_xy[1])
        d_pressure_z = (d_pressure_z_s1 + d_pressure_z_s2) / 2.0
        self._set_z_zero(d_pressure_z)
        
        d_bed_z_s1 = self._generic_z_probe(gcmd, self.probe_object, x=self.bed_xy[0], y=self.bed_xy[1])
        d_bed_z_s2 = self._generic_z_probe(gcmd, self.probe_object, x=self.bed_xy[0], y=self.bed_xy[1])
        d_bed_z = (d_bed_z_s1 + d_bed_z_s2) / 2.0
        self._set_z_zero(d_bed_z)

        if polynomial:
            z_offset = self._calculate_z_offset_polynomial(d_bed_z, nozzle_temperature, bed_temperature, bed_type)
        else:   
            z_offset = self._calculate_z_offset(d_bed_z, nozzle_temperature, bed_temperature, bed_type)
        print_data = self._create_data_dict(d_bed_z, d_pressure_z, nozzle_temperature, bed_temperature, bed_type)
        append_data(PRINT_DATA_FILEPATH, print_data)

        gcmd.respond_info("DZOS: Z Offset: %.3f" % z_offset)
        self._display_msg(f"DZOS: {z_offset:.3f}")
        
        self._set_z_offset(z_offset + self.probe_offset_z)


    def _heat_soak(self, gcmd, current_bed_temperature: float, bed_temperature: int, force_soak_time: int=0):
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
            gcmd.respond_info("DZOS: Center Offset: %.3fmm" % print_max_center_size)
            soak_factor = self._calculate_soak_factor(current_bed_temperature, bed_temperature)
            gcmd.respond_info("DZOS: Soak Factor: %.3f" % soak_factor)
            duration =  int(max(((print_max_center_size / 0.085) - 300) * soak_factor, 60))
        gcmd.respond_info("DZOS: Soak Time: %is" % duration)
        iteration = -1
        nozzle_heater_enabled = False
        while iteration < duration:
            remaining = duration - iteration
            self._display_msg(f"DZOS: Soak-{int(remaining)}s")
            if not nozzle_heater_enabled and remaining <= 60:
                self._set_temperature(120, blocking=False, bed=False) 
                nozzle_heater_enabled = True
            self.toolhead.dwell(1)
            iteration += 1
        return duration


    def _display_msg(self, msg: str):
        gcmd = self.gcode.create_gcode_command(f"M117 {msg}", f"M117 {msg}", {})
        self.display_status_object.cmd_M117(gcmd)


    def _calculate_z_offset(self,
            d_bed_z: float,
            nozzle_temperature: int,            
            bed_temperature: int, 
            bed_type: str
        ) -> float:
        self._init_static_data()
        if self.static_bed_factor:
            plate_thickness = self.plate_thickness_dict[bed_type.lower()]
            target_z_offset = (
                (self.static_nozzle_factor * -self.static_e_pressure_nozzle) +
                (self.static_bed_factor * d_bed_z) + (self.static_bed_temperature_factor * bed_temperature) +
                (self.static_bed_thickness_factor * plate_thickness) + 
                (self.static_nozzle_temperature_factor * nozzle_temperature) +
                self.static_offset_factor
            )
        else:
            target_z_offset = -self.static_e_pressure_nozzle
        target_z_offset = -target_z_offset
        
        return target_z_offset


    def _calculate_z_offset_polynomial(self,
            d_bed_z: float,
            nozzle_temperature: int,            
            bed_temperature: int, 
            bed_type: str
        ) -> float:
        self._init_static_data()
        if self.static_bed_factor:
            plate_thickness = self.plate_thickness_dict[bed_type.lower()]
            target_z_offset = (
                (self.static_nozzle_factor * -self.static_e_pressure_nozzle) +
                (self.static_nozzle_temperature_factor * nozzle_temperature) +
                (self.static_bed_factor * d_bed_z + self.static_bed_factor2 * (d_bed_z **2)) +
                (self.static_bed_temperature_factor * bed_temperature + self.static_bed_temperature_factor2 * (bed_temperature **2)) +
                (self.static_bed_thickness_factor * plate_thickness) +
                self.static_offset_factor
            )
        else:
            target_z_offset = -self.static_e_pressure_nozzle
        target_z_offset = -target_z_offset
        
        return target_z_offset                            
                           

    def _generic_z_probe(self, gcmd, probe_object, x: float, y: float, hop=True) -> float:
        try:
            return self._latest_z_probe(gcmd, probe_object, x, y, hop)
        except:
            return self._stock_z_probe(gcmd, probe_object, x, y, hop)


    def _stock_z_probe(self, gcmd, probe_object, x: float, y: float, hop=True) -> float:
        if hop:
            self._execute_hop_z(self.hop_z)
            self.toolhead.manual_move([x, y, None], self.speed)
        probe_z = probe_object.run_probe(gcmd)[2]
        return probe_z


    def _latest_z_probe(self, gcmd, probe_object, x: float, y: float, hop=True) -> float:
        if hop:
            self._execute_hop_z(self.hop_z)
            self.toolhead.manual_move([x, y, None], self.speed)
        probe_session = probe_object.start_probe_session(gcmd)
        probe_session.run_probe(gcmd)
        probe_z = probe_session.pull_probed_results()[0][2]
        probe_session.end_probe_session()
        return probe_z


    def _set_z_zero(self, z: float):
        current = list(self.toolhead.get_position())
        current[2] = current[2] - z
        self.toolhead.set_position(current)


    def _execute_hop_z(self, z: float):
        self.toolhead.manual_move([None, None, z], self.speed_z_hop)


    def _set_z_offset(self, offset: float):
        gcmd_offset = self.gcode.create_gcode_command("SET_GCODE_OFFSET", "SET_GCODE_OFFSET", {'Z': offset})
        self.gcode_move.cmd_SET_GCODE_OFFSET(gcmd_offset)


    def _save_z_offset(self):
        gcmd_probe_save = self.gcode.create_gcode_command("Z_OFFSET_APPLY_PROBE", "", {})
        self.printer.lookup_object('probe').cmd_Z_OFFSET_APPLY_PROBE(gcmd_probe_save)


    def _create_data_dict(self, 
            d_bed_z: float, 
            d_pressure_z: float,
            nozzle_temperature: int,
            bed_temperature: int, 
            bed_type: str
        ) -> dict:
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


    def _set_temperature(self, temperature: int, blocking: bool=False, bed: bool=True):
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


    def _home(self, axes: str="Z"):
        gcmd_home = self.gcode.create_gcode_command("G28", "G28", {axes: None})
        home = self.printer.lookup_object('homing_override')
        home.cmd_G28(gcmd_home)


    def _calculate_soak_factor(self, current_bed_temperature: int, target_bed_temperature: int) -> float:
        bed_temperature_difference = target_bed_temperature - current_bed_temperature
        if bed_temperature_difference < 0:
            return 0
        bed_soak_factor = min((bed_temperature_difference / (target_bed_temperature - 22)) * 2, 1.0)
        return bed_soak_factor


def load_config(config):
    return DZOS(config)


######################################################################################################################################################################################################
# UTILS
######################################################################################################################################################################################################

def write_data(file_path: str, data: dict):
    try:
        with open(file_path, "w") as file:
            json.dump(data, file, indent=4)
    except:
        print(f"DZOS: Error Data Write")

def append_data(file_path: str, data: dict):
    try:
        if not os.path.exists(file_path):
            write_data(file_path, [])
        loaded_data: list = read_data(file_path)
        loaded_data.append(data)
        with open(file_path, "w") as file:
            json.dump(loaded_data, file, indent=4)
    except:
        print(f"DZOS: Error Data Append")

def read_data(file_path: str) -> dict:  
    try:
        if os.path.exists(file_path):
            with open(file_path, "r") as file:
                data = json.load(file)
            return data
    except:
        print(f"DZOS: Error Data Read")

def delete_file(file_path):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except:
        print(f"DZOS: Error Deleting File")

def backup_file(file_path):
    try:
        if os.path.exists(file_path):
            base, ext = os.path.splitext(file_path)
            backup_path = f"{base}_backup{ext}"
            delete_file(backup_path)
            os.rename(file_path, backup_path)
    except:
        print(f"DZOS: Error Backing Up File")

######################################################################################################################################################################################################
# ML
######################################################################################################################################################################################################

def ml_stat_dict(input_list: list[float]) -> dict:
    return {
        "last_print" : float(input_list[-1]),
        "mean" : float(np.mean(input_list)),
        "std" : float(np.std(input_list)),
        "min" : float(np.min(input_list)),
        "max" : float(np.max(input_list))
    }

def ml_linear_optimize(print_data: dict, plate_thickness_dict: dict, advanced_sample_min: int) -> dict:
    nozzle_list = []
    nozzle_temperature_list = []
    bed_list = []
    bed_temperature_list = []
    bed_thickness_list = []
    z_list = []
    for entry in print_data:
        nozzle: float = entry.get('e_pressure_nozzle_z')
        nozzle_temperature = entry.get('nozzle_temperature')
        bed: float = entry.get('d_bed_z')
        bed_temperature = entry.get('bed_temperature')
        bed_type: str = entry.get('bed_type')
        z_offset: float = entry.get('z_offset')
        if not z_offset:
            continue
        nozzle_list.append(-nozzle)
        nozzle_temperature_list.append(float(nozzle_temperature))
        bed_list.append(bed)
        bed_temperature_list.append(float(bed_temperature))
        bed_thickness_list.append(float(plate_thickness_dict.get(bed_type.lower(), plate_thickness_dict['none'])))
        z_list.append(z_offset)
    samples = len(z_list)
    if samples < 2:
        return

    data = np.column_stack([
        np.array(nozzle_list, dtype=float),
        np.array(nozzle_temperature_list, dtype=float),
        np.array(bed_list, dtype=float),
        np.array(bed_temperature_list, dtype=float),
        np.array(bed_thickness_list, dtype=float),
        np.ones(samples, dtype=float)
    ])
    target = np.array(z_list, dtype=float)

    result = np.linalg.lstsq(data, target, rcond=None)

    if samples >= advanced_sample_min:
        coefficients, processed_data, processed_target = ml_remove_outliers(result, data, target, polynomial=False)
    else:
        coefficients = result[0]
        processed_data = data
        processed_target = target
    nozzle_factor, nozzle_temperature_factor, bed_factor, bed_temperature_factor, bed_thickness_factor, offset = coefficients

    factor_dict = {
        "nozzle_factor": float(nozzle_factor),
        "nozzle_temperature_factor": float(nozzle_temperature_factor),
        "bed_factor": float(bed_factor),
        "bed_temperature_factor": float(bed_temperature_factor),
        "bed_thickness_factor": float(bed_thickness_factor),
        "offset_factor": float(offset),
        "outliers" : int(len(target) - len(processed_target)),
        "samples" : int(samples),
        "statistics" : ml_get_statistics(coefficients, processed_data, processed_target, polynomial=False)
    }
    factor_dict['statistics']['samples'] = int(samples)
    factor_dict['statistics']['outliers'] = int(len(target) - len(processed_target))
    return factor_dict




def ml_polynomial_optimize(print_data: dict, plate_thickness_dict: dict, advanced_sample_min: int) -> dict:
    nozzle_list = []
    nozzle_temperature_list = []
    bed_list = []
    bed_temperature_list = []
    bed_thickness_list = []
    z_list = []
    for entry in print_data:
        nozzle: float = entry.get('e_pressure_nozzle_z')
        nozzle_temperature = entry.get('nozzle_temperature')
        bed: float = entry.get('d_bed_z')
        bed_temperature = entry.get('bed_temperature')
        bed_type: str = entry.get('bed_type')
        z_offset: float = entry.get('z_offset')
        if z_offset is None:
            continue
        nozzle_list.append(-nozzle)
        nozzle_temperature_list.append(float(nozzle_temperature))
        bed_list.append(bed)
        bed_temperature_list.append(float(bed_temperature))
        bed_thickness_list.append(float(plate_thickness_dict.get(bed_type.lower(), plate_thickness_dict['none'])))
        z_list.append(float(z_offset))
    samples = len(z_list)
    if samples < 2:
        return
    
    polynomial_data = np.column_stack([
        np.array(nozzle_list, dtype=float),
        np.array(nozzle_temperature_list, dtype=float),
        np.array(bed_list, dtype=float),
        np.array(bed_list, dtype=float) ** 2,
        np.array(bed_temperature_list, dtype=float),
        np.array(bed_temperature_list, dtype=float) ** 2,
        np.array(bed_thickness_list, dtype=float),
        np.ones(samples, dtype=float)
    ])
    target = np.array(z_list, dtype=float)

    result = np.linalg.lstsq(polynomial_data, target, rcond=None)

    if samples >= advanced_sample_min:
        coefficients, processed_data, processed_target = ml_remove_outliers(result, polynomial_data, target, polynomial=True)
    else:
        coefficients = result[0]
        processed_data = polynomial_data
        processed_target = target

    nozzle_factor = coefficients[0]
    nozzle_temperature_factor = coefficients[1]
    bed_factor = coefficients[2]
    bed_factor2 = coefficients[3]
    bed_temperature_factor = coefficients[4]
    bed_temperature_factor2 = coefficients[5]
    bed_thickness_factor = coefficients[6]
    offset = coefficients[7]

    factor_dict = {
        "nozzle_factor": float(nozzle_factor),
        "nozzle_temperature_factor": float(nozzle_temperature_factor),
        "bed_factor": float(bed_factor),
        "bed_factor2": float(bed_factor2),
        "bed_temperature_factor": float(bed_temperature_factor),
        "bed_temperature_factor2": float(bed_temperature_factor2),
        "bed_thickness_factor": float(bed_thickness_factor),
        "offset_factor": float(offset),
        "statistics": ml_get_statistics(coefficients, processed_data, processed_target, polynomial=True)
    }
    factor_dict['statistics']['samples'] = int(samples)
    factor_dict['statistics']['outliers'] = int(samples - len(processed_target))
    return factor_dict


def ml_remove_outliers(result, data: np.ndarray, target: np.ndarray, polynomial: bool) -> tuple[np.ndarray, np.ndarray]:
    predicted = data.dot(result[0])
    residuals = target - predicted
    median = np.median(residuals)
    mad = np.median(np.abs(residuals - median))
    deviation = 1.5 if polynomial else 3.0
    if mad > 0:
        thresh = deviation * 1.4826 * mad
    else:
        std_res = float(np.std(residuals))
        thresh = deviation * std_res if std_res > 0 else 1e-8
    mask = np.abs(residuals - median) <= thresh
    if mask.sum() < len(mask) and mask.sum() >= 2:
        data_filtered = data[mask]
        target_filtered = target[mask]
        refined_result = np.linalg.lstsq(data_filtered, target_filtered, rcond=None)
        coefficients = refined_result[0]
        processed_data, processed_target = data_filtered, target_filtered
    else:
        processed_data, processed_target = data, target
    return coefficients, processed_data, processed_target


def ml_get_statistics(coefficients, data: np.ndarray, target: np.ndarray, polynomial: bool) -> dict:
    if polynomial:
        nozzle_factor, nozzle_temperature_factor, bed_factor, bed2_factor, bed_temperature_factor, bed_temperature2_factor, bed_thickness_factor, offset = coefficients
    else:
        nozzle_factor, nozzle_temperature_factor, bed_factor, bed_temperature_factor, bed_thickness_factor, offset = coefficients
    predictions = data.dot(coefficients)
    samples = len(target)
    r = float(np.corrcoef(predictions, target)[0, 1])
    if abs(r) < 0.999999:
        z = np.arctanh(r)
        se_z = 1.0 / math.sqrt(samples - 3)
        z_crit = 1.96
        z_low, z_high = z - z_crit * se_z, z + z_crit * se_z
        r_low, r_high = math.tanh(z_low), math.tanh(z_high)
        r2_low, r2_high = r_low ** 2, r_high ** 2
        error = float((r2_high - r2_low) / 2.0)
    else:
        r2_low = r2_high = error = 0.0
    if polynomial:
        predicted_nozzle = data[:, 0] * nozzle_factor
        predicted_nozzle_temperature = data[:, 1] * nozzle_temperature_factor
        predicted_bed = data[:, 2] * bed_factor
        predicted_bed2 = data[:, 3] * bed2_factor
        predicted_bed_temperature = data[:, 4] * bed_temperature_factor
        predicted_bed_temperature2 = data[:, 5] * bed_temperature2_factor
        predicted_bed_thickness = data[:, 6] * bed_thickness_factor
        predicted_offset = data[:, 7] * offset
        statistics = {
            "nozzle": ml_stat_dict(predicted_nozzle),
            "nozzle_temperature": ml_stat_dict(predicted_nozzle_temperature),
            "bed": ml_stat_dict(predicted_bed),
            "bed2": ml_stat_dict(predicted_bed2),
            "bed_temperature": ml_stat_dict(predicted_bed_temperature),
            "bed_temperature2": ml_stat_dict(predicted_bed_temperature2),
            "bed_thickness": ml_stat_dict(predicted_bed_thickness),
            "offset": ml_stat_dict(predicted_offset),
            "error": error,
        }
    else:
        predicted_nozzle = data[:, 0] * nozzle_factor
        predicted_nozzle_temperature = data[:, 1] * nozzle_temperature_factor
        predicted_bed = data[:, 2] * bed_factor
        predicted_bed_temperature = data[:, 3] * bed_temperature_factor
        predicted_bed_thickness = data[:, 4] * bed_thickness_factor
        predicted_offset = data[:, 5] * offset
        statistics = {
            "nozzle": ml_stat_dict(predicted_nozzle),
            "nozzle_temperature": ml_stat_dict(predicted_nozzle_temperature),
            "bed": ml_stat_dict(predicted_bed),
            "bed_temperature": ml_stat_dict(predicted_bed_temperature),
            "bed_thickness": ml_stat_dict(predicted_bed_thickness),
            "offset": ml_stat_dict(predicted_offset),
            "error": error,
        }
    return statistics




