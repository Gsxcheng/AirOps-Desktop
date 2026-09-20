import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .network import execute_device, test_tcp


class DeviceToolApp:
    def __init__(self, db):
        self.db = db
        self.root = tk.Tk()
        self.root.title("AirOps Desktop 0.1.0")
        self.root.geometry("1420x860")
        self.root.minsize(1100, 700)

        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=25)

        self.running_ids = set()
        self.current_template_id = None
        self.current_device_template_id = None
        self.templates_cache = []
        self.device_templates_cache = []

        self._build_settings()
        self._build_notebook()
        self._build_log()

        self.db.reset_device_test_statuses()
        self.refresh_all()
        self.root.after(15000, self._scheduler_tick)

    def run(self):
        self.root.mainloop()

    def log(self, text):
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {text}"
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")

    # ---------------- settings ----------------

    def _build_settings(self):
        frame = ttk.LabelFrame(self.root, text="Default connection settings")
        frame.pack(fill="x", padx=8, pady=(8, 4))

        self.setting_vars = {}
        fields = [
            ("SSH port", "ssh_port", False),
            ("Telnet port", "telnet_port", False),
            ("FTP port", "ftp_port", False),
            ("Username", "username", False),
            ("Password", "password", True),
            ("Connect timeout", "connect_timeout", False),
            ("Command timeout", "command_timeout", False),
        ]

        for index, (label, key, secret) in enumerate(fields):
            row = index // 4
            col = (index % 4) * 2
            ttk.Label(frame, text=label + ":").grid(
                row=row, column=col, sticky="e", padx=(6, 2), pady=4
            )
            var = tk.StringVar()
            self.setting_vars[key] = var
            ttk.Entry(
                frame,
                textvariable=var,
                width=18,
                show="*" if secret else "",
            ).grid(row=row, column=col + 1, sticky="ew", padx=(0, 8), pady=4)

        ttk.Button(frame, text="Save defaults", command=self.save_settings).grid(
            row=1, column=6, columnspan=2, sticky="e", padx=8, pady=4
        )

        for col in (1, 3, 5, 7):
            frame.grid_columnconfigure(col, weight=1)

    def refresh_settings(self):
        values = self.db.get_settings()
        for key, var in self.setting_vars.items():
            var.set(values.get(key, ""))

    def save_settings(self):
        values = {key: var.get().strip() for key, var in self.setting_vars.items()}
        self.db.save_settings(values)
        self.log("Default settings saved.")

    # ---------------- tabs ----------------

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=4)

        self.device_tab = ttk.Frame(self.notebook)
        self.command_tab = ttk.Frame(self.notebook)
        self.device_template_tab = ttk.Frame(self.notebook)
        self.schedule_tab = ttk.Frame(self.notebook)
        self.run_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.device_tab, text="Devices")
        self.notebook.add(self.command_tab, text="Command templates")
        self.notebook.add(self.device_template_tab, text="Device templates")
        self.notebook.add(self.schedule_tab, text="Schedules")
        self.notebook.add(self.run_tab, text="Execution history")

        self._build_device_tab()
        self._build_command_tab()
        self._build_device_template_tab()
        self._build_schedule_tab()
        self._build_run_tab()

    # ---------------- devices ----------------

    def _build_device_tab(self):
        bar = ttk.Frame(self.device_tab)
        bar.pack(fill="x", padx=4, pady=4)

        for text, command in [
            ("Add", self.add_device),
            ("Edit", self.edit_device),
            ("Delete", self.delete_devices),
            ("Test connectivity", self.test_selected),
            ("Run selected", self.run_selected),
            ("Import MD", self.import_devices),
            ("Export MD", self.export_devices),
        ]:
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=3)

        columns = (
            "name",
            "ip",
            "protocol",
            "port",
            "template",
            "status",
            "schedule",
            "remark",
        )
        self.device_tree = ttk.Treeview(
            self.device_tab,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        headings = {
            "name": "Device",
            "ip": "Address",
            "protocol": "Protocol",
            "port": "Port",
            "template": "Command template",
            "status": "Status",
            "schedule": "Schedule",
            "remark": "Remark",
        }
        widths = {
            "name": 220,
            "ip": 140,
            "protocol": 80,
            "port": 60,
            "template": 230,
            "status": 100,
            "schedule": 100,
            "remark": 260,
        }
        for column in columns:
            self.device_tree.heading(column, text=headings[column])
            self.device_tree.column(
                column,
                width=widths[column],
                minwidth=50,
                anchor="w",
            )

        scroll_y = ttk.Scrollbar(
            self.device_tab, orient="vertical", command=self.device_tree.yview
        )
        scroll_x = ttk.Scrollbar(
            self.device_tab, orient="horizontal", command=self.device_tree.xview
        )
        self.device_tree.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )
        self.device_tree.pack(fill="both", expand=True, padx=4)
        scroll_y.place(relx=1.0, rely=0.06, relheight=0.88, anchor="ne")
        scroll_x.pack(fill="x", padx=4, pady=(0, 4))
        self.device_tree.bind("<Double-1>", lambda _event: self.edit_device())

    def refresh_devices(self):
        self.device_tree.delete(*self.device_tree.get_children())
        for device in self.db.list_devices():
            schedule = (
                device.get("schedule_time") or ""
                if device.get("schedule_enabled")
                else ""
            )
            self.device_tree.insert(
                "",
                "end",
                iid=str(device["id"]),
                values=(
                    device["name"],
                    device["ip"],
                    device["protocol"],
                    device.get("port") or "",
                    device.get("template_name") or "",
                    device.get("last_status") or "Not tested",
                    schedule,
                    device.get("remark") or "",
                ),
            )

    def _selected_device_ids(self):
        return [int(item) for item in self.device_tree.selection()]

    def add_device(self):
        self._device_dialog(None)

    def edit_device(self):
        selected = self._selected_device_ids()
        if len(selected) != 1:
            messagebox.showinfo("Edit device", "Select exactly one device.")
            return
        self._device_dialog(self.db.get_device(selected[0]))

    def _device_dialog(self, device):
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit device" if device else "Add device")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True)

        command_templates = self.db.list_templates()
        command_name_to_id = {item["name"]: item["id"] for item in command_templates}
        device_templates = self.db.list_device_templates()
        device_template_map = {item["name"]: item for item in device_templates}

        vars_ = {
            "name": tk.StringVar(),
            "ip": tk.StringVar(),
            "protocol": tk.StringVar(value="SSH"),
            "port": tk.StringVar(value="22"),
            "username": tk.StringVar(),
            "password": tk.StringVar(),
            "privilege_enabled": tk.BooleanVar(),
            "enable_command": tk.StringVar(value="enable"),
            "enable_password": tk.StringVar(),
            "ftp_enabled": tk.BooleanVar(),
            "ftp_host": tk.StringVar(),
            "ftp_port": tk.StringVar(value="21"),
            "ftp_username": tk.StringVar(),
            "ftp_password": tk.StringVar(),
            "ftp_remote_dir": tk.StringVar(value="/"),
            "command_template": tk.StringVar(),
            "schedule_enabled": tk.BooleanVar(),
            "schedule_time": tk.StringVar(value="02:00"),
            "remark": tk.StringVar(),
            "device_template": tk.StringVar(),
        }

        if device:
            command = self.db.get_template(device.get("template_id"))
            for key in (
                "name",
                "ip",
                "protocol",
                "port",
                "username",
                "password",
                "enable_command",
                "enable_password",
                "ftp_host",
                "ftp_port",
                "ftp_username",
                "ftp_password",
                "ftp_remote_dir",
                "schedule_time",
                "remark",
            ):
                value = device.get(key)
                vars_[key].set("" if value is None else value)
            vars_["privilege_enabled"].set(bool(device.get("privilege_enabled")))
            vars_["ftp_enabled"].set(bool(device.get("ftp_enabled")))
            vars_["schedule_enabled"].set(bool(device.get("schedule_enabled")))
            vars_["command_template"].set(command["name"] if command else "")
        else:
            settings = self.db.get_settings()
            vars_["port"].set(settings["ssh_port"])
            vars_["username"].set(settings["username"])
            vars_["password"].set(settings["password"])
            vars_["ftp_port"].set(settings["ftp_port"])

        template_bar = ttk.LabelFrame(dialog, text="Start from device template")
        template_bar.grid(row=0, column=0, columnspan=4, sticky="ew", padx=8, pady=6)
        template_combo = ttk.Combobox(
            template_bar,
            textvariable=vars_["device_template"],
            values=list(device_template_map),
            state="readonly",
            width=32,
        )
        template_combo.pack(side="left", padx=6, pady=5)

        def apply_device_template():
            item = device_template_map.get(vars_["device_template"].get())
            if not item:
                return
            mapping = {
                "protocol": item.get("protocol") or "SSH",
                "port": item.get("port") or "",
                "username": item.get("username") or "",
                "password": item.get("password") or "",
                "privilege_enabled": bool(item.get("privilege_enabled")),
                "enable_command": item.get("enable_command") or "enable",
                "enable_password": item.get("enable_password") or "",
                "ftp_enabled": bool(item.get("ftp_enabled")),
                "ftp_port": item.get("ftp_port") or "",
                "ftp_username": item.get("ftp_username") or "",
                "ftp_password": item.get("ftp_password") or "",
                "ftp_remote_dir": item.get("ftp_remote_dir") or "/",
                "schedule_enabled": bool(item.get("schedule_enabled")),
                "schedule_time": item.get("schedule_time") or "02:00",
                "command_template": item.get("command_template_name") or "",
            }
            for key, value in mapping.items():
                vars_[key].set(value)

        ttk.Button(
            template_bar, text="Apply", command=apply_device_template
        ).pack(side="left", padx=4)

        fields = [
            ("Name", "name", False),
            ("Address", "ip", False),
            ("Protocol", "protocol", False),
            ("Port", "port", False),
            ("Username", "username", False),
            ("Password", "password", True),
            ("Enable command", "enable_command", False),
            ("Enable password", "enable_password", True),
            ("FTP host", "ftp_host", False),
            ("FTP port", "ftp_port", False),
            ("FTP username", "ftp_username", False),
            ("FTP password", "ftp_password", True),
            ("FTP directory", "ftp_remote_dir", False),
            ("Schedule time", "schedule_time", False),
            ("Remark", "remark", False),
        ]

        row = 1
        for index, (label, key, secret) in enumerate(fields):
            col = (index % 2) * 2
            if index and index % 2 == 0:
                row += 1
            ttk.Label(dialog, text=label + ":").grid(
                row=row, column=col, sticky="e", padx=5, pady=4
            )
            if key == "protocol":
                widget = ttk.Combobox(
                    dialog,
                    textvariable=vars_[key],
                    values=("SSH", "Telnet"),
                    state="readonly",
                )
            else:
                widget = ttk.Entry(
                    dialog,
                    textvariable=vars_[key],
                    show="*" if secret else "",
                )
            widget.grid(row=row, column=col + 1, sticky="ew", padx=5, pady=4)

        row += 1
        ttk.Checkbutton(
            dialog,
            text="Privilege mode",
            variable=vars_["privilege_enabled"],
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(
            dialog,
            text="FTP download",
            variable=vars_["ftp_enabled"],
        ).grid(row=row, column=2, columnspan=2, sticky="w", padx=8, pady=4)

        row += 1
        ttk.Checkbutton(
            dialog,
            text="Daily schedule",
            variable=vars_["schedule_enabled"],
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        ttk.Label(dialog, text="Command template:").grid(
            row=row, column=2, sticky="e", padx=5, pady=4
        )
        ttk.Combobox(
            dialog,
            textvariable=vars_["command_template"],
            values=list(command_name_to_id),
            state="readonly",
        ).grid(row=row, column=3, sticky="ew", padx=5, pady=4)

        row += 1
        button_bar = ttk.Frame(dialog)
        button_bar.grid(row=row, column=0, columnspan=4, sticky="e", padx=8, pady=10)

        def save():
            try:
                name = vars_["name"].get().strip()
                ip = vars_["ip"].get().strip()
                if not name or not ip:
                    raise ValueError("Name and address are required.")
                datetime.strptime(vars_["schedule_time"].get().strip() or "02:00", "%H:%M")

                port_text = vars_["port"].get().strip()
                ftp_port_text = vars_["ftp_port"].get().strip()
                data = {
                    "name": name,
                    "ip": ip,
                    "protocol": vars_["protocol"].get() or "SSH",
                    "port": int(port_text) if port_text else None,
                    "username": vars_["username"].get().strip(),
                    "password": vars_["password"].get(),
                    "privilege_enabled": int(vars_["privilege_enabled"].get()),
                    "enable_command": vars_["enable_command"].get().strip() or "enable",
                    "enable_password": vars_["enable_password"].get(),
                    "ftp_enabled": int(vars_["ftp_enabled"].get()),
                    "ftp_host": vars_["ftp_host"].get().strip(),
                    "ftp_port": int(ftp_port_text) if ftp_port_text else None,
                    "ftp_username": vars_["ftp_username"].get().strip(),
                    "ftp_password": vars_["ftp_password"].get(),
                    "ftp_remote_dir": vars_["ftp_remote_dir"].get().strip() or "/",
                    "template_id": command_name_to_id.get(
                        vars_["command_template"].get()
                    ),
                    "schedule_enabled": int(vars_["schedule_enabled"].get()),
                    "schedule_time": vars_["schedule_time"].get().strip() or "02:00",
                    "remark": vars_["remark"].get().strip(),
                }
                self.db.save_device(data, device["id"] if device else None)
                dialog.destroy()
                self.refresh_all()
            except Exception as exc:
                messagebox.showerror("Save failed", str(exc), parent=dialog)

        ttk.Button(button_bar, text="Save", command=save).pack(side="left", padx=4)
        ttk.Button(button_bar, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=4
        )

        for col in (1, 3):
            dialog.grid_columnconfigure(col, weight=1)

    def delete_devices(self):
        ids = self._selected_device_ids()
        if not ids:
            return
        if not messagebox.askyesno(
            "Delete devices", f"Delete {len(ids)} selected device(s)?"
        ):
            return
        for device_id in ids:
            self.db.delete_device(device_id)
        self.refresh_all()

    def test_selected(self):
        ids = self._selected_device_ids()
        if not ids:
            messagebox.showinfo("Connectivity", "Select one or more devices.")
            return

        settings = self.db.get_settings()

        def worker():
            devices = [self.db.get_device(device_id) for device_id in ids]
            with ThreadPoolExecutor(max_workers=min(32, len(devices))) as pool:
                futures = {}
                for device in devices:
                    port = device.get("port")
                    if not port:
                        port = (
                            settings["ssh_port"]
                            if device["protocol"].upper() == "SSH"
                            else settings["telnet_port"]
                        )
                    future = pool.submit(
                        test_tcp,
                        device["ip"],
                        port,
                        settings["connect_timeout"],
                    )
                    futures[future] = device

                for future in as_completed(futures):
                    device = futures[future]
                    try:
                        future.result()
                        status = "Reachable"
                    except Exception:
                        status = "Unreachable"
                    self.db.update_device_status(device["id"], status)
                    self.root.after(0, self.refresh_devices)

        threading.Thread(target=worker, daemon=True).start()

    def run_selected(self):
        ids = self._selected_device_ids()
        if not ids:
            messagebox.showinfo("Run", "Select one or more devices.")
            return
        self._run_device_ids(ids, "manual")

    def _run_device_ids(self, ids, trigger_type):
        ids = [device_id for device_id in ids if device_id not in self.running_ids]
        if not ids:
            return

        settings = self.db.get_settings()
        batch_stamp = datetime.now().strftime("%Y%m%d%H%M%S")

        def worker():
            for device_id in ids:
                self.running_ids.add(device_id)

            def run_one(device_id):
                device = self.db.get_device(device_id)
                template = self.db.get_template(device.get("template_id"))
                return device, execute_device(
                    device,
                    template,
                    settings,
                    trigger_type,
                    self.db,
                    lambda message: self.root.after(0, self.log, message),
                    batch_stamp=batch_stamp,
                )

            try:
                with ThreadPoolExecutor(max_workers=min(16, len(ids))) as pool:
                    futures = {pool.submit(run_one, device_id): device_id for device_id in ids}
                    for future in as_completed(futures):
                        device_id = futures[future]
                        try:
                            device, result = future.result()
                            ok, summary, _path = result
                            self.root.after(
                                0,
                                self.log,
                                f"{device['name']}: {'OK' if ok else 'FAILED'} - {summary}",
                            )
                        except Exception as exc:
                            self.root.after(
                                0, self.log, f"Device {device_id}: {type(exc).__name__}: {exc}"
                            )
                        finally:
                            self.running_ids.discard(device_id)
                            self.root.after(0, self.refresh_all)
            finally:
                for device_id in ids:
                    self.running_ids.discard(device_id)

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- command templates ----------------

    def _build_command_tab(self):
        pane = ttk.Panedwindow(self.command_tab, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=4, pady=4)

        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left, weight=1)
        pane.add(right, weight=3)

        self.command_list = tk.Listbox(left, exportselection=False)
        self.command_list.pack(fill="both", expand=True, padx=4, pady=4)
        self.command_list.bind("<<ListboxSelect>>", self._on_command_selected)

        buttons = ttk.Frame(left)
        buttons.pack(fill="x", padx=4, pady=4)
        ttk.Button(buttons, text="New", command=self.new_command_template).pack(
            side="left", padx=2
        )
        ttk.Button(buttons, text="Delete", command=self.delete_command_template).pack(
            side="left", padx=2
        )

        self.command_name_var = tk.StringVar()
        self.command_desc_var = tk.StringVar()

        ttk.Label(right, text="Name:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(right, textvariable=self.command_name_var).grid(
            row=0, column=1, sticky="ew", padx=4, pady=4
        )
        ttk.Label(right, text="Description:").grid(
            row=1, column=0, sticky="e", padx=4, pady=4
        )
        ttk.Entry(right, textvariable=self.command_desc_var).grid(
            row=1, column=1, sticky="ew", padx=4, pady=4
        )
        self.command_text = tk.Text(right, wrap="none")
        self.command_text.grid(
            row=2, column=0, columnspan=2, sticky="nsew", padx=4, pady=4
        )
        ttk.Button(right, text="Save template", command=self.save_command_template).grid(
            row=3, column=1, sticky="e", padx=4, pady=6
        )
        right.grid_columnconfigure(1, weight=1)
        right.grid_rowconfigure(2, weight=1)

    def refresh_command_templates(self):
        self.templates_cache = self.db.list_templates()
        self.command_list.delete(0, "end")
        for item in self.templates_cache:
            self.command_list.insert("end", item["name"])

    def _on_command_selected(self, _event=None):
        selection = self.command_list.curselection()
        if not selection:
            return
        item = self.templates_cache[selection[0]]
        self.current_template_id = item["id"]
        self.command_name_var.set(item["name"])
        self.command_desc_var.set(item.get("description") or "")
        self.command_text.delete("1.0", "end")
        self.command_text.insert("1.0", item.get("commands") or "")

    def new_command_template(self):
        self.current_template_id = None
        self.command_name_var.set("")
        self.command_desc_var.set("")
        self.command_text.delete("1.0", "end")

    def save_command_template(self):
        name = self.command_name_var.get().strip()
        if not name:
            messagebox.showerror("Save failed", "Template name is required.")
            return
        self.current_template_id = self.db.save_template(
            name,
            self.command_text.get("1.0", "end").strip(),
            self.command_desc_var.get().strip(),
            self.current_template_id,
        )
        self.refresh_all()

    def delete_command_template(self):
        if not self.current_template_id:
            return
        if messagebox.askyesno("Delete", "Delete this command template?"):
            self.db.delete_template(self.current_template_id)
            self.current_template_id = None
            self.new_command_template()
            self.refresh_all()

    # ---------------- device templates ----------------

    def _build_device_template_tab(self):
        pane = ttk.Panedwindow(self.device_template_tab, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=4, pady=4)

        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left, weight=1)
        pane.add(right, weight=3)

        self.device_template_list = tk.Listbox(left, exportselection=False)
        self.device_template_list.pack(fill="both", expand=True, padx=4, pady=4)
        self.device_template_list.bind(
            "<<ListboxSelect>>", self._on_device_template_selected
        )

        buttons = ttk.Frame(left)
        buttons.pack(fill="x", padx=4, pady=4)
        ttk.Button(buttons, text="New", command=self.new_device_template).pack(
            side="left", padx=2
        )
        ttk.Button(buttons, text="Delete", command=self.delete_device_template).pack(
            side="left", padx=2
        )

        self.dt_vars = {
            "name": tk.StringVar(),
            "protocol": tk.StringVar(value="SSH"),
            "port": tk.StringVar(value="22"),
            "username": tk.StringVar(),
            "password": tk.StringVar(),
            "privilege_enabled": tk.BooleanVar(),
            "enable_command": tk.StringVar(value="enable"),
            "enable_password": tk.StringVar(),
            "command_template": tk.StringVar(),
            "remark": tk.StringVar(),
        }

        fields = [
            ("Name", "name", False),
            ("Protocol", "protocol", False),
            ("Port", "port", False),
            ("Username", "username", False),
            ("Password", "password", True),
            ("Enable command", "enable_command", False),
            ("Enable password", "enable_password", True),
            ("Remark", "remark", False),
        ]

        for row, (label, key, secret) in enumerate(fields):
            ttk.Label(right, text=label + ":").grid(
                row=row, column=0, sticky="e", padx=4, pady=4
            )
            if key == "protocol":
                widget = ttk.Combobox(
                    right,
                    textvariable=self.dt_vars[key],
                    values=("SSH", "Telnet"),
                    state="readonly",
                )
            else:
                widget = ttk.Entry(
                    right,
                    textvariable=self.dt_vars[key],
                    show="*" if secret else "",
                )
            widget.grid(row=row, column=1, sticky="ew", padx=4, pady=4)

        row = len(fields)
        ttk.Checkbutton(
            right,
            text="Privilege mode",
            variable=self.dt_vars["privilege_enabled"],
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        row += 1
        ttk.Label(right, text="Command template:").grid(
            row=row, column=0, sticky="e", padx=4, pady=4
        )
        self.dt_command_combo = ttk.Combobox(
            right,
            textvariable=self.dt_vars["command_template"],
            state="readonly",
        )
        self.dt_command_combo.grid(row=row, column=1, sticky="ew", padx=4, pady=4)

        row += 1
        ttk.Button(
            right, text="Save device template", command=self.save_device_template
        ).grid(row=row, column=1, sticky="e", padx=4, pady=8)

        right.grid_columnconfigure(1, weight=1)

    def refresh_device_templates(self):
        self.device_templates_cache = self.db.list_device_templates()
        self.device_template_list.delete(0, "end")
        for item in self.device_templates_cache:
            self.device_template_list.insert("end", item["name"])
        self.dt_command_combo["values"] = [item["name"] for item in self.db.list_templates()]

    def _on_device_template_selected(self, _event=None):
        selection = self.device_template_list.curselection()
        if not selection:
            return
        item = self.device_templates_cache[selection[0]]
        self.current_device_template_id = item["id"]
        for key in ("name", "protocol", "port", "username", "password", "enable_command", "enable_password", "remark"):
            value = item.get(key)
            self.dt_vars[key].set("" if value is None else value)
        self.dt_vars["privilege_enabled"].set(bool(item.get("privilege_enabled")))
        self.dt_vars["command_template"].set(item.get("command_template_name") or "")

    def new_device_template(self):
        self.current_device_template_id = None
        self.dt_vars["name"].set("")
        self.dt_vars["protocol"].set("SSH")
        self.dt_vars["port"].set("22")
        self.dt_vars["username"].set("")
        self.dt_vars["password"].set("")
        self.dt_vars["privilege_enabled"].set(False)
        self.dt_vars["enable_command"].set("enable")
        self.dt_vars["enable_password"].set("")
        self.dt_vars["command_template"].set("")
        self.dt_vars["remark"].set("")

    def save_device_template(self):
        name = self.dt_vars["name"].get().strip()
        if not name:
            messagebox.showerror("Save failed", "Template name is required.")
            return
        command_map = {item["name"]: item["id"] for item in self.db.list_templates()}
        port_text = self.dt_vars["port"].get().strip()
        data = {
            "name": name,
            "protocol": self.dt_vars["protocol"].get() or "SSH",
            "port": int(port_text) if port_text else None,
            "username": self.dt_vars["username"].get().strip(),
            "password": self.dt_vars["password"].get(),
            "privilege_enabled": int(self.dt_vars["privilege_enabled"].get()),
            "enable_command": self.dt_vars["enable_command"].get().strip() or "enable",
            "enable_password": self.dt_vars["enable_password"].get(),
            "ftp_enabled": 0,
            "ftp_port": 21,
            "ftp_username": "",
            "ftp_password": "",
            "ftp_remote_dir": "/",
            "command_template_id": command_map.get(
                self.dt_vars["command_template"].get()
            ),
            "schedule_enabled": 0,
            "schedule_time": "02:00",
            "remark": self.dt_vars["remark"].get().strip(),
        }
        self.current_device_template_id = self.db.save_device_template(
            data, self.current_device_template_id
        )
        self.refresh_all()

    def delete_device_template(self):
        if not self.current_device_template_id:
            return
        if messagebox.askyesno("Delete", "Delete this device template?"):
            self.db.delete_device_template(self.current_device_template_id)
            self.current_device_template_id = None
            self.new_device_template()
            self.refresh_all()

    # ---------------- schedules / history ----------------

    def _build_schedule_tab(self):
        columns = ("device", "address", "time", "last")
        self.schedule_tree = ttk.Treeview(
            self.schedule_tab, columns=columns, show="headings"
        )
        for column, heading, width in [
            ("device", "Device", 260),
            ("address", "Address", 180),
            ("time", "Daily time", 120),
            ("last", "Last scheduled date", 160),
        ]:
            self.schedule_tree.heading(column, text=heading)
            self.schedule_tree.column(column, width=width, anchor="w")
        self.schedule_tree.pack(fill="both", expand=True, padx=4, pady=4)

    def refresh_schedule_view(self):
        self.schedule_tree.delete(*self.schedule_tree.get_children())
        for device in self.db.list_devices():
            if device.get("schedule_enabled"):
                self.schedule_tree.insert(
                    "",
                    "end",
                    values=(
                        device["name"],
                        device["ip"],
                        device.get("schedule_time") or "",
                        device.get("last_schedule_date") or "",
                    ),
                )

    def _build_run_tab(self):
        columns = ("started", "device", "trigger", "result", "summary", "path")
        self.run_tree = ttk.Treeview(
            self.run_tab, columns=columns, show="headings"
        )
        for column, heading, width in [
            ("started", "Started", 160),
            ("device", "Device", 220),
            ("trigger", "Trigger", 90),
            ("result", "Result", 80),
            ("summary", "Summary", 420),
            ("path", "Output", 360),
        ]:
            self.run_tree.heading(column, text=heading)
            self.run_tree.column(column, width=width, anchor="w")
        self.run_tree.pack(fill="both", expand=True, padx=4, pady=4)

    def refresh_run_view(self):
        self.run_tree.delete(*self.run_tree.get_children())
        for run in self.db.list_runs():
            if run.get("success") is None:
                result = "Running"
            else:
                result = "OK" if run["success"] else "Failed"
            self.run_tree.insert(
                "",
                "end",
                values=(
                    run["started_at"],
                    run["device_name"],
                    run["trigger_type"],
                    result,
                    run.get("summary") or "",
                    run.get("output_path") or "",
                ),
            )

    def _scheduler_tick(self):
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")
        due = []
        for device in self.db.list_devices():
            if not device.get("schedule_enabled"):
                continue
            if (device.get("schedule_time") or "") != current_time:
                continue
            if device.get("last_schedule_date") == today:
                continue
            if device["id"] in self.running_ids:
                continue
            self.db.mark_schedule_run(device["id"], today)
            due.append(device["id"])

        if due:
            self.log(f"Scheduled run: {len(due)} device(s).")
            self._run_device_ids(due, "schedule")

        self.root.after(15000, self._scheduler_tick)

    # ---------------- markdown import/export ----------------

    @staticmethod
    def _md_escape(value):
        return str(value or "").replace("|", "\\|").replace("\n", " ")

    @staticmethod
    def _split_md_row(line):
        text = line.strip().strip("|")
        values = re_split = []
        current = []
        escaped = False
        for char in text:
            if escaped:
                current.append(char)
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "|":
                re_split.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        re_split.append("".join(current).strip())
        return re_split

    def _read_md_table(self, path):
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
        for index in range(len(lines) - 1):
            if "|" not in lines[index]:
                continue
            separator = lines[index + 1].strip()
            if not separator.startswith("|") or "---" not in separator:
                continue
            headers = self._split_md_row(lines[index])
            rows = []
            for line in lines[index + 2 :]:
                if not line.strip().startswith("|"):
                    if rows:
                        break
                    continue
                values = self._split_md_row(line)
                if len(values) < len(headers):
                    values.extend([""] * (len(headers) - len(values)))
                rows.append(dict(zip(headers, values[: len(headers)])))
            return headers, rows
        raise ValueError("No Markdown table found.")

    def import_devices(self):
        path = filedialog.askopenfilename(
            title="Import device list",
            filetypes=[("Markdown", "*.md")],
        )
        if not path:
            return

        try:
            headers, rows = self._read_md_table(path)
            if "Device" not in headers or "Address" not in headers:
                raise ValueError("Required columns: Device, Address.")

            device_templates = {
                item["name"]: item for item in self.db.list_device_templates()
            }
            command_templates = {
                item["name"]: item["id"] for item in self.db.list_templates()
            }

            imported = 0
            for row in rows:
                name = row.get("Device", "").strip()
                address = row.get("Address", "").strip()
                if not name and not address:
                    continue
                if not name or not address:
                    raise ValueError("Every non-empty row needs Device and Address.")

                device_template = device_templates.get(
                    row.get("Device template", "").strip()
                )
                protocol = row.get("Protocol", "").strip()
                port = row.get("Port", "").strip()
                username = row.get("Username", "").strip()
                template_name = row.get("Command template", "").strip()

                if device_template:
                    protocol = protocol or device_template.get("protocol") or "SSH"
                    port = port or str(device_template.get("port") or "")
                    username = username or device_template.get("username") or ""
                    if not template_name:
                        template_name = device_template.get("command_template_name") or ""

                data = {
                    "name": name,
                    "ip": address,
                    "protocol": protocol or "SSH",
                    "port": int(port) if port else None,
                    "username": username,
                    "password": "",
                    "privilege_enabled": 0,
                    "enable_command": "enable",
                    "enable_password": "",
                    "ftp_enabled": 0,
                    "ftp_host": "",
                    "ftp_port": 21,
                    "ftp_username": "",
                    "ftp_password": "",
                    "ftp_remote_dir": "/",
                    "template_id": command_templates.get(template_name),
                    "schedule_enabled": 0,
                    "schedule_time": "02:00",
                    "remark": row.get("Remark", "").strip(),
                }
                self.db.save_device(data)
                imported += 1

            self.refresh_all()
            messagebox.showinfo("Import complete", f"Imported {imported} device(s).")
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

    def export_devices(self):
        path = filedialog.asksaveasfilename(
            title="Export device list",
            initialfile="AirOps-Desktop_devices.md",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md")],
        )
        if not path:
            return

        fields = [
            "Device",
            "Address",
            "Protocol",
            "Port",
            "Username",
            "Command template",
            "Schedule",
            "Remark",
        ]

        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# AirOps Desktop device export\n\n")
            handle.write(
                "> Passwords are intentionally excluded from exports.\n\n"
            )
            handle.write("| " + " | ".join(fields) + " |\n")
            handle.write("| " + " | ".join("---" for _ in fields) + " |\n")
            for device in self.db.list_devices():
                row = {
                    "Device": device["name"],
                    "Address": device["ip"],
                    "Protocol": device["protocol"],
                    "Port": device.get("port") or "",
                    "Username": device.get("username") or "",
                    "Command template": device.get("template_name") or "",
                    "Schedule": (
                        device.get("schedule_time") or ""
                        if device.get("schedule_enabled")
                        else ""
                    ),
                    "Remark": device.get("remark") or "",
                }
                handle.write(
                    "| "
                    + " | ".join(self._md_escape(row[field]) for field in fields)
                    + " |\n"
                )

        self.log(f"Device list exported: {path}")

    # ---------------- log and helpers ----------------

    def _build_log(self):
        frame = ttk.LabelFrame(self.root, text="Activity")
        frame.pack(fill="x", padx=8, pady=(4, 8))
        self.log_text = tk.Text(frame, height=6, wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set)

    def refresh_all(self):
        self.refresh_settings()
        self.refresh_command_templates()
        self.refresh_device_templates()
        self.refresh_devices()
        self.refresh_schedule_view()
        self.refresh_run_view()
