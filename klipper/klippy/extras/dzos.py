######################################################################################################################################################################################################
# DZOS: DYNAMIC Z OFFSET AND SOAK
# AUTHOR: MAKER KIT LABORATORIES
# VERSION: 0.5.00
######################################################################################################################################################################################################
import json
import os
import numpy as np
import time
import threading



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

        self.eddy = self.config.getboolean('eddy', default=False)
        self.pressure_sensor = self.config.getboolean('pressure_sensor', default=False)
        self.sensor_name = self.config.get('sensor_name', default='none')
        
        self.polynomial = self.config.getboolean('polynomial', default=False)
        self.polynomial_sample_min = self.config.getint('polynomial_sample_min', default=20)
        self.outlier_sample_min = self.config.getint('outlier_sample_min', default=20)
        self.outlier_deviation = self.config.getfloat('outlier_deviation', default=3.0)
        self.soak_multiplier = self.config.getfloat('soak_multiplier', default=1.0)
        
        self.bed_type_dict = {
            "none" : "none",
            "cool plate" : "cp",
            "high temp plate" : "ht",
            "engineering plate" : "eng",
            "textured pei plate" : "pei",
            "textured cool plate" : "tcp",
            "supertack plate" : "st",
        }

        self.soak_xyz = list(self.config.getfloatlist("soak_xyz", count=3, default=[330, 20, 1]))

        probe_config = self.config.getsection('probe')
        probe_offset_x = probe_config.getfloat('x_offset')
        probe_offset_y = probe_config.getfloat('y_offset')
        self.probe_offset_z = probe_config.getfloat('z_offset')
        
        self.bed_xy = list(self.config.getfloatlist("bed_xy", count=2, default=[191, 165]))
        self.pressure_nozzle_xy = list(self.config.getfloatlist("pressure_xy", count=2, default=[289, 361]))
        self.pressure_xy = [self.pressure_nozzle_xy[0] - probe_offset_x, self.pressure_nozzle_xy[1] - probe_offset_y]

        self.gcode = self.printer.lookup_object('gcode')
        self.gcode_move = self.printer.lookup_object('gcode_move')

        print_data = read_data(PRINT_DATA_FILEPATH)
        if self.polynomial and print_data:
            self.polynomial = True if len(print_data) > self.polynomial_sample_min else False                    

        self.gcode.register_command("DZOS_Z_OFFSET", self.cmd_DZOS_Z_OFFSET)
        self.gcode.register_command("DZOS_Z_CALCULATE", self.cmd_DZOS_Z_CALCULATE)
        self.gcode.register_command("DZOS_Z_CAPTURE", self.cmd_DZOS_Z_CAPTURE)


    def cmd_DZOS_Z_OFFSET(self, gcmd):
        self._init_printer_objects()
        cache_static = int(gcmd.get("CACHE_STATIC", 0))
        input_bed_type = str(gcmd.get("BEDTYPE", "None"))
        input_bed_temperature = float(gcmd.get("BEDTEMP", 0))
        input_nozzle_temperature = float(gcmd.get("NOZZLETEMP", 0))
        if not input_bed_temperature or not input_nozzle_temperature:
            gcode_temperature = self._read_gcode_temperature()
            if not input_nozzle_temperature:
                input_nozzle_temperature = gcode_temperature.get("nozzle_temperature")
            if not input_bed_temperature:
                input_bed_temperature = gcode_temperature.get("bed_temperature")
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
        if not os.path.exists(STATIC_FILEPATH) or self.pressure_xy == [0,0]:
            gcmd.respond_info("DZOS: No Static Data Found!")
            self._display_msg("DZOS: No Static!")
            return
        gcmd.respond_info(f"DZOS: Bed Type: {input_bed_type}")
        self._display_msg(f"DZOS: Bed {input_bed_type}")
        if self.eddy:
            self._heat_soak_eddy(gcmd, input_bed_temperature, force_soak_time)
        else:
            self._heat_soak(gcmd, current_bed_temperature, input_bed_temperature, force_soak_time)
        self._calculate_dynamic_offset(
            gcmd, 
            input_nozzle_temperature,
            input_bed_temperature, 
            input_bed_type,
            self.polynomial,
        )
        self._print_thread = self._create_print_thread(gcmd)


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
            factor_dict = ml_polynomial_optimize(print_data, self.bed_type_dict, self.outlier_sample_min, self.outlier_deviation) 
        else:
            factor_dict = ml_linear_optimize(print_data, self.bed_type_dict, self.outlier_sample_min, self.outlier_deviation)
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
            static_data["bed_type_factors"] = factor_dict["bed_type_factors"] 
            static_data["sensor_temperature_factor"] = factor_dict["sensor_temperature_factor"]
            if self.polynomial:
                static_data["sensor_temperature_factor2"] = factor_dict["sensor_temperature_factor2"] 
            static_data["offset_factor"] = factor_dict["offset_factor"]
            static_data["statistics"] = factor_dict["statistics"]
            write_data(STATIC_FILEPATH, static_data)
            if statistics:
                gcmd.respond_info(f"DZOS: Type: {'Polynomial' if self.polynomial else 'Linear'}")
                gcmd.respond_info(f"DZOS: Samples: {factor_dict['statistics']['samples']}")
                gcmd.respond_info(f"DZOS: Outliers: {factor_dict['statistics']['outliers']} [{','.join(factor_dict['statistics']['outlier_indices'])}]")
                gcmd.respond_info(f"DZOS: Error: ±{factor_dict['statistics']['error']:.3f}")
                gcmd.respond_info(f"DZOS: Nozzle Z: {factor_dict['statistics']['nozzle']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Nozzle Temperature: {factor_dict['statistics']['nozzle_temperature']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Z: {factor_dict['statistics']['bed']['mean']:.3f}")
                if self.polynomial:
                    gcmd.respond_info(f"DZOS: Bed² Z: {factor_dict['statistics']['bed2']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Temperature: {factor_dict['statistics']['bed_temperature']['mean']:.3f}")
                if self.polynomial:
                    gcmd.respond_info(f"DZOS: Bed Temperature²: {factor_dict['statistics']['bed_temperature2']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Type Default: {factor_dict['statistics']['bed_type_factor_none']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Type Cool Plate: {factor_dict['statistics']['bed_type_factor_cp']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Type High Temp Plate: {factor_dict['statistics']['bed_type_factor_ht']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Type Engineering Plate: {factor_dict['statistics']['bed_type_factor_eng']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Type Textured PEI Plate: {factor_dict['statistics']['bed_type_factor_pei']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Type Textured Cool Plate: {factor_dict['statistics']['bed_type_factor_tcp']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Bed Type Supertack Plate: {factor_dict['statistics']['bed_type_factor_st']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Sensor Temperature: {factor_dict['statistics']['sensor_temperature']['mean']:.3f}")
                if self.polynomial:
                    gcmd.respond_info(f"DZOS: Sensor Temperature²: {factor_dict['statistics']['sensor_temperature2']['mean']:.3f}")
                gcmd.respond_info(f"DZOS: Offset: {factor_dict['statistics']['offset']['mean']:.3f}")
            else:
                self._set_z_offset(-self.probe_offset_z)
                gcmd.respond_info("DZOS: Complete!")
        else:
            gcmd.respond_info("DZOS: Not Enough Data!")
            self._display_msg("DZOS: Data!")
        

    def cmd_DZOS_Z_CAPTURE(self, gcmd):
        self._init_printer_objects()
        gcmd_clear = self.gcode.create_gcode_command("BED_MESH_CLEAR", "BED_MESH_CLEAR", {})
        self.bed_mesh.cmd_BED_MESH_CLEAR(gcmd_clear)
        toolhead = self.printer.lookup_object('toolhead')
        z_position = toolhead.get_position()[2]
        gcode_position = self.gcode_move._get_gcode_position()
        z = gcode_position[2]
        z_offset = z - (z_position - self.probe_offset_z)
        gcmd.respond_info(f"DZOS: Captured Z: {-z_offset:.3f}")
        print_data: list[dict] = read_data(PRINT_DATA_FILEPATH)
        if not print_data:
            return
        if not print_data[-1].get("z_offset", None):
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
        self.stats = self.printer.lookup_object('print_stats')
        self.gcode_macro = self.printer.lookup_object('gcode_macro')
        self.bed_mesh = self.printer.lookup_object('bed_mesh')


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
        self.static_bed_type_factors = static_data.get("bed_type_factors", {})
        self.static_offset_factor = static_data.get("offset_factor", 0)
        self.static_sensor_temperature_factor = static_data.get("sensor_temperature_factor", 0)
        self.static_sensor_temperature_factor2 = static_data.get("sensor_temperature_factor2", 0)


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
        
        event_time = self.printer.get_reactor().monotonic()
        if self.eddy:
            sensor_status = self.printer.lookup_object(f'temperature_probe {self.sensor_name}').get_status(event_time)
            sensor_temperature = sensor_status.get('temperature')
        elif self.sensor_name != 'none':
            sensor_status = self.printer.lookup_object(f'temperature_sensor {self.sensor_name}').get_status(event_time)
            sensor_temperature = sensor_status.get('temperature')

        if polynomial:
            z_offset = self._calculate_z_offset_polynomial(d_bed_z, nozzle_temperature, bed_temperature, bed_type, sensor_temperature)
        else:   
            z_offset = self._calculate_z_offset(d_bed_z, nozzle_temperature, bed_temperature, bed_type, sensor_temperature)
        print_data = self._create_data_dict(d_bed_z, d_pressure_z, nozzle_temperature, bed_temperature, bed_type, sensor_temperature)
        append_data(PRINT_DATA_FILEPATH, print_data)

        gcmd.respond_info("DZOS: Z Offset: %.3f" % z_offset)
        self._display_msg(f"DZOS: {z_offset:.3f}")
        
        self._set_z_offset(z_offset + self.probe_offset_z)

    def _calculate_mesh_bounds(self, gcmd):
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
        return print_max_center_size

    def _heat_soak(self, gcmd, current_bed_temperature: float, bed_temperature: int, force_soak_time: int=0):
        if force_soak_time > 0:
            duration = force_soak_time
        else:
            print_max_center_size = self._calculate_mesh_bounds(gcmd)
            gcmd.respond_info("DZOS: Center Offset: %.3fmm" % print_max_center_size)
            soak_factor = self._calculate_soak_factor(current_bed_temperature, bed_temperature) * self.soak_multiplier
            gcmd.respond_info("DZOS: Soak Factor: %.3f" % soak_factor)
            duration =  int(max(((print_max_center_size / 0.085) - 300) * soak_factor, 120))
        iteration = -1
        nozzle_heater_enabled = False
        if bed_temperature:
            self._set_temperature(bed_temperature, blocking=True)
        self._quad_gantry_level(check=True)
        if not force_soak_time:
            self.toolhead.manual_move([self.soak_xyz[0], self.soak_xyz[1], None], self.speed)
            self.toolhead.manual_move([None, None, self.soak_xyz[2]], self.speed_z_hop)
        gcmd.respond_info("DZOS: Soak Time: %is" % duration)
        while iteration < duration:
            remaining = duration - iteration
            self._display_msg(f"DZOS:{int(remaining)}")
            if not nozzle_heater_enabled and remaining <= 120:
                self._set_temperature(120, blocking=False, bed=False)
                nozzle_heater_enabled = True
            self.toolhead.dwell(1)
            iteration += 1
        return duration


    def _heat_soak_eddy(self, gcmd, bed_temperature: int, force_soak_time: int=0):
        if force_soak_time > 0:
            duration = force_soak_time
        else:
            duration =  120 * self.soak_multiplier
        iteration = -1
        nozzle_heater_enabled = False
        if bed_temperature:
            max_temperature = self.config.getsection("heater_bed").getint("max_temp", default=105)
            soak_temperature = min(bed_temperature + 15, max_temperature)
            self._set_temperature(soak_temperature, blocking=True)
            self._set_temperature(bed_temperature, blocking=True)
        self._quad_gantry_level(check=True)
        if not force_soak_time:
            self.toolhead.manual_move([self.soak_xyz[0], self.soak_xyz[1], None], self.speed)
            self.toolhead.manual_move([None, None, self.soak_xyz[2]], self.speed_z_hop)
        gcmd.respond_info("DZOS: Soak Time: %is" % duration)
        while iteration < duration:
            remaining = duration - iteration
            self._display_msg(f"DZOS:{int(remaining)}")
            if not nozzle_heater_enabled and remaining <= 120:
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
            bed_type: str,
            sensor_temperature: float
        ) -> float:
        self._init_static_data() 
        if self.static_bed_factor:
            bed_type_key = self.bed_type_dict[bed_type.lower()]
            bed_type_factor = self.static_bed_type_factors[bed_type_key]
            target_z_offset = (
                (self.static_nozzle_factor * -self.static_e_pressure_nozzle) +
                (self.static_bed_factor * d_bed_z) + 
                (self.static_bed_temperature_factor * bed_temperature) +
                bed_type_factor + 
                (self.static_nozzle_temperature_factor * nozzle_temperature) +
                (self.static_sensor_temperature_factor * sensor_temperature) +
                self.static_offset_factor
            )
            target_z_offset = -target_z_offset
        else:
            target_z_offset = 0.001
        return target_z_offset


    def _calculate_z_offset_polynomial(self,
            d_bed_z: float,
            nozzle_temperature: int,            
            bed_temperature: int, 
            bed_type: str,
            sensor_temperature: float,
        ) -> float:
        self._init_static_data()        
        if self.static_bed_factor:
            bed_type_key = self.bed_type_dict[bed_type.lower()]
            bed_type_factor = self.static_bed_type_factors[bed_type_key]
            target_z_offset = (
                (self.static_nozzle_factor * -self.static_e_pressure_nozzle) +
                (self.static_nozzle_temperature_factor * nozzle_temperature) +
                (self.static_bed_factor * d_bed_z + self.static_bed_factor2 * (d_bed_z **2)) +
                (self.static_bed_temperature_factor * bed_temperature + self.static_bed_temperature_factor2 * (bed_temperature **2)) +
                bed_type_factor +
                (self.static_sensor_temperature_factor * sensor_temperature + self.static_sensor_temperature_factor2 * (sensor_temperature **2)) +
                self.static_offset_factor
            )
            target_z_offset = -(target_z_offset)
        else:
            target_z_offset = 0.001
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
            bed_type: str,
            sensor_temperature: float,
        ) -> dict:
        self._init_static_data()
        data_dict = {
            "e_pressure_nozzle_z": self.static_e_pressure_nozzle,
            "d_bed_z": d_bed_z,
            "d_pressure_z": d_pressure_z,
            "nozzle_temperature": nozzle_temperature,
            "bed_temperature": bed_temperature,
            "sensor_temperature": sensor_temperature,
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


    def _quad_gantry_level(self, check=False):
        gcmd_qgl = self.gcode.create_gcode_command("QUAD_GANTRY_LEVEL", "QUAD_GANTRY_LEVEL", {})
        qgl = self.printer.lookup_object('quad_gantry_level')
        qgl_status = qgl.get_status(self.printer.get_reactor().monotonic()).get("applied", False)
        if not check or (check and not qgl_status):
            qgl.cmd_QUAD_GANTRY_LEVEL(gcmd_qgl)


    def _home(self, axes: str="Z"):
        gcmd_home = self.gcode.create_gcode_command("G28", "G28", {axes: None})
        home = self.printer.lookup_object('homing_override')
        home.cmd_G28(gcmd_home)


    def _calculate_soak_factor(self, current_bed_temperature: int, target_bed_temperature: int) -> float:
        bed_temperature_difference = target_bed_temperature - current_bed_temperature
        if bed_temperature_difference < 0:
            return 0
        bed_soak_factor = min((bed_temperature_difference / (target_bed_temperature - 22)) * 3.0, 1.0)
        return bed_soak_factor


    def _create_print_thread(self, gcmd):
        print_thread = threading.Thread(target=self._print_end_check, args=(gcmd,))
        print_thread.start()
        return print_thread
    

    def _print_end_check(self, gcmd):
        printing = True
        while printing:
            event_time = self.printer.get_reactor().monotonic()
            status_dict = self.stats.get_status(event_time)
            state: str = status_dict["state"]
            if state.lower() != "printing":
                printing = False
                gcmd.respond_info("DZOS: Print End!")
            else:
                time.sleep(5)
        if state.lower() == "complete":
            self.cmd_DZOS_Z_CAPTURE(gcmd)
        self._print_thread.join()


    def _read_gcode_temperature(self) -> dict:
        file_path = self._get_active_gcode_file()
        nozzle_command_list = get_gcode_command(file_path, "M109")
        bed_command_list = get_gcode_command(file_path, "M190")
        nozzle_temperature = 0
        bed_temperature = 0
        if nozzle_command_list:
            nozzle_temperature = get_command_temperature(nozzle_command_list[0])
        if bed_command_list:
            bed_temperature = get_command_temperature(bed_command_list[0])
        return {
            "nozzle_temperature": nozzle_temperature,
            "bed_temperature": bed_temperature
        }


    def _get_active_gcode_file(self) -> str:
        virtual_sd = self.printer.lookup_object('virtual_sdcard')
        virtual_sd_stats = virtual_sd.get_status(self.printer.get_reactor().monotonic())
        file_path = virtual_sd_stats.get('file_path', None)
        return file_path


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


def get_gcode_command(file_path: str, command: str) -> list:
    command_list = []
    try:
        with open(file_path, "r") as file:
            for line in file:
                line = line.strip()
                if line.startswith(command):
                    command_list.append(line)
    except:
        print(f"DZOS: Error Reading Gcode File")
    return command_list


def get_command_temperature(command: str) -> int:
    parts = command.split()
    for part in parts:
        if part.startswith("S"):
            temperature_str = part[1:]
            temperature = int(temperature_str.split(";")[0])
            return temperature


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


def ml_linear_optimize(print_data: dict, bed_type_dict: dict, outlier_sample_min: int, outlier_deviation: float) -> dict:
    nozzle_list = []
    nozzle_temperature_list = []
    bed_list = []
    bed_temperature_list = []
    sensor_temperature_list = []
    bed_type_encoded_list = []
    z_list = []

    bed_type_indices = {bed : index for index, bed in enumerate(bed_type_dict.keys())}

    for entry in print_data:
        nozzle: float = entry.get('e_pressure_nozzle_z')
        nozzle_temperature = entry.get('nozzle_temperature')
        bed: float = entry.get('d_bed_z')
        bed_temperature = entry.get('bed_temperature')
        bed_type: str = entry.get('bed_type')
        sensor_temperature = entry.get('sensor_temperature', 0.0)
        z_offset: float = entry.get('z_offset')
        if not z_offset:
            continue
        nozzle_list.append(-nozzle)
        nozzle_temperature_list.append(float(nozzle_temperature))
        bed_list.append(bed)
        bed_temperature_list.append(float(bed_temperature))
        one_hot = [0.0] * len(bed_type_dict)
        one_hot[bed_type_indices[bed_type.lower()]] = 1.0
        bed_type_encoded_list.append(one_hot)        
        sensor_temperature_list.append(float(sensor_temperature))
        z_list.append(z_offset)
        

        
    samples = len(z_list)
    if samples < 2:
        return
    
    data = np.column_stack([
        np.array(nozzle_list, dtype=float),
        np.array(nozzle_temperature_list, dtype=float),
        np.array(bed_list, dtype=float),
        np.array(bed_temperature_list, dtype=float),
        np.array(bed_type_encoded_list, dtype=float),
        np.array(sensor_temperature_list, dtype=float),
        np.ones(samples, dtype=float)
    ])
    target = np.array(z_list, dtype=float)

    result = np.linalg.lstsq(data, target, rcond=None)

    if samples >= outlier_sample_min:
        coefficients, processed_data, processed_target, outlier_indices = ml_remove_outliers(result, data, target, outlier_deviation)
    else:
        coefficients = result[0]
        processed_data = data
        processed_target = target
        outlier_indices = []
    
    nozzle_factor = coefficients[0]
    nozzle_temperature_factor = coefficients[1]
    bed_factor = coefficients[2]
    bed_temperature_factor = coefficients[3]
    bed_type_factors = {
        "none" : float(coefficients[4]),
        "cp": float(coefficients[5]),
        "ht": float(coefficients[6]),
        "eng": float(coefficients[7]),
        "pei": float(coefficients[8]),
        "tcp": float(coefficients[9]),
        "st": float(coefficients[10])
    }
    sensor_temperature_factor = coefficients[11]
    offset = coefficients[12]
    factor_dict = {
        "nozzle_factor": float(nozzle_factor),
        "nozzle_temperature_factor": float(nozzle_temperature_factor),
        "bed_factor": float(bed_factor),
        "bed_temperature_factor": float(bed_temperature_factor),
        "bed_type_factors": bed_type_factors,
        "sensor_temperature_factor": float(sensor_temperature_factor),
        "offset_factor": float(offset),
        "statistics" : ml_get_statistics(coefficients, processed_data, processed_target, polynomial=False)
    }
    factor_dict['statistics']['samples'] = int(samples)
    factor_dict['statistics']['outliers'] = int(len(target) - len(processed_target))
    factor_dict['statistics']['outlier_indices'] = outlier_indices
    return factor_dict


def ml_polynomial_optimize(print_data: dict, bed_type_dict: dict, outlier_sample_min: int, outlier_deviation: float) -> dict:
    nozzle_list = []
    nozzle_temperature_list = []
    bed_list = []
    bed_temperature_list = []
    sensor_temperature_list = []
    bed_type_encoded_list = []
    z_list = []

    bed_type_indices = {bed : index for index, bed in enumerate(bed_type_dict.keys())}
    
    for entry in print_data:
        nozzle: float = entry.get('e_pressure_nozzle_z')
        nozzle_temperature = entry.get('nozzle_temperature')
        bed: float = entry.get('d_bed_z')
        bed_temperature = entry.get('bed_temperature')
        bed_type: str = entry.get('bed_type')
        sensor_temperature = entry.get('sensor_temperature', 0.0)
        z_offset: float = entry.get('z_offset')
        if z_offset is None:
            continue
        nozzle_list.append(-nozzle)
        nozzle_temperature_list.append(float(nozzle_temperature))
        bed_list.append(bed)
        bed_temperature_list.append(float(bed_temperature))
       
        one_hot = [0.0] * len(bed_type_dict)
        one_hot[bed_type_indices[bed_type.lower()]] = 1.0
        bed_type_encoded_list.append(one_hot)

        sensor_temperature_list.append(float(sensor_temperature))
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
        np.array(bed_type_encoded_list, dtype=float),
        np.array(sensor_temperature_list, dtype=float),
        np.array(sensor_temperature_list, dtype=float) ** 2,
        np.ones(samples, dtype=float)
    ])
    target = np.array(z_list, dtype=float)

    result = np.linalg.lstsq(polynomial_data, target, rcond=None)

    if samples >= outlier_sample_min:
        coefficients, processed_data, processed_target, outlier_indices = ml_remove_outliers(result, polynomial_data, target, outlier_deviation)
    else:
        coefficients = result[0]
        processed_data = polynomial_data
        processed_target = target
        outlier_indices = []

    nozzle_factor = coefficients[0]
    nozzle_temperature_factor = coefficients[1]
    bed_factor = coefficients[2]
    bed_factor2 = coefficients[3]
    bed_temperature_factor = coefficients[4]
    bed_temperature_factor2 = coefficients[5]
    bed_type_factors = {
        "none" : float(coefficients[6]),
        "cp": float(coefficients[7]),
        "ht": float(coefficients[8]),
        "eng": float(coefficients[9]),
        "pei": float(coefficients[10]),
        "tcp": float(coefficients[11]),
        "st": float(coefficients[12])
    }
    sensor_temperature_factor = coefficients[13]
    sensor_temperature_factor2 = coefficients[14]
    offset = coefficients[15]

    factor_dict = {
        "nozzle_factor": float(nozzle_factor),
        "nozzle_temperature_factor": float(nozzle_temperature_factor),
        "bed_factor": float(bed_factor),
        "bed_factor2": float(bed_factor2),
        "bed_temperature_factor": float(bed_temperature_factor),
        "bed_temperature_factor2": float(bed_temperature_factor2),
        "bed_type_factors": bed_type_factors,
        "sensor_temperature_factor": float(sensor_temperature_factor),
        "sensor_temperature_factor2": float(sensor_temperature_factor2),
        "offset_factor": float(offset),
        "statistics": ml_get_statistics(coefficients, processed_data, processed_target, polynomial=True)
    }
    factor_dict['statistics']['samples'] = int(samples)
    factor_dict['statistics']['outliers'] = int(samples - len(processed_target))
    factor_dict['statistics']['outlier_indices'] = outlier_indices
    return factor_dict


