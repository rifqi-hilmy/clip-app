"""End-to-end smoke test for Phase 1 against a running backend on :8000."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api"
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # 19s public test video


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def wait_jobs(pid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        jobs = call("GET", f"/jobs?project_id={pid}")
        if jobs and all(j["status"] in ("done", "error") for j in jobs):
            return jobs
        time.sleep(1)
    raise TimeoutError(jobs)


info = call("POST", "/videos/info", {"url": URL})
print("info:", info["title"], info["duration"], "heatmap:", info["has_heatmap"])

p = call("POST", "/projects", {"url": URL})
pid = p["id"]
print("project", pid, p["status"])
jobs = wait_jobs(pid)
print("download:", [(j["type"], j["status"], j["error"]) for j in jobs])

proj = call("GET", f"/projects/{pid}")
print("status:", proj["status"], "media:", proj["video"]["media_url"])

c1 = call("POST", f"/projects/{pid}/clips", {"start": 2, "end": 10, "title": "Blur test", "reframe": "blur"})
c2 = call("POST", f"/projects/{pid}/clips", {"start": 5, "end": 15, "title": "Center test", "reframe": "center", "crop_x": 0.3})
t0 = time.time()
call("POST", f"/projects/{pid}/render-all")
jobs = wait_jobs(pid)
print(f"render ({time.time() - t0:.1f}s):", [(j["type"], j["status"], j["message"], j["error"]) for j in jobs if j["type"] == "render"])
proj = call("GET", f"/projects/{pid}")
for c in proj["clips"]:
    print("clip:", c["title"], c["export_url"])
