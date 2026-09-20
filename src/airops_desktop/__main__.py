from .db import Database
from .ui import DeviceToolApp


def main():
    db = Database()
    app = DeviceToolApp(db)
    app.run()


if __name__ == "__main__":
    main()
