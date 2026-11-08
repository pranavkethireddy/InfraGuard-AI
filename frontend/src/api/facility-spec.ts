import type { FaultKind } from './fleet-types';

// Exact compatibility from approved PR80 simulator FACILITY (read-only reference).
export const facilityFaults: Record<string, readonly FaultKind[]> = {
  "ups": [
    "ups_battery_fade",
    "ups_on_battery"
  ],
  "generator": [
    "gen_start_battery",
    "gen_low_fuel"
  ],
  "ats": [
    "ats_transfer_fail",
    "ats_utility_sag"
  ],
  "pdu": [
    "pdu_overload",
    "pdu_imbalance"
  ],
  "chiller": [
    "chiller_trip",
    "chiller_low_flow"
  ],
  "cdu": [
    "cdu_leak",
    "cdu_pump_failure"
  ],
  "env_sensor": [
    "env_water_leak",
    "env_high_humidity"
  ],
  "network_switch": [
    "switch_optic_degraded",
    "switch_link_down"
  ],
  "smoke_detector": [
    "smoke_alarm"
  ],
  "fire_suppression": [
    "suppression_pressure_loss",
    "suppression_disarmed"
  ],
  "access_control": [
    "door_forced",
    "badge_reader_failure"
  ]
};

// Native metric names from FACILITY/layout; no L/s→L/min or kPa→bar conversion.
const units: Record<string, string> = {
  "runtime_min": "min",
  "load_pct": "%",
  "battery_charge_pct": "%",
  "battery_temp_c": "°C",
  "input_voltage_v": "V",
  "output_voltage_v": "V",
  "on_battery": "binary 0/1",
  "fuel_pct": "%",
  "start_battery_v": "V",
  "coolant_temp_c": "°C",
  "last_test_ok": "binary 0/1",
  "running": "binary 0/1",
  "output_kw": "kW",
  "utility_voltage_v": "V",
  "source": "binary 0/1",
  "transfer_ok": "binary 0/1",
  "transfer_time_ms": "ms",
  "phase_a_amps": "A",
  "phase_b_amps": "A",
  "phase_c_amps": "A",
  "breaker_rating_amps": "A",
  "max_phase_pct": "%",
  "imbalance_pct": "%",
  "power_kw": "kW",
  "supply_water_c": "°C",
  "return_water_c": "°C",
  "compressor_amps": "A",
  "flow_lps": "L/s",
  "pressure_kpa": "kPa",
  "coolant_supply_c": "°C",
  "coolant_return_c": "°C",
  "leak_detected": "binary 0/1",
  "temperature_c": "°C",
  "humidity_pct": "%",
  "dew_point_c": "°C",
  "water_under_floor": "binary 0/1",
  "cpu_pct": "%",
  "optic_rx_dbm": "dBm",
  "port_errors_per_min": "count/min",
  "links_down": "count",
  "packet_loss_pct": "%",
  "obscuration_pct_per_m": "%/m",
  "alarm_level": "count",
  "agent_pressure_pct": "%",
  "armed": "binary 0/1",
  "door_held_open_s": "s",
  "badge_failures_per_min": "count/min",
  "forced_open": "binary 0/1"
};
export const facilityMetricUnit = (field: string): string | undefined => units[field];
export const equipmentPath = (id: string, site = 'datacenter') => `/fleet/equipment/${encodeURIComponent(id)}?site=${encodeURIComponent(site)}`;
