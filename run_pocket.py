import os

from app import app, clean_config_value


def main():
    host = clean_config_value(os.environ.get("POCKET_HOST")) or "0.0.0.0"
    port = int(clean_config_value(os.environ.get("POCKET_PORT")) or "5052")
    app.run(host=host, port=port, use_reloader=False)


if __name__ == "__main__":
    main()
