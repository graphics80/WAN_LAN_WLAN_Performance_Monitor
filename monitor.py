import time

from config import AppConfig, configure_logging, load_env_from_file
from metrics import create_influx_client
from scheduler import start_scheduler


def main() -> None:
    configure_logging()
    load_env_from_file()
    config = AppConfig.from_env()
    client = create_influx_client(config)

    scheduler = start_scheduler(client, config)
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
