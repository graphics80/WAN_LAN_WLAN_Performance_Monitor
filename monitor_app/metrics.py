import logging
from typing import Dict

import requests
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException

from monitor_app.config import AppConfig


def create_influx_client(config: AppConfig) -> InfluxDBClient:
    return InfluxDBClient(url=config.influx_url, token=config.influx_token, org=config.influx_org)


def write_metric(client: InfluxDBClient, config: AppConfig, measurement: str, tags: Dict[str, str], fields: Dict[str, float]) -> None:
    if not config.influx_token:
        logging.warning("Skipping InfluxDB write for %s: INFLUX_TOKEN not set", measurement)
        return

    point = Point(measurement)
    for key, value in tags.items():
        point = point.tag(key, value)
    for key, value in fields.items():
        point = point.field(key, value)

    write_api = client.write_api(write_options=SYNCHRONOUS)
    try:
        write_api.write(bucket=config.influx_bucket, org=config.influx_org, record=point)
    except ApiException as exc:
        logging.error("Failed to write %s to InfluxDB: %s", measurement, exc)
    except requests.exceptions.RequestException as exc:
        logging.warning("InfluxDB connection error while writing %s: %s", measurement, exc)
    except Exception:
        logging.exception("Unexpected error while writing %s to InfluxDB", measurement)