def ml_remove_outliers(result, data: np.ndarray, target: np.ndarray, outlier_deviation: float) -> tuple:
    predicted = data.dot(result[0])
    residuals = target - predicted
    median = np.median(residuals)
    mad = np.median(np.abs(residuals - median))
    if mad > 0:
        thresh = outlier_deviation * 1.4826 * mad
    else:
        std_res = float(np.std(residuals))
        thresh = outlier_deviation * std_res if std_res > 0 else 1e-8
    mask = np.abs(residuals - median) <= thresh
    if mask.sum() < len(mask) and mask.sum() >= 2:
        data_filtered = data[mask]
        target_filtered = target[mask]
        refined_result = np.linalg.lstsq(data_filtered, target_filtered, rcond=None)
        coefficients = refined_result[0]
        processed_data, processed_target = data_filtered, target_filtered
    else:
        processed_data, processed_target = data, target
        coefficients = result[0]
    outlier_indices = np.where(~mask)[0]
    outlier_indices_str = [str(outlier) for outlier in outlier_indices]
    return coefficients, processed_data, processed_target, outlier_indices_str


def ml_get_statistics(coefficients, data: np.ndarray, target: np.ndarray, polynomial: bool) -> dict:
    if polynomial:
        (
            nozzle_factor, 
            nozzle_temperature_factor, 
            bed_factor, bed2_factor, 
            bed_temperature_factor, 
            bed_temperature2_factor, 
            bed_type_factor_none,
            bed_type_factor_cp,
            bed_type_factor_ht,
            bed_type_factor_eng,
            bed_type_factor_pei,
            bed_type_factor_tcp,
            bed_type_factor_st,
            sensor_temperature_factor, 
            sensor_temperature_factor2, 
            offset
        ) = coefficients
    else:
        (
            nozzle_factor, 
            nozzle_temperature_factor, 
            bed_factor, 
            bed_temperature_factor, 
            bed_type_factor_none,
            bed_type_factor_cp,
            bed_type_factor_ht,
            bed_type_factor_eng,
            bed_type_factor_pei,
            bed_type_factor_tcp,
            bed_type_factor_st,
            sensor_temperature_factor, 
            offset 
        ) = coefficients
    predictions = data.dot(coefficients)
    error = float(np.mean(np.abs(predictions - target)))
    if polynomial:
        predicted_nozzle = data[:, 0] * nozzle_factor
        predicted_nozzle_temperature = data[:, 1] * nozzle_temperature_factor
        predicted_bed = data[:, 2] * bed_factor
        predicted_bed2 = data[:, 3] * bed2_factor
        predicted_bed_temperature = data[:, 4] * bed_temperature_factor
        predicted_bed_temperature2 = data[:, 5] * bed_temperature2_factor
        predicted_bed_none_factor = data[:, 6] * bed_type_factor_none
        predicted_bed_cp_factor = data[:, 7] * bed_type_factor_cp
        predicted_bed_ht_factor = data[:, 8] * bed_type_factor_ht
        predicted_bed_eng_factor = data[:, 9] * bed_type_factor_eng
        predicted_bed_pei_factor = data[:, 10] * bed_type_factor_pei
        predicted_bed_tcp_factor = data[:, 11] * bed_type_factor_tcp
        predicted_bed_st_factor = data[:, 12] * bed_type_factor_st
        predicted_sensor_temperature = data[:, 13] * sensor_temperature_factor
        predicted_sensor_temperature2 = data[:, 14] * sensor_temperature_factor2
        predicted_offset = data[:, 15] * offset
        statistics = {
            "nozzle": ml_stat_dict(predicted_nozzle),
            "nozzle_temperature": ml_stat_dict(predicted_nozzle_temperature),
            "bed": ml_stat_dict(predicted_bed),
            "bed2": ml_stat_dict(predicted_bed2),
            "bed_temperature": ml_stat_dict(predicted_bed_temperature),
            "bed_temperature2": ml_stat_dict(predicted_bed_temperature2),
            "bed_type_factor_none": ml_stat_dict(predicted_bed_none_factor),
            "bed_type_factor_cp": ml_stat_dict(predicted_bed_cp_factor),
            "bed_type_factor_ht": ml_stat_dict(predicted_bed_ht_factor),
            "bed_type_factor_eng": ml_stat_dict(predicted_bed_eng_factor),
            "bed_type_factor_pei": ml_stat_dict(predicted_bed_pei_factor),
            "bed_type_factor_tcp": ml_stat_dict(predicted_bed_tcp_factor),
            "bed_type_factor_st": ml_stat_dict(predicted_bed_st_factor),
            "sensor_temperature": ml_stat_dict(predicted_sensor_temperature),
            "sensor_temperature2": ml_stat_dict(predicted_sensor_temperature2),
            "offset": ml_stat_dict(predicted_offset),
            "error": error,
        }
    else:
        predicted_nozzle = data[:, 0] * nozzle_factor
        predicted_nozzle_temperature = data[:, 1] * nozzle_temperature_factor
        predicted_bed = data[:, 2] * bed_factor
        predicted_bed_temperature = data[:, 3] * bed_temperature_factor
        predicted_bed_none_factor = data[:, 4] * bed_type_factor_none
        predicted_bed_cp_factor = data[:, 5] * bed_type_factor_cp
        predicted_bed_ht_factor = data[:, 6] * bed_type_factor_ht
        predicted_bed_eng_factor = data[:, 7] * bed_type_factor_eng
        predicted_bed_pei_factor = data[:, 8] * bed_type_factor_pei
        predicted_bed_tcp_factor = data[:, 9] * bed_type_factor_tcp
        predicted_bed_st_factor = data[:, 10] * bed_type_factor_st
        predicted_sensor_temperature = data[:, 11] * sensor_temperature_factor
        predicted_offset = data[:, 12] * offset
        statistics = {
            "nozzle": ml_stat_dict(predicted_nozzle),
            "nozzle_temperature": ml_stat_dict(predicted_nozzle_temperature),
            "bed": ml_stat_dict(predicted_bed),
            "bed_temperature": ml_stat_dict(predicted_bed_temperature),
            "bed_type_factor_none": ml_stat_dict(predicted_bed_none_factor),
            "bed_type_factor_cp": ml_stat_dict(predicted_bed_cp_factor),
            "bed_type_factor_ht": ml_stat_dict(predicted_bed_ht_factor),
            "bed_type_factor_eng": ml_stat_dict(predicted_bed_eng_factor),
            "bed_type_factor_pei": ml_stat_dict(predicted_bed_pei_factor),
            "bed_type_factor_tcp": ml_stat_dict(predicted_bed_tcp_factor),
            "bed_type_factor_st": ml_stat_dict(predicted_bed_st_factor),
            "sensor_temperature": ml_stat_dict(predicted_sensor_temperature),
            "offset": ml_stat_dict(predicted_offset),
            "error": error,
        }
    return statistics