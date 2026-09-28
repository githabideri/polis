"""R2 VisualCaptureService (Phase 2, 2026-09-28, design doc §11.2).

The /polis/observer-screenshot endpoint is a SCARCE VISUAL SENSOR: one
capture in flight, ~0.6-1 s, teleport/restore side effects (enforced in
C#: atomic in-flight guard, JSON rejection, lifecycle-safe restore). This
service is the Python-side owner of that scariness:

  - one capture in flight (single-threaded caller: a request either
    reuses a recent capture or performs exactly one);
  - requests carry {maxAgeMs, reason}: a capture newer than maxAgeMs
    satisfies the request WITHOUT a new capture (coalescing - judge
    ~100 ms, debug UI ~500 ms, dashcam ~1000 ms);
  - timeouts and disconnects become RESULTS (error cause + provenance),
    never exceptions into the decision loop;
  - every result carries provenance: request id, reason, capture
    timestamp, whether it was fresh or coalesced.

Scope tonight (flagged to review): the service is implemented and
unit-tested against a fake transport. The three EXISTING screenshot
consumers (dashcam, judge attachment, UI auto-capture) keep their direct
calls until a separate controlled pass migrates them - a behavior change
in the live loop is not a Phase 2 deliverable.

Semantic sensors (/polis/state, scan, verify, action outcomes) stay on
the direct-query path: fixtures and completion verification never depend
on the visual sensor (a deterministic oracle must not hang on a
serialized 1-second sensor).
"""
import time


class Capture:
    """One screenshot result with provenance (doc §12.1/12.2).

    `result` is a taxonomy, never a collapsed None:
      ok           capture succeeded (payload present)
      coalesced    satisfied by an existing capture within maxAgeMs
      unavailable  the endpoint REJECTED (its own JSON error: in-flight
                   guard fired, entity gone, world not ready)
      timeout      no result within the timeout
      disconnected transport-level failure (viewer gone, network)
    The future judge path cares WHY visual evidence is unavailable -
    rejection and disconnect are different diagnoses.
    """

    def __init__(self, request_id, reason, payload, captured_at_ms,
                 result, caused_by=None, detail=None):
        self.request_id = request_id
        self.reason = reason            # who asked ("judge"/"dashcam"/...)
        self.payload = payload          # bytes | None
        self.captured_at_ms = captured_at_ms
        self.result = result            # the taxonomy above
        self.caused_by = caused_by      # optional action id (12.6 rule 6)
        self.detail = detail            # short human string (endpoint msg)

    @property
    def ok(self):
        return self.payload is not None and self.result in ("ok", "coalesced")

    def to_dict(self):
        return {"request_id": self.request_id, "reason": self.reason,
                "result": self.result, "captured_at_ms": self.captured_at_ms,
                "caused_by": self.caused_by, "detail": self.detail,
                "bytes": len(self.payload) if self.payload else 0}


class VisualCaptureService:
    """The serialized visual sensor. The transport is injected: the live
    one issues GET /polis/observer-screenshot (base64 JSON); tests inject
    a fake with controllable latency and failures.

    Single-threaded by contract: the v5 loop is one thread, and the C#
    endpoint already enforces one capture in flight server-side. This
    class adds the client-side policy layer on top.
    """

    def __init__(self, transport, timeout_s=10.0):
        self._transport = transport       # fn() -> (bytes, captured_at_ms)
                                           # raises on failure
        self._timeout_s = timeout_s
        self._last = None                 # Capture (the last successful one)
        self._seq = 0
        self.stats = {"captures": 0, "coalesced": 0,
                      "timeouts": 0, "errors": 0}

    def _now(self):
        return int(time.time() * 1000)

    def request(self, reason, max_age_ms, now=None):
        """Request a screenshot no older than max_age_ms.

        Coalescing: a successful capture newer than max_age_ms (or taken
        since the previous request) satisfies the request without a new
        capture. Otherwise exactly one capture is attempted; timeout and
        failure are results, not exceptions.
        """
        now = self._now() if now is None else now
        self._seq += 1
        rid = "cap-%04d" % self._seq
        last = self._last
        if last is not None and last.ok:
            age = now - last.captured_at_ms
            if age <= max_age_ms:
                self.stats["coalesced"] += 1
                return Capture(rid, reason, last.payload,
                               last.captured_at_ms, "coalesced",
                               detail="reused %dms-old capture" % age)
        # one capture; failure kinds become results, never exceptions
        try:
            payload, captured_at_ms = self._with_timeout()
            self.stats["captures"] += 1
            self._last = Capture(rid, reason, payload, captured_at_ms,
                                 "ok")
            return self._last
        except _Timeout:
            self.stats["timeouts"] += 1
            return Capture(rid, reason, None, now, "timeout")
        except (ConnectionError, OSError) as e:   # transport / viewer gone
            self.stats["errors"] += 1
            return Capture(rid, reason, None, now, "disconnected",
                           detail=str(e)[:120])
        except _Rejected as e:                    # endpoint said no (JSON)
            self.stats["errors"] += 1
            return Capture(rid, reason, None, now, "unavailable",
                           detail=str(e)[:120])
        except Exception as e:                    # anything else: treat as
            self.stats["errors"] += 1              # unavailable, keep cause
            return Capture(rid, reason, None, now, "unavailable",
                           detail=str(e)[:120])

    def _with_timeout(self):
        # The live transport is a blocking HTTP call; the timeout is
        # enforced by the transport itself (http_json timeout=). This
        # wrapper keeps the timeout policy in ONE place: it wraps the
        # transport with an alarm only when the transport does not
        # provide its own (the fake transport simulates both shapes).
        if hasattr(self._transport, "has_own_timeout") and \
                self._transport.has_own_timeout:
            return self._transport()
        import threading
        box = {}

        def run():
            try:
                box["ok"] = self._transport()
            except Exception as e:
                box["err"] = e

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(self._timeout_s)
        if t.is_alive():
            raise _Timeout()
        if "err" in box:
            raise box["err"]
        return box["ok"]


class _Timeout(Exception):
    pass


class _Rejected(Exception):
    """The endpoint rejected the capture (its own JSON error response:
    in-flight guard, entity gone, world not ready). Distinct from a
    transport failure (12.1)."""


# ---------------------------------------------------------------- live ----

def http_screenshot_transport(harness, uid, poll_cell=None):
    """The live transport: GET /polis/observer-screenshot (the hardened
    C# endpoint: atomic in-flight guard, JSON rejection, lifecycle-safe
    restore). Returns (base64-decoded bytes, captured_at_ms)."""
    import base64
    import urllib.request

    url = harness + "/polis/observer-screenshot"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()
    # the endpoint returns {"ok": true, "base64": "...",
    # "captureTimeMs": ...} or a JSON error
    import json as _json
    try:
        d = _json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return raw, int(time.time() * 1000)
    if not d.get("ok"):
        raise _Rejected(d.get("error") or "observer-screenshot rejected")
    return base64.b64decode(d.get("base64") or ""), int(d.get("captureTimeMs")
                                                       or time.time() * 1000)
