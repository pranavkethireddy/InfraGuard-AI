from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
import math
from pathlib import Path
import random
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from simulator import SAMPLE_COUNT, generate, readings_payload
from simulator.__main__ import main
from simulator.client import SimulationAPIError, SimulationClient


class GeneratorTests(unittest.TestCase):
    def test_repeatability_and_reset_after_other_runs(self):
        first = generate("cooling_anomaly", 42, "cooling-01")
        generate("normal", 99, "cooling-02")
        self.assertEqual(first, generate("cooling_anomaly", 42, "cooling-01"))

    def test_no_shared_output_or_global_rng_state(self):
        state = random.getstate()
        samples = generate("normal", 42, "cooling-01")
        samples[0]["temperature_c"] = 999
        self.assertNotEqual(samples, generate("normal", 42, "cooling-01"))
        self.assertEqual(state, random.getstate())
        self.assertEqual(len({id(x) for x in samples}), SAMPLE_COUNT)

    def test_seed_changes_noise(self):
        self.assertNotEqual(generate("normal", 1, "a"), generate("normal", 2, "a"))

    def test_normal_is_below_demo_trigger_for_many_seeds(self):
        for seed in range(100):
            samples = generate("normal", seed, "a")
            self.assertEqual(len(samples), 30)
            self.assertTrue(all(24.25 <= s["temperature_c"] <= 24.75 for s in samples))
            self.assertTrue(all(1130 <= s["fan_speed_rpm"] <= 1170 for s in samples))

    def test_anomaly_has_persistent_trigger_and_recovery(self):
        # Check scenario coverage against the agreed demo rule, not model accuracy.
        for seed in range(100):
            samples = generate("cooling_anomaly", seed, "a")
            self.assertTrue(all(s["temperature_c"] < 32 for s in samples[:6]))
            self.assertTrue(all(s["temperature_c"] > 32 for s in samples[18:24]))
            self.assertTrue(all(s["temperature_c"] < 32 for s in samples[-6:]))
            self.assertGreater(samples[23]["temperature_c"], samples[6]["temperature_c"])
            self.assertLess(samples[23]["fan_speed_rpm"], samples[6]["fan_speed_rpm"])
            self.assertTrue(all(math.isfinite(v) for s in samples for v in s.values()))

    def test_reject_invalid_inputs(self):
        for scenario, seed, asset in [("bad", 42, "a"), ("normal", -1, "a"), ("normal", True, "a"), ("normal", 1.5, "a"), ("normal", 42, " ")]:
            with self.subTest(inputs=(scenario, seed, asset)), self.assertRaises(ValueError):
                generate(scenario, seed, asset)


