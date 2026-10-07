"""Phase 2 smoke test: transcribe project 1, render captioned clip. Backend must run on :8000."""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api"
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
MODEL = sys.argv[2] if len(sys.argv) > 2 else "small"


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "detail": e.read().decode()}


def wait_job(job_id, timeout=900):
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        j = next(x for x in call("GET", f"/jobs?project_id={PID}") if x["id"] == job_id)
        if j["message"] != last:
            last = j["message"]
            print(f"  [{time.time() - t0:5.1f}s] {j['status']} {j['progress']:.2f} {last}")
        if j["status"] in ("done", "error"):
            return j
        time.sleep(1)
    raise TimeoutError


t0 = time.time()
job = call("POST", f"/projects/{PID}/transcribe", {"model": MODEL, "force": True})
print("transcribe job:", job.get("id"), job.get("_error"), job.get("detail", ""))
j = wait_job(job["id"])
print(f"transcribe {j['status']} in {time.time() - t0:.1f}s err={j['error']}")

t = call("GET", f"/projects/{PID}/transcript")
print("language:", t["language"], "segments:", len(t["segments"]))
for s in t["segments"][:5]:
    print(f"  {s['start']:6.2f}-{s['end']:6.2f} {s['text']}  ({len(s['words'])} words)")

proj = call("GET", f"/projects/{PID}")
print("transcript meta:", proj["transcript"])
clip = proj["clips"][0]
for style in ("bold", "box"):
    call("PATCH", f"/clips/{clip['id']}", {"caption_style": style, "start": 0, "end": 15})
    rj = call("POST", f"/clips/{clip['id']}/render")
    r = wait_job(rj["id"])
    proj = call("GET", f"/projects/{PID}")
    c = next(x for x in proj["clips"] if x["id"] == clip["id"])
    print(style, "->", r["status"], r["error"], c["export_url"], c["srt_url"])
    import shutil, pathlib
    src = pathlib.Path(r"d:\LEARN\clip\storage") / c["export_url"].removeprefix("/media/")
    shutil.copy(src, src.with_name(f"caption_{style}.mp4"))
