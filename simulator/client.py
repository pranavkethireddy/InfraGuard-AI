"""Small standard-library client for the backend-owned simulation lifecycle."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


class SimulationAPIError(RuntimeError):
    """A readable error preserving HTTP status, backend code, and request ID."""

    def __init__(self, message, *, status=None, code=None, request_id=None):
        self.status = status
        self.code = code
        self.request_id = request_id
        super().__init__(message)

    def __str__(self):
        context = [str(x) for x in (self.status, self.code, self.request_id) if x is not None]
        return super().__str__() + (f" ({', '.join(context)})" if context else "")


class SimulationClient:
    def __init__(self, base_url="http://localhost:8000/api/v1", *, timeout=10.0):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url must be an HTTP(S) API URL without credentials, query, or fragment")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method, path, body=None):
        data = None if body is None else json.dumps(body, allow_nan=False).encode()
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            try:
                envelope = json.loads(exc.read())
                error = envelope.get("error", {}) if isinstance(envelope, dict) else {}
                if not isinstance(error, dict):
                    error = {}
            except (ValueError, UnicodeError):
                error = {}
            raise SimulationAPIError(
                error.get("message") or f"Backend rejected request: {exc.reason}",
                status=exc.code,
                code=error.get("code"),
                request_id=error.get("request_id") or exc.headers.get("X-Request-ID"),
            ) from exc
        except URLError as exc:
            raise SimulationAPIError(f"Cannot reach simulation API: {exc.reason}", code="NETWORK_ERROR") from exc
        except (TimeoutError, OSError) as exc:
            raise SimulationAPIError("Simulation API connection failed or timed out", code="NETWORK_ERROR") from exc
        except (ValueError, UnicodeError) as exc:
            raise SimulationAPIError("Simulation API returned invalid JSON", code="INVALID_RESPONSE") from exc

    def start(self, scenario, seed, asset_id):
        # Validate without generating/ingesting a second stream. Backend runs it.
        from .generator import SCENARIOS
        if scenario not in SCENARIOS or type(seed) is not int or seed < 0 or not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("start requires a supported scenario, non-negative integer seed, and asset_id")
        return self._request("POST", "/simulations", {"scenario": scenario, "seed": seed, "asset_id": asset_id})

    def status(self, simulation_id):
        return self._request("GET", "/simulations/" + self._id(simulation_id))

    def reset(self, simulation_id):
        return self._request("POST", "/simulations/" + self._id(simulation_id) + "/reset")

    @staticmethod
    def _id(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("simulation_id must be a non-empty string")
        return quote(value, safe="")
