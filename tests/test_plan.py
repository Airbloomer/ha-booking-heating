"""Renders the blueprint's plan templates outside Home Assistant.

The HA functions, filters and tests the templates use are faked below. The
fakes' results for as_datetime (date and time, date only, 'unknown', a missing
entity), as_local with timestamp(), timestamp_custom, and the `list` and
`match` tests were compared with Home Assistant 2026.6.3 in Europe/Rome and
agreed. `parse` is a rough stand-in for HA's conversion of rendered
templates into native types, not HA's own parser. as_datetime raises on an
unparseable value here, the stricter of the behaviours HA versions have had,
so a template that reaches it with bad input fails the test.

This checks the plan logic; it is not a run in Home Assistant.
Run: python3 tests/test_plan.py
"""
import ast
import datetime as dt
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import jinja2
import yaml

BP = Path(__file__).resolve().parent.parent / "blueprints/automation/airbloomer/booking_heating.yaml"
TZ = ZoneInfo("Europe/Rome")


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor("!input", lambda l, n: ("!input", l.construct_scalar(n)))
DOC = yaml.load(BP.read_text(), Loader=Loader)
DEFAULTS = {k: v.get("default") for s in DOC["blueprint"]["input"].values() for k, v in s["input"].items()}


def parse(text):
    # HA turns a rendered template into a native value when it looks like one.
    t = text.strip()
    if t in ("True", "False"):
        return t == "True"
    if t == "None":
        return None
    try:
        return ast.literal_eval(t)
    except Exception:
        return t


def make_env(now, states, attrs):
    env = jinja2.Environment(extensions=["jinja2.ext.loopcontrols"])

    def as_datetime(v):
        if isinstance(v, dt.datetime):
            return v
        try:
            return dt.datetime.fromisoformat(str(v))
        except ValueError:
            d = dt.date.fromisoformat(str(v))  # raises, like a strict HA
            return dt.datetime(d.year, d.month, d.day)

    def as_local(v):
        return v.replace(tzinfo=TZ) if v.tzinfo is None else v.astimezone(TZ)

    def timestamp_custom(ts, fmt, local=True):
        return dt.datetime.fromtimestamp(float(ts), TZ if local else dt.timezone.utc).strftime(fmt)

    def st(entity):
        return states.get(entity, "unknown")

    env.globals.update(
        now=lambda: now, timedelta=dt.timedelta, as_datetime=as_datetime, states=st,
        is_state=lambda e, s: st(e) == s, state_attr=lambda e, a: attrs.get(e, {}).get(a),
    )
    env.filters.update(as_local=as_local, timestamp_custom=timestamp_custom, states=st)
    env.tests.update(
        match=lambda v, p: re.match(p, str(v)) is not None,
        list=lambda v: isinstance(v, list),
    )
    return env


def plan(now, events, *, inputs=None, states=None, indoor=None, applied="vacant_long"):
    inputs = {**DEFAULTS, "climate_entity": "climate.t", "calendars": ["calendar.c"],
              "state_helper": "input_text.s", **(inputs or {})}
    states = {"climate.t": "heat", "calendar.c": "off", "input_text.s": applied, **(states or {})}
    attrs = {"climate.t": {"current_temperature": indoor, "temperature": 15.0}}
    env = make_env(now.replace(tzinfo=TZ), states, attrs)
    ctx = {}
    for k, v in DOC["variables"].items():
        if isinstance(v, tuple):
            ctx[k] = inputs[v[1]]
        else:
            ctx[k] = parse(env.from_string(str(v)).render(**ctx))
    ctx["cal"] = {"calendar.c": {"events": events}}
    for step in DOC["actions"]:
        if "variables" in step:
            for k, v in step["variables"].items():
                ctx[k] = parse(env.from_string(str(v)).render(**ctx))
            if "final_plan" in step["variables"]:
                return ctx["final_plan"]
    raise AssertionError("final_plan not found")


def stay(a, b, title="Reserved"):
    return {"start": a, "end": b, "summary": title}


T = dt.datetime
UNTIL = {"inputs": {"assume_vacant_until": "input_datetime.v"}}

