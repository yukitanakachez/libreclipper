import pytest
from fastapi.testclient import TestClient

from clipper.web.app import create_app
from clipper.web.worker import Worker


@pytest.fixture
def client(web_cfg):
    return TestClient(create_app(web_cfg, Worker(web_cfg.jobs_dir / "queue.json", {})),
                      base_url="http://127.0.0.1:8765")


def test_proxy_supports_range_requests(client, web_job):
    paths = web_job()
    paths.proxy.write_bytes(bytes(range(256)) * 4)          # 1024 bytes
    whole = client.get("/media/vid1/proxy.mp4")
    assert whole.status_code == 200 and len(whole.content) == 1024
    part = client.get("/media/vid1/proxy.mp4", headers={"Range": "bytes=100-199"})
    assert part.status_code == 206
    assert part.content == (bytes(range(256)) * 4)[100:200]
    assert part.headers["content-range"] == "bytes 100-199/1024"



def test_clips_are_served_from_the_clips_folder(client, web_job):
    paths = web_job()
    paths.out.mkdir(parents=True)
    (paths.out / "01-one.mp4").write_bytes(b"clip")
    r = client.get("/media/vid1/clips/01-one.mp4")
    assert r.status_code == 200 and r.content == b"clip"


@pytest.mark.parametrize("url", [
    "/media/vid1/clips/..%2Fjob.json",
    "/media/vid1/clips/%2e%2e%2fjob.json",
    "/media/vid1/clips/.hidden.mp4",
    "/media/..%2Fvid1/proxy.mp4",
    "/media/vid1/clips/missing.mp4",
    "/media/nope/proxy.mp4",
])
def test_nothing_outside_the_job_is_ever_served(client, web_job, url):
    paths = web_job()
    paths.proxy.write_bytes(b"x")
    assert client.get(url).status_code == 404
