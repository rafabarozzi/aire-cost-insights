from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from .connectors import DAY, instant, quantity
from .store import catalog


def period(start, end):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if not 0 < (b - a).days <= 366:
        raise ValueError("expected 1 to 366 UTC days, end exclusive")
    return a, b


def measure(db, tenant, ref, meter, env, start, end, spec):
    rows = db.execute("""SELECT * FROM samples WHERE tenant=? AND ref=? AND meter=? AND env=?
                      AND day>=? AND day<? ORDER BY start""", (tenant, ref, meter, env, str(start), str(end)))
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["day"]].append(row)
    total, daily, gaps = Decimal(0), [], []
    for i in range((end-start).days):
        day = start + i*DAY
        samples = grouped[str(day)]
        expected = instant(str(day)+"T00:00:00Z")
        valid = True
        values = []
        for row in samples:
            valid &= instant(row["start"]) == expected and row["value"] is not None
            expected = instant(row["end"])
            if row["value"] is not None:
                values.append(quantity(row["value"]))
        if not valid or expected != instant(str(day+DAY)+"T00:00:00Z"):
            gaps.append(str(day))
            continue
        subtotal = sum(values)
        if spec["aggregation"] == "mean":
            subtotal /= len(values)
        total += subtotal
        daily.append({"day":str(day), "value":str(subtotal)})
    if daily and spec["aggregation"] == "mean":
        total /= len(daily)
    return {"value": None if gaps else str(total), "unit": spec["unit"], "aggregation": spec["aggregation"],
            "daily":daily, "incomplete_days":gaps}


def report(db, tenant, start, end, ref=None, environment=None, product=None):
    a,b = period(start,end)
    config = catalog()
    bindings = config["bindings"][tenant]
    if ref and ref not in bindings:
        raise ValueError("unknown integration")
    days = (b-a).days
    items, opportunities = [], []
    ranking = defaultdict(list)
    for name, spec in bindings.items():
        if ref and ref != name:
            continue
        for meter, meta in spec["meters"].items():
            if product and product != meta["resource"]:
                continue
            for env in spec["environments"]:
                if environment and environment != env:
                    continue
                args = db,tenant,name,meter,env
                now = measure(*args,a,b,meta)
                prev = measure(*args,a-days*DAY,a,meta)
                v,p = now["value"],prev["value"]
                delta = str(quantity(v)-quantity(p)) if v is not None and p is not None else None
                forecast = None
                if v is not None:
                    forecast = str(quantity(v)*30/days if meta["aggregation"]=="sum" else quantity(v))
                item = {"integration_ref":name,"provider":spec["provider"],"meter":meter,"product":meta["resource"],
                        "environment":env,"usage":now,"previous_usage":prev,"change":delta,
                        "projection_30d":forecast,"source_scope":spec["provider_scope"]}
                items.append(item)
                if env != "unattributed" and v is not None:
                    ranking[(name,meter)].append({"environment":env,"value":v})
                if meta.get("dimension_evidence") and delta is not None and Decimal(delta)>0:
                    opportunities.append({"period":[start,end],"integration_ref":name,"meter":meter,
                        "evidence":[meta["dimension_evidence"],{"previous":p,"current":v,"unit":meta["unit"]}],
                        "assumptions":"A dimensão pode ser substituída sem perder segmentação operacional.",
                        "action":"Reproduzir consultas sem request_id em ambiente de teste.",
                        "possible_volume_reduction":None,"potential_savings":None,"observed_savings":None,
                        "risk":"Perda de correlação por requisição e de filtros de diagnóstico.",
                        "required_coverage":["Comparar alertas, SLOs e dashboards da jornada",
                                             "Reproduzir um incidente conhecido com traces e logs"],
                        "confidence":"low","missing":["cardinalidade por tag","dependências de consulta","SKU e tarifa"]})
    costs = [c for c in config["provider_costs"] if c["tenant"]==tenant and c["start"]==start and c["end"]==end
             and (not ref or c["ref"]==ref) and not environment and not product]
    return {"schema_version":"1","mode":config["mode"],"tenant":tenant,"period":[start,end],
            "comparison_period":[str(a-days*DAY),start],"projection_assumption":"Média diária constante por 30 dias, sem sazonalidade. Contagens médias preservam a unidade.",
            "usage":items,"consumers":[{"integration_ref":k[0],"meter":k[1],"ranking":sorted(v,key=lambda e:-quantity(e["value"]))}
            for k,v in ranking.items()],"provider_reported_cost":costs,"aire_estimated_cost":None,
            "observed_savings":None,"opportunities":opportunities,
            "provisional_days":[str(a+i*DAY) for i in range(days) if any(x["provider"]=="datadog" for x in items)
                and a+i*DAY >= date.fromisoformat(config["as_of"])-timedelta(days=3)
                and a+i*DAY < date.fromisoformat(config["as_of"])]}