CASES = [
    # Published defaults: no assume_vacant_until set, every plan as before.
    ("default: during a stay", T(2026, 12, 2, 12), [stay("2026-12-01", "2026-12-05")], {}, "occupied"),
    ("default: nothing booked", T(2026, 11, 20, 12), [], {}, "vacant_long"),
    ("default: owner block ignored", T(2026, 12, 21, 12), [stay("2026-12-20", "2027-01-06", "Airbnb (Not available)")], {}, "vacant_long"),
    ("default: short gap", T(2026, 12, 6, 12), [stay("2026-12-01", "2026-12-05"), stay("2026-12-08", "2026-12-10")], {}, "vacant_short"),
    ("default: pre-heat 15.5 h before at 15 °C", T(2026, 12, 1, 1, 0), [stay("2026-12-01", "2026-12-05")], {"indoor": 15.0}, "preheat"),
    ("default: not yet 16 h before at 15 °C", T(2026, 11, 30, 23, 30), [stay("2026-12-01", "2026-12-05")], {"indoor": 15.0}, "vacant_long"),
    ("default: frost outside season", T(2026, 10, 15, 12), [], {}, "off_season"),
    # assume_vacant_until set to 30 Nov 23:59.
    ("until: stay in progress ignored", T(2026, 11, 20, 12), [stay("2026-11-18", "2026-11-25")],
     {**UNTIL, "states": {"input_datetime.v": "2026-11-30 23:59:00"}}, "vacant_long"),
    ("until: 1 Dec arrival still pre-heats on time", T(2026, 12, 1, 1, 0), [stay("2026-12-01", "2026-12-05")],
     {**UNTIL, "states": {"input_datetime.v": "2026-11-30 23:59:00"}, "indoor": 15.0}, "preheat"),
    ("until: pre-heat starts before the date for a stay that starts after it", T(2026, 12, 1, 1, 0), [stay("2026-12-01", "2026-12-05")],
     {**UNTIL, "states": {"input_datetime.v": "2026-12-01 12:00:00"}, "indoor": 15.0}, "preheat"),
    ("until: a stay starting exactly at the date counts", T(2026, 12, 1, 12), [stay("2026-12-01", "2026-12-05")],
     {**UNTIL, "states": {"input_datetime.v": "2026-12-01 16:00:00"}, "indoor": 15.0}, "preheat"),
    ("until: expired, stays count again", T(2026, 12, 2, 12), [stay("2026-12-01", "2026-12-05")],
     {**UNTIL, "states": {"input_datetime.v": "2026-11-30 23:59:00"}}, "occupied"),
    ("until: expired, a stay that started before the date counts again", T(2026, 12, 2, 12), [stay("2026-11-28", "2026-12-05")],
     {**UNTIL, "states": {"input_datetime.v": "2026-12-01 00:00:00"}}, "occupied"),
    ("until: expired, a stay before the date counts again for the gap", T(2026, 12, 6, 12),
     [stay("2026-11-28", "2026-12-05"), stay("2026-12-08", "2026-12-10")],
     {**UNTIL, "states": {"input_datetime.v": "2026-12-01 00:00:00"}}, "vacant_short"),
    ("until: date-only helper", T(2026, 11, 20, 12), [stay("2026-11-18", "2026-11-25")],
     {**UNTIL, "states": {"input_datetime.v": "2026-12-01"}}, "vacant_long"),
    ("until: unknown helper has no effect", T(2026, 11, 20, 12), [stay("2026-11-18", "2026-11-25")],
     {**UNTIL, "states": {"input_datetime.v": "unknown"}}, "occupied"),
    ("until: unavailable helper has no effect", T(2026, 11, 20, 12), [stay("2026-11-18", "2026-11-25")],
     {**UNTIL, "states": {"input_datetime.v": "unavailable"}}, "occupied"),
    ("until: missing helper has no effect", T(2026, 11, 20, 12), [stay("2026-11-18", "2026-11-25")],
     UNTIL, "occupied"),
    ("until: time-only helper has no effect", T(2026, 11, 20, 12), [stay("2026-11-18", "2026-11-25")],
     {**UNTIL, "states": {"input_datetime.v": "12:00:00"}}, "occupied"),
    ("default: ignored event with a malformed start is still skipped", T(2026, 12, 2, 12),
     [stay("garbage", "2027-01-06", "Airbnb (Not available)"), stay("2026-12-01", "2026-12-05")], {}, "occupied"),
]


def main():
    failed = 0
    for name, now, events, kw, want in CASES:
        try:
            got = plan(now, events, inputs=kw.get("inputs"), states=kw.get("states"), indoor=kw.get("indoor"))
        except Exception as e:  # HA would abort the run
            got = f"error: {type(e).__name__}: {e}"
        ok = got == want
        failed += not ok
        print(("ok  " if ok else "FAIL"), name, "->", got, "" if ok else f"(want {want})")
    print(f"{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
