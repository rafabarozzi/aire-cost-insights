"""Single additive meter, exclusive contract pool, one full settlement period."""
from datetime import date
from decimal import Decimal
from .analysis import period, report
from .connectors import quantity


def simulate(db, tenant, card):
    start,end = card["billing_period"]
    a,b = period(start,end)
    valid_from, valid_to = map(date.fromisoformat, card["validity"])
    if not valid_from <= a < b <= valid_to or not card["source"].strip():
        raise ValueError("price source and effective dates required")
    if card["pool"] != "exclusive" or len(card["currency"])!=3 or not card["currency"].isalpha():
        raise ValueError("expected one exclusive pool and currency")
    items = report(db,tenant,start,end,card["integration_ref"],card["environment"])["usage"]
    item = next((x for x in items if x["meter"] == card["meter"]),None)
    if not item or item["usage"]["aggregation"] != "sum" or item["usage"]["unit"] != card["unit"] or item["usage"]["value"] is None:
        raise ValueError("requires complete additive usage in contract units")
    used = quantity(item["usage"]["value"])
    reduction = quantity(card["scenario_reduction"])
    discount = quantity(card["discount_fraction"])
    if reduction > used or discount > 1:
        raise ValueError("invalid reduction or discount")
    def cost(volume):
        remaining = max(Decimal(0),volume-quantity(card["included_units"]))
        variable = Decimal(0)
        tiers = card["tiers"]
        if not tiers or tiers[-1]["width"] is not None or any(t["width"] is None for t in tiers[:-1]):
            raise ValueError("tiers require a final unbounded band")
        for band in tiers:
            width = band["width"]
            take = remaining if width is None else min(remaining,quantity(width))
            variable += take*quantity(band["unit_rate"])
            remaining -= take
        return max(quantity(card["minimum_spend"]),quantity(card["base_fee"])+variable*(1-discount))
    before, after = cost(used),cost(used-reduction)
    return {"mode":"synthetic","period":[start,end],"measured_usage":str(used),"unit":card["unit"],
            "provider_reported_cost":None,"aire_estimated_cost":str(before),"scenario_cost":str(after),
            "potential_volume_reduction":str(reduction),"potential_savings":str(before-after),
            "observed_savings":None,"currency":card["currency"],"assumptions":card}
