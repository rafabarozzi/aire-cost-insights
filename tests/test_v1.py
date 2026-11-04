from contextlib import closing
import http.client
import json
import tempfile
import threading
import unittest
from datetime import date
from http.server import HTTPServer
from pathlib import Path

from aire.__main__ import handler
from aire.analysis import period, report
from aire.connectors import fixture_page, normalize
from aire.pricing import simulate
from aire.store import ROOT, catalog, collect, connect

T, DD, DT = "commerce-demo", "dd-demo", "dps-demo"


class V1(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)/"db"
        self.db = connect(self.path)
        self.addCleanup(self.db.close)

    def test_periods(self):
        for start,end in [("2026-02-30","2026-03-01"),("2026-10-01","2026-10-01"),
                          ("2026-10-02","2026-10-01"),("2025-01-01","2026-10-01")]:
            with self.assertRaises(ValueError):
                period(start,end)

    def test_incremental_refresh(self):
        self.assertEqual(2,collect(self.db,T,DD,"2026-10-03"))
        self.assertEqual(0,collect(self.db,T,DD,"2026-10-03"))
        self.assertEqual(1,collect(self.db,T,DD,"2026-10-04"))
        self.assertEqual(3,collect(self.db,T,DD,"2026-10-04",refresh=True))
        self.assertEqual(3*24*7,self.db.execute("SELECT count(*) FROM samples").fetchone()[0])

    def test_rollback_and_replay(self):
        with self.assertRaises(RuntimeError):
            collect(self.db,T,DD,"2026-10-03",budget=1)
        self.assertEqual(0,self.db.execute("SELECT count(*) FROM checkpoints").fetchone()[0])
        self.assertEqual(0,self.db.execute("SELECT count(*) FROM samples").fetchone()[0])
        self.assertEqual(2,collect(self.db,T,DD,"2026-10-03"))

    def test_pagination_retry_duplicate(self):
        calls = []
        def fetch(spec,ref,day,cursor):
            calls.append(cursor)
            if len(calls)==1:
                raise TimeoutError()
            page,_ = fixture_page(spec,ref,day,None)
            return page, "second" if cursor is None else None
        self.assertEqual(3,collect(self.db,T,DT,"2026-10-02",fetch,lambda seconds:None))
        self.assertEqual([None,None,"second"],calls)
        self.assertEqual(4,self.db.execute("SELECT count(*) FROM samples").fetchone()[0])

    def test_scope_guard(self):
        day = date(2026,10,1)
        page,_ = fixture_page(catalog()["bindings"][T][DD],DD,day)
        page["data"][0]["attributes"]["public_id"]="different-org"
        with self.assertRaises(ValueError):
            normalize(catalog()["bindings"][T][DD],page,day)

    def test_gaps_trends_and_opportunity(self):
        collect(self.db,T,DD,"2026-10-09")
        r = report(self.db,T,"2026-10-03","2026-10-05",DD,product="metrics.custom")
        item = r["usage"][0]
        self.assertEqual("150",item["usage"]["value"])
        self.assertEqual("40",item["change"])
        self.assertEqual("150",item["projection_30d"])
        self.assertEqual("low",r["opportunities"][0]["confidence"])
        partial = report(self.db,T,"2026-10-07","2026-10-09",DD)["usage"][0]
        self.assertIsNone(partial["usage"]["value"])
        self.assertEqual(["2026-10-07"],partial["usage"]["incomplete_days"])
        self.assertIsNone(partial["projection_30d"])

    def test_cost_scope_and_null(self):
        collect(self.db,T,DT,"2026-10-09")
        r = report(self.db,T,"2026-10-01","2026-10-05",DT)
        self.assertEqual("180.00",r["provider_reported_cost"][0]["amount"])
        self.assertEqual([],report(self.db,T,"2026-10-01","2026-10-05",DT,"production")["provider_reported_cost"])
        item = report(self.db,T,"2026-10-06","2026-10-07",DT,"lab")["usage"][0]
        self.assertIsNone(item["usage"]["value"])

    def test_financial_scenarios(self):
        collect(self.db,T,DT,"2026-10-09")
        card = json.loads((ROOT/"fixtures/scenario.json").read_text())
        result = simulate(self.db,T,card)
        self.assertEqual(("52","100","0",None),tuple(result[k] for k in
            ["measured_usage","aire_estimated_cost","potential_savings","observed_savings"]))
        card["minimum_spend"]="0"
        self.assertEqual("9.0",simulate(self.db,T,card)["potential_savings"])
        card["validity"][0]="2026-10-02"
        with self.assertRaises(ValueError):
            simulate(self.db,T,card)

    def test_http_isolation(self):
        collect(self.db,T,DT,"2026-10-03")
        collect(self.db,"other-demo","dps-other","2026-10-03")
        server = HTTPServer(("127.0.0.1",0),handler(self.path,{T:"aaa","other-demo":"bbb"}))
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def get(path,token):
            with closing(http.client.HTTPConnection("127.0.0.1",server.server_port)) as con:
                con.request("GET",path,headers={"Authorization":"Bearer "+token})
                res = con.getresponse()
                return res.status,json.loads(res.read())
        self.assertEqual(401,get("/v1/inventory","wrong")[0])
        self.assertEqual(400,get("/v1/report?tenant=other-demo&start=2026-10-01&end=2026-10-02","aaa")[0])
        self.assertEqual(400,get("/v1/samples?ref=dps-other&day=2026-10-01","aaa")[0])
        for token, tenant, env in [("aaa",T,"production"),("bbb","other-demo","isolated")]:
            status,body = get("/v1/report?start=2026-10-01&end=2026-10-02",token)
            self.assertEqual((200,tenant),(status,body["tenant"]))
            self.assertIn(env,{x["environment"] for x in body["usage"]})
        status,body = get("/v1/samples?ref=dps-demo&day=2026-10-01","aaa")
        self.assertEqual((200,4),(status,len(body["samples"])))
