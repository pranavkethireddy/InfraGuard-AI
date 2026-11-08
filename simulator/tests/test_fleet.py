import random
import unittest

from simulator import fleet

TYPES = ("cooling_unit", "storage_drive", "industrial_machine", "asic_miner", "gpu_server")


class FleetTests(unittest.TestCase):
    def test_profiles_and_streams_are_repeatable_per_machine(self):
        for t in TYPES:
            self.assertEqual(fleet.profile(t, "a-1", 7), fleet.profile(t, "a-1", 7))
            self.assertNotEqual(fleet.profile(t, "a-1", 7), fleet.profile(t, "a-2", 7))
        a = [fleet.rng_for(7, "x").random() for _ in range(3)]
        self.assertEqual(a, [fleet.rng_for(7, "x").random() for _ in range(3)])

    def test_global_random_state_untouched(self):
        state = random.getstate()
        p = fleet.profile("cooling_unit", "c", 1)
        fleet.sample("cooling_unit", p, 3, fleet.rng_for(1, "c"))
        self.assertEqual(state, random.getstate())

    def test_healthy_cooling_stays_below_rule_threshold_and_fault_exceeds_it(self):
        for i in range(30):
            p = fleet.profile("cooling_unit", f"c{i}", 42)
            r = fleet.rng_for(42, f"c{i}")
            self.assertTrue(all(fleet.sample("cooling_unit", p, k, r)["temperature_c"] < 30 for k in range(200)))
            self.assertGreater(fleet.sample("cooling_unit", p, 0, r, 1.0)["temperature_c"], 33)

    def test_drive_fault_raises_smart_counts(self):
        p = fleet.profile("storage_drive", "d", 42)
        r = fleet.rng_for(42, "d")
        healthy, bad = fleet.sample("storage_drive", p, 0, r), fleet.sample("storage_drive", p, 0, r, 1.0)
        self.assertEqual(healthy["pending_sectors"], 0)
        self.assertGreaterEqual(bad["reallocated_sectors"], 5000)
        self.assertEqual(set(healthy), set(bad))

    def test_machine_sample_matches_ai4i_inputs(self):
        p = fleet.profile("industrial_machine", "m", 42)
        s = fleet.sample("industrial_machine", p, 5, fleet.rng_for(42, "m"))
        self.assertEqual(set(s), {"type", "air_temperature_k", "process_temperature_k", "rotational_speed_rpm",
                                  "torque_nm", "tool_wear_min"})
        self.assertIn(s["type"], ("L", "M", "H"))

    def test_fault_phases(self):
        self.assertEqual(fleet.fault_phase("cooling_failure", 0), ("ramping", 1 / 6))
        self.assertEqual(fleet.fault_phase("cooling_failure", 6), ("holding", 1.0))
        self.assertEqual(fleet.fault_phase("cooling_failure", 36)[0], "recovering")
        self.assertEqual(fleet.fault_phase("cooling_failure", 42), ("ended", 0.0))
        self.assertEqual(fleet.fault_phase("drive_degradation", 39), ("holding", 1.0))
        self.assertEqual(fleet.fault_phase("drive_degradation", 40), ("ended", 0.0))

    def test_healthy_miner_within_rule_limits_and_faults_break_them(self):
        for i in range(30):
            p = fleet.profile("asic_miner", f"m{i}", 42)
            r = fleet.rng_for(42, f"m{i}")
            for k in range(200):
                s = fleet.sample("asic_miner", p, k, r)
                self.assertGreater(s["hashrate_ths"] / s["rated_hashrate_ths"], 0.9)
                self.assertLess(s["chip_temp_c"], 80)
                self.assertGreater(s["fan_speed_rpm"], 3000)
                self.assertLess(s["hw_error_pct"], 0.1)
            board = fleet.sample("asic_miner", p, 0, r, 1.0, "hashboard_failure")
            self.assertLess(board["hashrate_ths"] / board["rated_hashrate_ths"], 0.75)
            self.assertGreater(board["hw_error_pct"], 1.0)
            fan = fleet.sample("asic_miner", p, 0, r, 1.0, "fan_failure")
            self.assertLess(fan["fan_speed_rpm"], 1000)
            self.assertGreater(fan["chip_temp_c"], 88)

    def test_cooling_and_fan_faults_escalate_past_full_signature_others_clamp(self):
        p, r = fleet.profile("cooling_unit", "c", 42), fleet.rng_for(42, "c")
        t1 = fleet.sample("cooling_unit", p, 0, r, 1.0)["temperature_c"]
        t2 = fleet.sample("cooling_unit", p, 0, r, 1.5)["temperature_c"]
        self.assertGreater(t2 - t1, 5)
        m = fleet.profile("asic_miner", "m", 42)
        hot = fleet.sample("asic_miner", m, 0, fleet.rng_for(42, "m"), 1.5, "fan_failure")
        self.assertGreater(hot["chip_temp_c"], 100)
        self.assertGreaterEqual(hot["fan_speed_rpm"], 0)
        d = fleet.profile("storage_drive", "d", 42)
        self.assertEqual(fleet.sample("storage_drive", d, 0, fleet.rng_for(42, "d"), 1.8)["reallocated_sectors"],
                         d["reallocated_sectors"] + 5000)

    def test_every_type_has_a_fault_kind(self):
        self.assertEqual(set(fleet.FAULT_KINDS), set(TYPES))
        self.assertEqual(set(fleet.FAULT_CHOICES), set(TYPES))
        for kinds in fleet.FAULT_CHOICES.values():
            self.assertTrue(all(k in fleet.FAULT_TICKS for k in kinds))
        with self.assertRaises(ValueError):
            fleet.profile("toaster", "t", 1)


if __name__ == "__main__":
    unittest.main()