class EnvelopeTests(unittest.TestCase):
    def payload(self, **kwargs):
        args = dict(scenario="normal", seed=42, asset_id="cooling-01", simulation_id="sim-test", start_at=datetime(2026, 11, 7, 20, tzinfo=timezone.utc))
        return readings_payload(**(args | kwargs))

    def test_simulated_batch_matches_contract_keys(self):
        fixture = json.loads((Path(__file__).resolve().parents[2] / "contracts/fixtures/readings.request.json").read_text())
        payload = self.payload()
        self.assertEqual(payload.keys(), fixture.keys())
        self.assertEqual(payload["data_origin"], "simulated")
        self.assertEqual(payload["simulation_id"], "sim-test")
        self.assertTrue(all(s.keys() == fixture["readings"][0].keys() for s in payload["readings"]))
        json.dumps(payload, allow_nan=False)

    def test_explicit_utc_clock_and_spacing(self):
        payload = self.payload(start_at=datetime(2026, 11, 7, 14, tzinfo=timezone(timedelta(hours=-6))))
        self.assertEqual(payload["readings"][0]["observed_at"], "2026-11-07T20:00:00Z")
        self.assertEqual(payload["readings"][-1]["observed_at"], "2026-11-07T20:00:58Z")
        self.assertEqual(payload, self.payload())

    def test_invalid_clock_and_cadence(self):
        for kwargs in [{"start_at": datetime(2026, 1, 1)}, {"tick_seconds": 0}, {"tick_seconds": float("nan")}, {"tick_seconds": float("inf")}, {"tick_seconds": True}, {"simulation_id": ""}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.payload(**kwargs)


class ClientTests(unittest.TestCase):
    @patch("simulator.client.urlopen")
    def test_start_uses_exact_contract_and_no_readings_endpoint(self, opener):
        opener.return_value = io.BytesIO(b'{"simulation_id":"sim-1"}')
        result = SimulationClient().start("normal", 42, "cooling-01")
        self.assertEqual(result["simulation_id"], "sim-1")
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:8000/api/v1/simulations")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"scenario": "normal", "seed": 42, "asset_id": "cooling-01"})
        self.assertEqual(opener.call_count, 1)

    @patch("simulator.client.urlopen")
    def test_status_and_reset_routes(self, opener):
        opener.side_effect = [io.BytesIO(b'{}'), io.BytesIO(b'{}')]
        client = SimulationClient("http://localhost:8000/api/v1/")
        client.status("sim /1")
        client.reset("sim-1")
        first, second = [call.args[0] for call in opener.call_args_list]
        self.assertEqual(first.full_url, "http://localhost:8000/api/v1/simulations/sim%20%2F1")
        self.assertEqual(first.get_method(), "GET")
        self.assertEqual(second.full_url, "http://localhost:8000/api/v1/simulations/sim-1/reset")
        self.assertEqual(second.get_method(), "POST")
        self.assertIsNone(second.data)

    @patch("simulator.client.urlopen")
    def test_error_envelope_preserves_debug_context(self, opener):
        body = b'{"error":{"code":"SIMULATION_ALREADY_RUNNING","message":"Already running","request_id":"req-1"}}'
        opener.side_effect = HTTPError("http://localhost", 409, "Conflict", {}, io.BytesIO(body))
        with self.assertRaises(SimulationAPIError) as ctx:
            SimulationClient().start("normal", 42, "a")
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(ctx.exception.code, "SIMULATION_ALREADY_RUNNING")
        self.assertIn("req-1", str(ctx.exception))

    @patch("simulator.client.urlopen")
    def test_non_json_error_uses_request_header(self, opener):
        opener.side_effect = HTTPError("http://localhost", 503, "Unavailable", {"X-Request-ID": "req-2"}, io.BytesIO(b'<html>error</html>'))
        with self.assertRaises(SimulationAPIError) as ctx:
            SimulationClient().status("sim-1")
        self.assertEqual(ctx.exception.request_id, "req-2")

    @patch("simulator.client.urlopen")
    def test_network_failure_does_not_report_success(self, opener):
        opener.side_effect = URLError("offline")
        with self.assertRaisesRegex(SimulationAPIError, "NETWORK_ERROR"):
            SimulationClient().status("sim-1")

    @patch("simulator.client.urlopen")
    def test_invalid_json_success_is_explicit(self, opener):
        opener.return_value = io.BytesIO(b'not json')
        with self.assertRaisesRegex(SimulationAPIError, "INVALID_RESPONSE"):
            SimulationClient().status("sim-1")

    def test_invalid_url(self):
        for url in ("file:///tmp/a", "https://user:password@localhost", "http://localhost/api?token=a", "http://localhost/api#fragment"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                SimulationClient(url)

    @patch("simulator.client.urlopen")
    def test_list_runs_filters_and_empty_result(self, opener):
        opener.return_value = io.BytesIO(b'{"items":[],"total":0,"limit":50,"offset":0}')
        result = SimulationClient().list_runs(status="running", asset_id="cooling /01")
        self.assertEqual(result["items"], [])
        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, "http://localhost:8000/api/v1/simulations?status=running&asset_id=cooling+%2F01")

    def test_list_rejects_invalid_filters(self):
        for filters in ({"status": "unknown"}, {"asset_id": " "}):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                SimulationClient().list_runs(**filters)


class CLITests(unittest.TestCase):
    @patch("simulator.client.urlopen")
    def test_list_command(self, opener):
        opener.return_value = io.BytesIO(b'{"items":[],"total":0,"limit":50,"offset":0}')
        out = io.StringIO()
        with redirect_stdout(out):
            status = main(["list", "--status", "running", "--asset-id", "cooling-01"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out.getvalue())["total"], 0)
    @patch("simulator.client.urlopen")
    def test_preview_is_offline_and_valid_json(self, opener):
        out = io.StringIO()
        with redirect_stdout(out):
            status = main(["preview", "--scenario", "cooling_anomaly", "--start-at", "2026-11-07T20:00:00Z"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out.getvalue())["data_origin"], "simulated")
        opener.assert_not_called()

    def test_bad_preview_exits_nonzero(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = main(["preview", "--seed", "-1", "--start-at", "2026-11-07T20:00:00Z"])
        self.assertEqual(status, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("seed", err.getvalue())


if __name__ == "__main__":
    unittest.main()
