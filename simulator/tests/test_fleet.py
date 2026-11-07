import random
import unittest

from simulator import fleet

TYPES = ("cooling_unit", "storage_drive", "industrial_machine")


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

    def test_every_type_has_a_fault_kind(self):
        self.assertEqual(set(fleet.FAULT_KINDS), set(TYPES))
        with self.assertRaises(ValueError):
            fleet.profile("toaster", "t", 1)


if __name__ == "__main__":
    unittest.main()
