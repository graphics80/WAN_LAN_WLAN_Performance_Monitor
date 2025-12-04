from monitor_app.config import AppConfig
from monitor_app.metrics import create_influx_client, write_metric


class DummyWriteAPI:
    def __init__(self):
        self.calls = []

    def write(self, bucket, org, record):
        self.calls.append((bucket, org, record))


class DummyClient:
    def __init__(self):
        self.api = DummyWriteAPI()

    def write_api(self, write_options=None):
        return self.api


def test_create_influx_client():
    cfg = AppConfig()
    cfg.influx_url = "http://example.com"
    client = create_influx_client(cfg)
    assert client.api_client.configuration.host == "http://example.com"


def test_write_metric_calls_write(monkeypatch):
    cfg = AppConfig()
    cfg.influx_token = "token"
    dummy = DummyClient()
    write_metric(dummy, cfg, "m", {"t": "v"}, {"f": 1.0})
    assert len(dummy.api.calls) == 1
    bucket, org, record = dummy.api.calls[0]
    assert bucket == cfg.influx_bucket
    assert org == cfg.influx_org
    assert record is not None
