"""Provider-shaped fixture readers. No network or provider mutations."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

DAY = timedelta(days=1)


def quantity(value):
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid quantity") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("invalid non-negative quantity")
    return number


def fixture_page(spec, ref, day, cursor=None):
    if cursor is not None:
        raise ValueError("unexpected fixture cursor")
    path = Path(__file__).resolve().parent.parent / "fixtures" / (ref + ".json")
    seed = json.loads(path.read_text())
    n = (day - date.fromisoformat(spec["first_day"])).days
    stamp = day.isoformat() + "T00:00:00Z"
    data = []
    if spec["provider"] == "datadog":
        for hour in range(24):
            if n == 6 and hour == 12:
                continue
            t = f"{day}T{hour:02}:00:00Z"
            measurements = [{"usage_type": key, "value": seed["hourly_base"][i] + n * seed["daily_step"][i]}
                            for i, key in enumerate(spec["meters"])]
            data.append({"id": f"demo-{t}", "attributes": {"public_id": spec["provider_scope"],
                         "timestamp": t, "measurements": measurements}})
        return {"data": data}, None
    for j, env in enumerate(spec["environments"]):
        usage = [{"startTime": stamp, "endTime": (day + DAY).isoformat() + "T00:00:00Z",
                  "capabilityKey": key, "unitMeasure": meta["unit"],
                  "value": None if n == 5 and j == 1 else (1+j)*(seed["daily_base"][i]+n*seed["daily_step"][i])}
                 for i, (key, meta) in enumerate(spec["meters"].items())]
        data.append({"environmentId": env, "usage": usage})
    return {"lastModifiedTime": (day + DAY).isoformat() + "T00:00:00Z", "data": data}, None


def instant(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("expected UTC timestamp")
    return parsed


def normalize(spec, page, day):
    """IDs and units come from a pinned integration scope and meter catalog."""
    if page is None:
        return []
    rows = []
    def add(meter, env, start, end, value, source_id):
        if start.date() != day or end <= start or end > datetime.combine(day + DAY, datetime.min.time(), timezone.utc):
            raise ValueError("record outside collection window")
        if meter not in spec["meters"] or env not in spec["environments"]:
            raise ValueError("unmapped meter or environment")
        rows.append((meter, env, start.isoformat(), end.isoformat(), None if value is None else str(quantity(value)), source_id))

    for item in page["data"]:
        if spec["provider"] == "datadog":
            attr = item["attributes"]
            if attr["public_id"] != spec["provider_scope"]:
                raise ValueError("provider scope mismatch")
            start = instant(attr["timestamp"])
            for m in attr["measurements"]:
                add(m["usage_type"], "unattributed", start, start + timedelta(hours=1), m["value"], item["id"])
        elif spec["provider"] == "dynatrace" and spec["license"] == "DPS":
            for m in item["usage"]:
                meter = m["capabilityKey"]
                if m["unitMeasure"] != spec["meters"][meter]["unit"]:
                    raise ValueError("provider unit changed")
                add(meter, item["environmentId"], instant(m["startTime"]), instant(m["endTime"]),
                    m["value"], page["lastModifiedTime"])
        else:
            raise ValueError("unsupported provider or license")
    return rows
