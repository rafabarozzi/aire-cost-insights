import argparse
from contextlib import closing
from datetime import date
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

from .analysis import report
from .pricing import simulate
from .store import ROOT, catalog, collect, connect


def identities():
    tokens = json.loads(os.environ.get("AIRE_READ_TOKENS","{}"))
    if not tokens or not isinstance(tokens,dict) or any(k not in catalog()["bindings"] or not isinstance(v,str)
            or not v.isascii() or len(v)<16 for k,v in tokens.items()) or len(set(tokens.values()))!=len(tokens):
        raise ValueError("configure distinct tenant-scoped AIRE_READ_TOKENS (16+ ASCII characters)")
    return tokens


def handler(db_path, tokens):
    class Reader(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No URL, headers, provider body or credential material in logs.

        def respond(self,status,body):
            data = json.dumps(body,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlsplit(self.path)
            if self.path == "/health":
                return self.respond(200,{"status":"ok"})
            token = self.headers.get("Authorization","")
            tenant = next((k for k,v in tokens.items() if hmac.compare_digest(token.encode(),("Bearer "+v).encode())),None)
            if tenant is None:
                return self.respond(401,{"error":"unauthorized"})
            if url.path not in ("/v1/inventory","/v1/report","/v1/samples","/v1/scenarios/example"):
                return self.respond(404,{"error":"not_found"})
            try:
                q = parse_qs(url.query,strict_parsing=True,keep_blank_values=True,max_num_fields=6)
                if any(len(v)!=1 or not v[0] for v in q.values()):
                    raise ValueError()
                params = {k:v[0] for k,v in q.items()}
                if url.path == "/v1/inventory":
                    if params:
                        raise ValueError()
                    return self.respond(200,{"schema_version":"1","mode":"synthetic","tenant":tenant,
                        "integrations":catalog()["bindings"][tenant]})
                with closing(sqlite3.connect(Path(db_path).resolve().as_uri()+"?mode=ro",uri=True)) as db:
                    db.row_factory = sqlite3.Row
                    if url.path == "/v1/scenarios/example":
                        card = json.loads((ROOT/"fixtures/scenario.json").read_text())
                        if params or card["integration_ref"] not in catalog()["bindings"][tenant]:
                            return self.respond(404,{"error":"not_found"})
                        result = simulate(db,tenant,card)
                    elif url.path == "/v1/report":
                        if set(params)-{"start","end","ref","environment","product"}:
                            raise ValueError()
                        result = report(db,tenant,**params)
                    else:
                        if set(params)!={"ref","day"} or params["ref"] not in catalog()["bindings"][tenant]:
                            raise ValueError()
                        date.fromisoformat(params["day"])
                        result = {"schema_version":"1","mode":"synthetic","samples":[dict(r) for r in db.execute(
                            "SELECT * FROM samples WHERE tenant=? AND ref=? AND day=? ORDER BY meter,env,start",
                            (tenant,params["ref"],params["day"]))]}
                self.respond(200,result)
            except (ValueError,TypeError,KeyError,OverflowError):
                self.respond(400,{"error":"invalid_parameters"})
            except sqlite3.Error:
                self.respond(503,{"error":"storage_unavailable"})
    return Reader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db",default=os.getenv("AIRE_DB","aire.db"))
    sub = parser.add_subparsers(dest="cmd",required=True)
    seed = sub.add_parser("collect")
    seed.add_argument("--until",default="2026-10-09")
    seed.add_argument("--refresh",action="store_true")
    api = sub.add_parser("serve")
    api.add_argument("--host",default="127.0.0.1")
    api.add_argument("--port",type=int,default=8080)
    scenario = sub.add_parser("scenario")
    scenario.add_argument("file")
    scenario.add_argument("--tenant",required=True)
    args = parser.parse_args()
    if args.cmd=="serve":
        with HTTPServer((args.host,args.port), handler(args.db,identities())) as server:
            server.serve_forever()
    else:
        with closing(connect(args.db)) as db:
            if args.cmd=="collect":
                for tenant, bindings in catalog()["bindings"].items():
                    for ref in bindings:
                        calls = collect(db,tenant,ref,args.until,refresh=args.refresh)
                        print(f"{tenant}/{ref} calls={calls}")
            else:
                print(json.dumps(simulate(db,args.tenant,json.loads(Path(args.file).read_text())),indent=2))


if __name__=="__main__":
    main()
