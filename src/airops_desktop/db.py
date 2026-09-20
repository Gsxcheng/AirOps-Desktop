import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "airops_desktop.db"

DEFAULT_SETTINGS = {
    "ssh_port": "22",
    "telnet_port": "23",
    "ftp_port": "21",
    "username": "",
    "password": "",
    "ftp_username": "",
    "ftp_password": "",
    "ftp_remote_dir": "/",
    "connect_timeout": "10",
    "command_timeout": "30",
    "log_dir": str(ROOT / "logs"),
    "result_dir": str(ROOT / "results"),
}


class Database:
    def __init__(self, path=DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._ensure_runtime_paths()

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def session(self):
        conn = self.connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self):
        with self.session() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS command_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    commands TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS device_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    protocol TEXT NOT NULL DEFAULT 'SSH',
                    port INTEGER,
                    username TEXT NOT NULL DEFAULT '',
                    password TEXT NOT NULL DEFAULT '',
                    privilege_enabled INTEGER NOT NULL DEFAULT 0,
                    enable_command TEXT NOT NULL DEFAULT 'enable',
                    enable_password TEXT NOT NULL DEFAULT '',
                    ftp_enabled INTEGER NOT NULL DEFAULT 0,
                    ftp_port INTEGER,
                    ftp_username TEXT NOT NULL DEFAULT '',
                    ftp_password TEXT NOT NULL DEFAULT '',
                    ftp_remote_dir TEXT NOT NULL DEFAULT '/',
                    command_template_id INTEGER,
                    schedule_enabled INTEGER NOT NULL DEFAULT 0,
                    schedule_time TEXT NOT NULL DEFAULT '02:00',
                    remark TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(command_template_id) REFERENCES command_templates(id)
                );

                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    ip TEXT NOT NULL,
                    protocol TEXT NOT NULL DEFAULT 'SSH',
                    port INTEGER,
                    username TEXT NOT NULL DEFAULT '',
                    password TEXT NOT NULL DEFAULT '',
                    privilege_enabled INTEGER NOT NULL DEFAULT 0,
                    enable_command TEXT NOT NULL DEFAULT 'enable',
                    enable_password TEXT NOT NULL DEFAULT '',
                    ftp_enabled INTEGER NOT NULL DEFAULT 0,
                    ftp_host TEXT NOT NULL DEFAULT '',
                    ftp_port INTEGER,
                    ftp_username TEXT NOT NULL DEFAULT '',
                    ftp_password TEXT NOT NULL DEFAULT '',
                    ftp_remote_dir TEXT NOT NULL DEFAULT '/',
                    template_id INTEGER,
                    schedule_enabled INTEGER NOT NULL DEFAULT 0,
                    schedule_time TEXT NOT NULL DEFAULT '02:00',
                    last_schedule_date TEXT,
                    remark TEXT NOT NULL DEFAULT '',
                    last_status TEXT NOT NULL DEFAULT 'Not tested',
                    last_test_time TEXT,
                    FOREIGN KEY(template_id) REFERENCES command_templates(id)
                );

                CREATE TABLE IF NOT EXISTS execution_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    trigger_type TEXT NOT NULL,
                    success INTEGER,
                    summary TEXT NOT NULL DEFAULT '',
                    output_path TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(device_id) REFERENCES devices(id)
                );
                """
            )

            for key, value in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                    (key, value),
                )
            self._seed_public_templates(conn)

    def _seed_public_templates(self, conn):
        now = datetime.now().isoformat(timespec="seconds")
        command_defs = [
            (
                "Generic CLI - Example",
                "# Replace with commands supported by your device.\nshow version",
                "Vendor-neutral starter example.",
            ),
            (
                "Huawei VRP - Read-only Inspection",
                "\n".join(
                    [
                        "screen-length 0 temporary",
                        "display clock",
                        "display version",
                        "display device",
                        "display cpu-usage",
                        "display memory-usage",
                        "display temperature",
                        "display power",
                        "display fan",
                        "display interface brief",
                        "display ip interface brief",
                        "display vlan",
                        "display arp",
                        "display ip routing-table",
                        "display logbuffer",
                        "display startup",
                        "display current-configuration",
                    ]
                ),
                "Read-only Huawei VRP inspection and configuration collection example.",
            ),
        ]

        command_ids = {}
        for name, commands, description in command_defs:
            row = conn.execute(
                "SELECT id FROM command_templates WHERE name=?", (name,)
            ).fetchone()
            if row:
                command_ids[name] = row["id"]
                continue
            cur = conn.execute(
                "INSERT INTO command_templates"
                "(name,commands,description,created_at,updated_at)"
                " VALUES(?,?,?,?,?)",
                (name, commands, description, now, now),
            )
            command_ids[name] = cur.lastrowid

        device_defs = [
            (
                "Generic SSH",
                "SSH",
                22,
                command_ids["Generic CLI - Example"],
                "Generic SSH device. Credentials are intentionally blank.",
            ),
            (
                "Generic Telnet",
                "Telnet",
                23,
                command_ids["Generic CLI - Example"],
                "Legacy Telnet device. Use only on trusted isolated networks.",
            ),
            (
                "Huawei VRP",
                "SSH",
                22,
                command_ids["Huawei VRP - Read-only Inspection"],
                "Generic Huawei VRP read-only inspection template.",
            ),
        ]

        for name, protocol, port, command_template_id, remark in device_defs:
            if conn.execute(
                "SELECT id FROM device_templates WHERE name=?", (name,)
            ).fetchone():
                continue
            conn.execute(
                """
                INSERT INTO device_templates(
                    name,protocol,port,username,password,
                    privilege_enabled,enable_command,enable_password,
                    ftp_enabled,ftp_port,ftp_username,ftp_password,ftp_remote_dir,
                    command_template_id,schedule_enabled,schedule_time,remark,
                    created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    name, protocol, port, "", "",
                    0, "enable", "",
                    0, 21, "", "", "/",
                    command_template_id, 0, "02:00", remark,
                    now, now,
                ),
            )

    def _ensure_runtime_paths(self):
        log_dir = ROOT / "logs"
        result_dir = ROOT / "results"
        log_dir.mkdir(parents=True, exist_ok=True)
        result_dir.mkdir(parents=True, exist_ok=True)
        self.save_settings(
            {"log_dir": str(log_dir), "result_dir": str(result_dir)}
        )

    def get_settings(self):
        with self.session() as conn:
            rows = conn.execute("SELECT key,value FROM settings").fetchall()
        values = DEFAULT_SETTINGS.copy()
        values.update({row["key"]: row["value"] for row in rows})
        return values

    def save_settings(self, values):
        with self.session() as conn:
            for key, value in values.items():
                conn.execute(
                    "INSERT INTO settings(key,value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, str(value)),
                )

    def list_templates(self):
        with self.session() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM command_templates ORDER BY name"
                ).fetchall()
            ]

    def get_template(self, template_id):
        if not template_id:
            return None
        with self.session() as conn:
            row = conn.execute(
                "SELECT * FROM command_templates WHERE id=?", (template_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_template(self, name, commands, description="", template_id=None):
        now = datetime.now().isoformat(timespec="seconds")
        with self.session() as conn:
            if template_id:
                conn.execute(
                    "UPDATE command_templates SET name=?,commands=?,description=?,"
                    "updated_at=? WHERE id=?",
                    (name, commands, description, now, template_id),
                )
                return template_id
            cur = conn.execute(
                "INSERT INTO command_templates"
                "(name,commands,description,created_at,updated_at)"
                " VALUES(?,?,?,?,?)",
                (name, commands, description, now, now),
            )
            return cur.lastrowid

    def delete_template(self, template_id):
        with self.session() as conn:
            conn.execute(
                "UPDATE devices SET template_id=NULL WHERE template_id=?",
                (template_id,),
            )
            conn.execute(
                "UPDATE device_templates SET command_template_id=NULL "
                "WHERE command_template_id=?",
                (template_id,),
            )
            conn.execute(
                "DELETE FROM command_templates WHERE id=?", (template_id,)
            )

    def list_device_templates(self):
        sql = """
        SELECT dt.*, ct.name AS command_template_name
        FROM device_templates dt
        LEFT JOIN command_templates ct ON ct.id=dt.command_template_id
        ORDER BY dt.name
        """
        with self.session() as conn:
            return [dict(row) for row in conn.execute(sql).fetchall()]

    def get_device_template(self, template_id):
        if not template_id:
            return None
        with self.session() as conn:
            row = conn.execute(
                "SELECT * FROM device_templates WHERE id=?", (template_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_device_template(self, data, template_id=None):
        now = datetime.now().isoformat(timespec="seconds")
        columns = [
            "name","protocol","port","username","password",
            "privilege_enabled","enable_command","enable_password",
            "ftp_enabled","ftp_port","ftp_username","ftp_password",
            "ftp_remote_dir","command_template_id","schedule_enabled",
            "schedule_time","remark",
        ]
        values = [data.get(column) for column in columns]
        with self.session() as conn:
            if template_id:
                assignments = ",".join(f"{column}=?" for column in columns)
                conn.execute(
                    f"UPDATE device_templates SET {assignments},updated_at=? "
                    "WHERE id=?",
                    values + [now, template_id],
                )
                return template_id
            marks = ",".join("?" for _ in columns)
            cur = conn.execute(
                f"INSERT INTO device_templates({','.join(columns)},created_at,updated_at) "
                f"VALUES({marks},?,?)",
                values + [now, now],
            )
            return cur.lastrowid

    def delete_device_template(self, template_id):
        with self.session() as conn:
            conn.execute(
                "DELETE FROM device_templates WHERE id=?", (template_id,)
            )

    def list_devices(self):
        sql = """
        SELECT d.*, t.name AS template_name
        FROM devices d
        LEFT JOIN command_templates t ON t.id=d.template_id
        ORDER BY d.name
        """
        with self.session() as conn:
            return [dict(row) for row in conn.execute(sql).fetchall()]

    def get_device(self, device_id):
        with self.session() as conn:
            row = conn.execute(
                "SELECT * FROM devices WHERE id=?", (device_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_device(self, data, device_id=None):
        columns = [
            "name","ip","protocol","port","username","password",
            "privilege_enabled","enable_command","enable_password",
            "ftp_enabled","ftp_host","ftp_port","ftp_username","ftp_password",
            "ftp_remote_dir","template_id","schedule_enabled",
            "schedule_time","remark",
        ]
        values = [data.get(column) for column in columns]
        with self.session() as conn:
            if device_id:
                assignments = ",".join(f"{column}=?" for column in columns)
                conn.execute(
                    f"UPDATE devices SET {assignments} WHERE id=?",
                    values + [device_id],
                )
                return device_id
            marks = ",".join("?" for _ in columns)
            cur = conn.execute(
                f"INSERT INTO devices({','.join(columns)}) VALUES({marks})",
                values,
            )
            return cur.lastrowid

    def delete_device(self, device_id):
        with self.session() as conn:
            conn.execute(
                "DELETE FROM execution_runs WHERE device_id=?", (device_id,)
            )
            conn.execute("DELETE FROM devices WHERE id=?", (device_id,))

    def update_device_status(self, device_id, status):
        now = datetime.now().isoformat(timespec="seconds")
        with self.session() as conn:
            conn.execute(
                "UPDATE devices SET last_status=?,last_test_time=? WHERE id=?",
                (status, now, device_id),
            )

    def reset_device_test_statuses(self):
        with self.session() as conn:
            conn.execute(
                "UPDATE devices SET last_status='Not tested',last_test_time=NULL"
            )

    def mark_schedule_run(self, device_id, date_text):
        with self.session() as conn:
            conn.execute(
                "UPDATE devices SET last_schedule_date=? WHERE id=?",
                (date_text, device_id),
            )

    def create_run(self, device_id, trigger_type):
        started = datetime.now().isoformat(timespec="seconds")
        with self.session() as conn:
            cur = conn.execute(
                "INSERT INTO execution_runs(device_id,started_at,trigger_type) "
                "VALUES(?,?,?)",
                (device_id, started, trigger_type),
            )
            return cur.lastrowid

    def finish_run(self, run_id, success, summary, output_path):
        finished = datetime.now().isoformat(timespec="seconds")
        with self.session() as conn:
            conn.execute(
                "UPDATE execution_runs SET finished_at=?,success=?,summary=?,"
                "output_path=? WHERE id=?",
                (finished, int(bool(success)), summary, output_path, run_id),
            )

    def list_runs(self, limit=500):
        sql = """
        SELECT r.*, d.name AS device_name, d.ip AS device_ip
        FROM execution_runs r
        JOIN devices d ON d.id=r.device_id
        ORDER BY r.id DESC
        LIMIT ?
        """
        with self.session() as conn:
            return [
                dict(row)
                for row in conn.execute(sql, (int(limit),)).fetchall()
            ]
