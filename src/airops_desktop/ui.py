import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .network import execute_device, test_tcp


class DeviceToolApp:
    def __init__(self, db):
        self.db = db
        self.root = tk.Tk()
        self.root.title("AirOps Desktop 0.1.0")
        self.root.geometry("1500x900")
        self.root.minsize(1180, 720)

        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=26)
        style.configure(
            "Treeview.Heading",
            font=("Microsoft YaHei UI", 9, "bold"),
        )

        self.selected_device_ids = set()
        self.current_device_id = None
        self.current_template_id = None
        self.current_device_template_id = None
        self.template_name_to_id = {}
        self.templates_cache = []
        self.device_templates_cache = []
        self.running_ids = set()
        self.device_sort_column = "name"
        self.device_sort_reverse = False
        self.device_heading_texts = {}
        self.status_render_job = None

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self._build_notebook()
        self._build_log_panel()

        self.refresh_templates()
        self.refresh_device_templates()
        self.db.reset_device_test_statuses()
        self.refresh_devices()
        self.refresh_schedule_view()
        self.refresh_run_view()

        self.root.after(15000, self._scheduler_tick)

    def run(self):
        self.root.mainloop()

    def log(self, message):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{stamp}] {message}\n")
        self.log_text.see("end")

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=8,
            pady=(6, 4),
        )

        self.device_tab = ttk.Frame(self.notebook)
        self.template_tab = ttk.Frame(self.notebook)
        self.device_template_tab = ttk.Frame(self.notebook)
        self.schedule_tab = ttk.Frame(self.notebook)
        self.run_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.device_tab, text="设备管理")
        self.notebook.add(self.template_tab, text="命令模板")
        self.notebook.add(self.device_template_tab, text="设备模板")
        self.notebook.add(self.schedule_tab, text="定时任务")
        self.notebook.add(self.run_tab, text="执行记录")

        self._build_device_tab()
        self._build_template_tab()
        self._build_device_template_tab()
        self._build_schedule_tab()
        self._build_run_tab()

    # ------------------------------------------------------------------
    # Device management
    # ------------------------------------------------------------------

    def _build_device_tab(self):
        self.device_tab.grid_rowconfigure(0, weight=1)
        self.device_tab.grid_columnconfigure(0, weight=3)
        self.device_tab.grid_columnconfigure(1, weight=2)

        left = ttk.LabelFrame(self.device_tab, text="设备列表")
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 3), pady=4)
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)

        columns = (
            "pick",
            "name",
            "ip",
            "protocol",
            "port",
            "template",
            "ftp",
            "status",
            "next",
        )
        self.device_tree = ttk.Treeview(
            left,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "pick": "全选",
            "name": "设备名称",
            "ip": "IP地址",
            "protocol": "协议",
            "port": "端口",
            "template": "命令模板",
            "ftp": "FTP目录",
            "status": "状态",
            "next": "下次执行时间",
        }
        self.device_heading_texts = dict(headings)
        widths = {
            "pick": 55,
            "name": 110,
            "ip": 125,
            "protocol": 70,
            "port": 60,
            "template": 145,
            "ftp": 100,
            "status": 90,
            "next": 150,
        }
        for column in columns:
            if column == "pick":
                self.device_tree.heading(
                    column,
                    text=headings[column],
                    command=self.toggle_select_all,
                )
            else:
                self.device_tree.heading(
                    column,
                    text=headings[column],
                    command=lambda c=column: self.sort_devices_by(c),
                )
            self.device_tree.column(
                column,
                width=widths[column],
                anchor="center",
            )

        self.device_tree.grid(row=0, column=0, sticky="nsew")

        yscroll = ttk.Scrollbar(
            left,
            orient="vertical",
            command=self._scroll_device_tree,
        )
        yscroll.grid(row=0, column=1, sticky="ns")
        self.device_tree.configure(yscrollcommand=yscroll.set)

        self.status_canvas = tk.Canvas(
            self.device_tree,
            highlightthickness=0,
            borderwidth=0,
            background="SystemWindow",
        )
        self.status_canvas.bind("<Button-1>", self._on_status_canvas_click)

        self.device_tree.bind("<Button-1>", self._on_device_tree_click)
        self.device_tree.bind(
            "<<TreeviewSelect>>",
            self._on_device_selected,
        )
        self.device_tree.bind(
            "<Configure>",
            self._schedule_status_cell_render,
            add="+",
        )
        self.device_tree.bind(
            "<MouseWheel>",
            self._schedule_status_cell_render,
            add="+",
        )
        self.device_tree.bind(
            "<ButtonRelease-1>",
            self._schedule_status_cell_render,
            add="+",
        )

        toolbar = ttk.Frame(left)
        toolbar.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 2),
        )
        for text, command in (
            ("新增设备", self.new_device),
            ("从设备模板新增", self.new_device_from_template),
            ("删除设备", self.delete_device),
            ("测试连通性", self.test_selected_devices),
            ("导入设备(MD)", self.import_devices),
            ("下载MD模板", self.save_device_import_template),
            ("导出设备(MD)", self.export_devices),
            ("开始执行", self.execute_selected_devices),
        ):
            ttk.Button(
                toolbar,
                text=text,
                command=command,
            ).pack(side="left", padx=3)

        right = ttk.LabelFrame(
            self.device_tab,
            text="设备详细配置（选中设备后可编辑）",
        )
        right.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(3, 4),
            pady=4,
        )
        right.grid_columnconfigure(1, weight=1)
        right.grid_columnconfigure(3, weight=1)

        self.device_vars = {
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
            "template": tk.StringVar(),
            "schedule_enabled": tk.BooleanVar(),
            "schedule_time": tk.StringVar(value="02:00"),
            "remark": tk.StringVar(),
        }

        self._detail_entry(right, 0, 0, "设备名称", "name", colspan=3)
        self._detail_entry(right, 1, 0, "IP地址", "ip", colspan=3)

        ttk.Label(right, text="协议：").grid(
            row=2, column=0, sticky="e", padx=5, pady=4
        )
        ttk.Combobox(
            right,
            textvariable=self.device_vars["protocol"],
            values=("SSH", "Telnet"),
            state="readonly",
            width=12,
        ).grid(
            row=2, column=1, sticky="ew", padx=5, pady=4
        )
        ttk.Label(right, text="端口：").grid(
            row=2, column=2, sticky="e", padx=5, pady=4
        )
        ttk.Entry(
            right,
            textvariable=self.device_vars["port"],
            width=10,
        ).grid(
            row=2, column=3, sticky="ew", padx=5, pady=4
        )

        self._detail_entry(right, 3, 0, "用户名", "username")
        self._detail_entry(
            right, 3, 2, "密码", "password", password=True
        )

        ttk.Checkbutton(
            right,
            text="启用特权模式",
            variable=self.device_vars["privilege_enabled"],
        ).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            padx=8,
            pady=4,
        )
        self._detail_entry(
            right,
            4,
            2,
            "特权密码",
            "enable_password",
            password=True,
        )
        self._detail_entry(
            right,
            5,
            0,
            "特权命令",
            "enable_command",
            colspan=3,
        )

        ttk.Label(right, text="命令模板：").grid(
            row=6, column=0, sticky="e", padx=5, pady=4
        )
        self.template_combo = ttk.Combobox(
            right,
            textvariable=self.device_vars["template"],
            state="readonly",
        )
        self.template_combo.grid(
            row=6,
            column=1,
            columnspan=2,
            sticky="ew",
            padx=5,
            pady=4,
        )
        ttk.Button(
            right,
            text="管理模板",
            command=lambda: self.notebook.select(self.template_tab),
        ).grid(
            row=6, column=3, sticky="ew", padx=5, pady=4
        )

        ttk.Checkbutton(
            right,
            text="启用FTP下载",
            variable=self.device_vars["ftp_enabled"],
        ).grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="w",
            padx=8,
            pady=4,
        )
        self._detail_entry(
            right,
            7,
            2,
            "FTP目录",
            "ftp_remote_dir",
        )
        self._detail_entry(right, 8, 0, "FTP地址", "ftp_host")
        self._detail_entry(right, 8, 2, "FTP端口", "ftp_port")
        self._detail_entry(right, 9, 0, "FTP用户", "ftp_username")
        self._detail_entry(
            right,
            9,
            2,
            "FTP密码",
            "ftp_password",
            password=True,
        )

        ttk.Checkbutton(
            right,
            text="启用定时执行",
            variable=self.device_vars["schedule_enabled"],
        ).grid(
            row=10,
            column=0,
            columnspan=2,
            sticky="w",
            padx=8,
            pady=4,
        )
        ttk.Label(right, text="时间：").grid(
            row=10, column=2, sticky="e", padx=5, pady=4
        )
        time_box = ttk.Frame(right)
        time_box.grid(
            row=10, column=3, sticky="ew", padx=5, pady=4
        )
        ttk.Entry(
            time_box,
            textvariable=self.device_vars["schedule_time"],
            width=8,
        ).pack(side="left", fill="x", expand=True)
        ttk.Label(time_box, text="  每天").pack(side="left")

        ttk.Label(right, text="备注：").grid(
            row=11, column=0, sticky="e", padx=5, pady=4
        )
        ttk.Entry(
            right,
            textvariable=self.device_vars["remark"],
        ).grid(
            row=11,
            column=1,
            columnspan=3,
            sticky="ew",
            padx=5,
            pady=4,
        )

        buttons = ttk.Frame(right)
        buttons.grid(
            row=12,
            column=0,
            columnspan=4,
            sticky="e",
            padx=6,
            pady=(12, 6),
        )
        ttk.Button(
            buttons,
            text="保存",
            width=10,
            command=self.save_device,
        ).pack(side="left", padx=3)
        ttk.Button(
            buttons,
            text="保存为设备模板",
            command=self.save_current_as_device_template,
        ).pack(side="left", padx=3)
        ttk.Button(
            buttons,
            text="新建",
            width=10,
            command=self.new_device,
        ).pack(side="left", padx=3)
        ttk.Button(
            buttons,
            text="删除",
            width=10,
            command=self.delete_device,
        ).pack(side="left", padx=3)
        ttk.Button(
            buttons,
            text="测试连接",
            width=10,
            command=self.test_selected_devices,
        ).pack(side="left", padx=3)

    def _detail_entry(
        self,
        parent,
        row,
        column,
        label,
        key,
        password=False,
        colspan=1,
    ):
        ttk.Label(parent, text=label + "：").grid(
            row=row,
            column=column,
            sticky="e",
            padx=5,
            pady=4,
        )
        ttk.Entry(
            parent,
            textvariable=self.device_vars[key],
            show="*" if password else "",
        ).grid(
            row=row,
            column=column + 1,
            columnspan=colspan,
            sticky="ew",
            padx=5,
            pady=4,
        )

    @staticmethod
    def _status_display(value):
        mapping = {
            "Not tested": "未测试",
            "Reachable": "正常",
            "Unreachable": "连接失败",
            "OK": "正常",
            "Failed": "执行失败",
        }
        return mapping.get(value or "", value or "未测试")

    def _update_select_all_heading(self):
        current_ids = {
            int(item) for item in self.device_tree.get_children()
        }
        all_selected = bool(current_ids) and current_ids.issubset(
            self.selected_device_ids
        )
        self.device_tree.heading(
            "pick",
            text="取消全选" if all_selected else "全选",
            command=self.toggle_select_all,
        )

    def _update_device_sort_headings(self):
        for column, base_text in self.device_heading_texts.items():
            if column == "pick":
                continue
            suffix = ""
            if column == self.device_sort_column:
                suffix = " ▼" if self.device_sort_reverse else " ▲"
            self.device_tree.heading(
                column,
                text=base_text + suffix,
                command=lambda c=column: self.sort_devices_by(c),
            )

    @staticmethod
    def _ip_sort_key(value):
        try:
            return tuple(int(part) for part in str(value).split("."))
        except (TypeError, ValueError):
            return (999, 999, 999, 999)

    def _device_sort_key(self, device):
        column = self.device_sort_column
        if column == "name":
            return (device.get("name") or "").lower()
        if column == "ip":
            return self._ip_sort_key(device.get("ip") or "")
        if column == "protocol":
            return (device.get("protocol") or "").lower()
        if column == "port":
            try:
                return int(device.get("port") or 0)
            except (TypeError, ValueError):
                return 0
        if column == "template":
            return (device.get("template_name") or "").lower()
        if column == "ftp":
            return (device.get("ftp_remote_dir") or "").lower()
        if column == "status":
            return self._status_display(device.get("last_status"))
        if column == "next":
            return self._next_run_text(device)
        return (device.get("name") or "").lower()

    def sort_devices_by(self, column):
        if column == self.device_sort_column:
            self.device_sort_reverse = not self.device_sort_reverse
        else:
            self.device_sort_column = column
            self.device_sort_reverse = False
        self.refresh_devices()

    def toggle_select_all(self):
        current_ids = {
            int(item) for item in self.device_tree.get_children()
        }
        if not current_ids:
            return
        if current_ids.issubset(self.selected_device_ids):
            self.selected_device_ids.difference_update(current_ids)
        else:
            self.selected_device_ids.update(current_ids)
        self.refresh_devices()

    def _on_device_tree_click(self, event):
        region = self.device_tree.identify_region(event.x, event.y)
        row_id = self.device_tree.identify_row(event.y)
        column = self.device_tree.identify_column(event.x)
        if region == "cell" and row_id and column == "#1":
            device_id = int(row_id)
            if device_id in self.selected_device_ids:
                self.selected_device_ids.discard(device_id)
            else:
                self.selected_device_ids.add(device_id)
            self.refresh_devices()
            return "break"
        return None

    def _on_device_selected(self, _event=None):
        selected = self.device_tree.selection()
        if not selected:
            return
        self.load_device(int(selected[0]))
        self._schedule_status_cell_render()

    def _schedule_status_cell_render(self, _event=None):
        if self.status_render_job is not None:
            return
        self.status_render_job = self.root.after(
            16,
            self._run_status_cell_render,
        )

    def _run_status_cell_render(self):
        self.status_render_job = None
        self._render_status_cells()

    def _scroll_device_tree(self, *args):
        self.device_tree.yview(*args)
        self._schedule_status_cell_render()

    def _on_status_canvas_click(self, event):
        if not self.status_canvas.winfo_ismapped():
            return
        canvas_y = self.status_canvas.winfo_y()
        item_id = self.device_tree.identify_row(canvas_y + event.y)
        if item_id:
            self.device_tree.selection_set(item_id)
            self.device_tree.focus(item_id)
            self.load_device(int(item_id))
            self._schedule_status_cell_render()

    def _render_status_cells(self):
        if not self.device_tree.winfo_exists():
            return

        visible = []
        tree_height = self.device_tree.winfo_height()
        for item_id in self.device_tree.get_children():
            bbox = self.device_tree.bbox(item_id, "status")
            if not bbox:
                continue
            x, y, width, height = bbox
            if y < 0 or y + height > tree_height:
                continue
            visible.append((item_id, x, y, width, height))

        if not visible:
            self.status_canvas.place_forget()
            return

        left = visible[0][1]
        top = min(item[2] for item in visible)
        width = visible[0][3]
        bottom = min(
            tree_height,
            max(item[2] + item[4] for item in visible),
        )
        height = max(1, bottom - top)

        self.status_canvas.place(
            x=left,
            y=top,
            width=width,
            height=height,
        )
        self.status_canvas.delete("all")

        selected_items = set(self.device_tree.selection())
        for item_id, _x, y, cell_width, cell_height in visible:
            relative_y = y - top
            status = self.device_tree.set(item_id, "status") or "未测试"
            selected = item_id in selected_items

            if selected:
                foreground = "SystemHighlightText"
                background = "SystemHighlight"
            else:
                background = "SystemWindow"
                if status == "正常":
                    foreground = "#17823B"
                elif status in ("连接失败", "执行失败"):
                    foreground = "#C62828"
                else:
                    foreground = "SystemWindowText"

            self.status_canvas.create_rectangle(
                0,
                relative_y,
                cell_width,
                relative_y + cell_height,
                fill=background,
                outline=background,
            )
            self.status_canvas.create_text(
                cell_width / 2,
                relative_y + cell_height / 2,
                text=status,
                fill=foreground,
                font=("Microsoft YaHei UI", 9),
                anchor="center",
            )

    def refresh_devices(self):
        selected = set(self.selected_device_ids)
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)

        devices = self.db.list_devices()
        devices.sort(
            key=self._device_sort_key,
            reverse=self.device_sort_reverse,
        )

        for device in devices:
            checked = "☑" if device["id"] in selected else "☐"
            self.device_tree.insert(
                "",
                "end",
                iid=str(device["id"]),
                values=(
                    checked,
                    device["name"],
                    device["ip"],
                    device["protocol"],
                    device.get("port") or "",
                    device.get("template_name") or "",
                    device.get("ftp_remote_dir") or "",
                    self._status_display(device.get("last_status")),
                    self._next_run_text(device),
                ),
            )

        self._update_select_all_heading()
        self._update_device_sort_headings()
        self._schedule_status_cell_render()
        self.refresh_schedule_view()

    def _next_run_text(self, device):
        if not int(device.get("schedule_enabled") or 0):
            return "-"
        try:
            hour, minute = map(
                int,
                (device.get("schedule_time") or "02:00").split(":"),
            )
            now = datetime.now()
            run_at = now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
            if run_at <= now:
                run_at += timedelta(days=1)
            return run_at.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "时间格式错误"

    def new_device(self):
        self.current_device_id = None
        settings = self.db.get_settings()
        for key, variable in self.device_vars.items():
            if isinstance(variable, tk.BooleanVar):
                variable.set(False)
            else:
                variable.set("")

        self.device_vars["protocol"].set("SSH")
        self.device_vars["port"].set(settings.get("ssh_port", "22"))
        self.device_vars["username"].set(settings.get("username", ""))
        self.device_vars["password"].set(settings.get("password", ""))
        self.device_vars["enable_command"].set("enable")
        self.device_vars["ftp_port"].set(settings.get("ftp_port", "21"))
        self.device_vars["ftp_remote_dir"].set(
            settings.get("ftp_remote_dir", "/")
        )
        self.device_vars["schedule_time"].set("02:00")
        self.device_tree.selection_remove(self.device_tree.selection())
        self._schedule_status_cell_render()

    def load_device(self, device_id):
        device = self.db.get_device(device_id)
        if not device:
            return
        self.current_device_id = device_id

        template = self.db.get_template(device.get("template_id"))
        values = {
            "name": device.get("name") or "",
            "ip": device.get("ip") or "",
            "protocol": device.get("protocol") or "SSH",
            "port": device.get("port") or "",
            "username": device.get("username") or "",
            "password": device.get("password") or "",
            "privilege_enabled": bool(device.get("privilege_enabled")),
            "enable_command": device.get("enable_command") or "enable",
            "enable_password": device.get("enable_password") or "",
            "ftp_enabled": bool(device.get("ftp_enabled")),
            "ftp_host": device.get("ftp_host") or "",
            "ftp_port": device.get("ftp_port") or "",
            "ftp_username": device.get("ftp_username") or "",
            "ftp_password": device.get("ftp_password") or "",
            "ftp_remote_dir": device.get("ftp_remote_dir") or "/",
            "template": template["name"] if template else "",
            "schedule_enabled": bool(device.get("schedule_enabled")),
            "schedule_time": device.get("schedule_time") or "02:00",
            "remark": device.get("remark") or "",
        }
        for key, value in values.items():
            self.device_vars[key].set(value)

    def _collect_device_form(self):
        name = self.device_vars["name"].get().strip()
        ip = self.device_vars["ip"].get().strip()
        if not name:
            raise ValueError("设备名称不能为空")
        if not ip:
            raise ValueError("IP地址不能为空")

        schedule_time = (
            self.device_vars["schedule_time"].get().strip() or "02:00"
        )
        datetime.strptime(schedule_time, "%H:%M")

        port_text = self.device_vars["port"].get().strip()
        ftp_port_text = self.device_vars["ftp_port"].get().strip()

        return {
            "name": name,
            "ip": ip,
            "protocol": self.device_vars["protocol"].get() or "SSH",
            "port": int(port_text) if port_text else None,
            "username": self.device_vars["username"].get().strip(),
            "password": self.device_vars["password"].get(),
            "privilege_enabled": int(
                self.device_vars["privilege_enabled"].get()
            ),
            "enable_command": (
                self.device_vars["enable_command"].get().strip()
                or "enable"
            ),
            "enable_password": self.device_vars["enable_password"].get(),
            "ftp_enabled": int(self.device_vars["ftp_enabled"].get()),
            "ftp_host": self.device_vars["ftp_host"].get().strip(),
            "ftp_port": int(ftp_port_text) if ftp_port_text else None,
            "ftp_username": self.device_vars["ftp_username"].get().strip(),
            "ftp_password": self.device_vars["ftp_password"].get(),
            "ftp_remote_dir": (
                self.device_vars["ftp_remote_dir"].get().strip() or "/"
            ),
            "template_id": self.template_name_to_id.get(
                self.device_vars["template"].get()
            ),
            "schedule_enabled": int(
                self.device_vars["schedule_enabled"].get()
            ),
            "schedule_time": schedule_time,
            "remark": self.device_vars["remark"].get().strip(),
        }

    def save_device(self):
        try:
            data = self._collect_device_form()
            self.current_device_id = self.db.save_device(
                data,
                self.current_device_id,
            )
            self.refresh_devices()
            if self.device_tree.exists(str(self.current_device_id)):
                self.device_tree.selection_set(str(self.current_device_id))
            self.log(f"设备已保存: {data['name']}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def delete_device(self):
        if not self.current_device_id:
            messagebox.showinfo("提示", "请先选择设备")
            return
        device = self.db.get_device(self.current_device_id)
        if not device:
            return
        if messagebox.askyesno(
            "确认删除",
            f"确定删除设备 {device['name']}？",
        ):
            self.db.delete_device(self.current_device_id)
            self.selected_device_ids.discard(self.current_device_id)
            self.current_device_id = None
            self.new_device()
            self.refresh_devices()
            self.refresh_run_view()

    def test_selected_devices(self):
        ids = list(self.selected_device_ids)
        if not ids and self.current_device_id:
            ids = [self.current_device_id]
        if not ids:
            messagebox.showinfo("提示", "请先勾选设备或选择当前设备")
            return

        settings = self.db.get_settings()
        devices = [self.db.get_device(device_id) for device_id in ids]
        devices = [device for device in devices if device]

        def worker():
            with ThreadPoolExecutor(
                max_workers=min(32, max(1, len(devices)))
            ) as pool:
                future_map = {}
                for device in devices:
                    port = device.get("port")
                    if not port:
                        port = (
                            settings["ssh_port"]
                            if (device.get("protocol") or "SSH").upper() == "SSH"
                            else settings["telnet_port"]
                        )
                    future = pool.submit(
                        test_tcp,
                        device["ip"],
                        port,
                        settings["connect_timeout"],
                    )
                    future_map[future] = device

                for future in as_completed(future_map):
                    device = future_map[future]
                    try:
                        future.result()
                        status = "Reachable"
                        message = "可达"
                    except Exception:
                        status = "Unreachable"
                        message = "不可达"
                    self.db.update_device_status(device["id"], status)
                    self.root.after(
                        0,
                        self.log,
                        f"{device['name']} ({device['ip']}): {message}",
                    )
                    self.root.after(0, self.refresh_devices)

        threading.Thread(target=worker, daemon=True).start()

    def execute_selected_devices(self):
        ids = list(self.selected_device_ids)
        if not ids:
            messagebox.showinfo("提示", "请先勾选需要执行的设备")
            return
        self._run_device_ids(ids, "manual")

    def _run_device_ids(self, ids, trigger_type):
        ids = [
            device_id
            for device_id in ids
            if device_id not in self.running_ids
        ]
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
                result = execute_device(
                    device,
                    template,
                    settings,
                    trigger_type,
                    self.db,
                    lambda message: self.root.after(
                        0,
                        self.log,
                        message,
                    ),
                    batch_stamp=batch_stamp,
                )
                return device, result

            try:
                with ThreadPoolExecutor(
                    max_workers=min(16, len(ids))
                ) as pool:
                    futures = {
                        pool.submit(run_one, device_id): device_id
                        for device_id in ids
                    }
                    for future in as_completed(futures):
                        device_id = futures[future]
                        try:
                            device, result = future.result()
                            ok, summary, _path = result
                            self.root.after(
                                0,
                                self.log,
                                f"{device['name']}: "
                                f"{'完成' if ok else '失败'} - {summary}",
                            )
                        except Exception as exc:
                            self.root.after(
                                0,
                                self.log,
                                f"设备 {device_id}: "
                                f"{type(exc).__name__}: {exc}",
                            )
                        finally:
                            self.running_ids.discard(device_id)
                            self.root.after(0, self.refresh_devices)
                            self.root.after(0, self.refresh_run_view)
            finally:
                for device_id in ids:
                    self.running_ids.discard(device_id)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Command templates
    # ------------------------------------------------------------------

    def _build_template_tab(self):
        self.template_tab.grid_rowconfigure(0, weight=1)
        self.template_tab.grid_columnconfigure(0, weight=1)
        self.template_tab.grid_columnconfigure(1, weight=3)

        left = ttk.LabelFrame(self.template_tab, text="模板列表")
        left.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(4, 3),
            pady=4,
        )
        self.template_list = tk.Listbox(left, exportselection=False)
        self.template_list.pack(
            fill="both",
            expand=True,
            padx=6,
            pady=6,
        )
        self.template_list.bind(
            "<<ListboxSelect>>",
            self._on_template_selected,
        )

        left_bar = ttk.Frame(left)
        left_bar.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(
            left_bar,
            text="新增模板",
            command=self.new_template,
        ).pack(side="left", padx=3)
        ttk.Button(
            left_bar,
            text="删除模板",
            command=self.delete_template,
        ).pack(side="left", padx=3)

        right = ttk.LabelFrame(self.template_tab, text="模板内容")
        right.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(3, 4),
            pady=4,
        )
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(1, weight=1)

        self.template_name_var = tk.StringVar()
        self.template_desc_var = tk.StringVar()

        ttk.Label(right, text="模板名称：").grid(
            row=0, column=0, sticky="e", padx=6, pady=5
        )
        ttk.Entry(
            right,
            textvariable=self.template_name_var,
            width=30,
        ).grid(
            row=0, column=1, sticky="ew", padx=6, pady=5
        )
        ttk.Button(
            right,
            text="保存命令模板",
            command=self.save_template,
        ).grid(
            row=0, column=2, sticky="ew", padx=(0, 6), pady=5
        )

        ttk.Label(right, text="说明：").grid(
            row=1, column=0, sticky="e", padx=6, pady=5
        )
        ttk.Entry(
            right,
            textvariable=self.template_desc_var,
        ).grid(
            row=1, column=1, sticky="ew", padx=6, pady=5
        )
        ttk.Button(
            right,
            text="导入TXT",
            command=self.import_template,
        ).grid(
            row=1, column=2, sticky="ew", padx=(0, 6), pady=5
        )

        command_frame = ttk.LabelFrame(
            right,
            text="命令（每行一条，按顺序执行；# 开头为注释）",
        )
        command_frame.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="nsew",
            padx=6,
            pady=6,
        )
        command_frame.grid_rowconfigure(0, weight=1)
        command_frame.grid_columnconfigure(0, weight=1)

        self.template_text = tk.Text(command_frame, wrap="none")
        self.template_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(
            command_frame,
            orient="vertical",
            command=self.template_text.yview,
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.template_text.configure(yscrollcommand=scroll.set)

        bar = ttk.Frame(right)
        bar.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=6,
            pady=6,
        )
        ttk.Button(
            bar,
            text="应用到已勾选设备",
            command=self.apply_template_to_selected,
        ).pack(side="left", padx=3)

    def refresh_templates(self):
        self.templates_cache = self.db.list_templates()
        self.template_name_to_id = {
            item["name"]: item["id"]
            for item in self.templates_cache
        }
        names = list(self.template_name_to_id.keys())

        if hasattr(self, "template_combo"):
            self.template_combo["values"] = names
        if hasattr(self, "device_template_command_combo"):
            self.device_template_command_combo["values"] = names
        if hasattr(self, "template_list"):
            self.template_list.delete(0, "end")
            for item in self.templates_cache:
                self.template_list.insert("end", item["name"])

    def _on_template_selected(self, _event=None):
        selection = self.template_list.curselection()
        if not selection:
            return
        template = self.templates_cache[selection[0]]
        self.current_template_id = template["id"]
        self.template_name_var.set(template["name"])
        self.template_desc_var.set(template.get("description") or "")
        self.template_text.delete("1.0", "end")
        self.template_text.insert(
            "1.0",
            template.get("commands") or "",
        )

    def new_template(self):
        self.current_template_id = None
        self.template_name_var.set("")
        self.template_desc_var.set("")
        self.template_text.delete("1.0", "end")

    def save_template(self):
        name = self.template_name_var.get().strip()
        commands = self.template_text.get("1.0", "end").strip()
        if not name:
            messagebox.showerror("保存失败", "模板名称不能为空")
            return
        try:
            self.current_template_id = self.db.save_template(
                name,
                commands,
                self.template_desc_var.get().strip(),
                self.current_template_id,
            )
            self.refresh_templates()
            self.refresh_devices()
            self.log(f"命令模板已保存: {name}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def delete_template(self):
        if not self.current_template_id:
            return
        if messagebox.askyesno(
            "确认删除",
            "删除当前命令模板？已绑定设备会自动解除绑定。",
        ):
            self.db.delete_template(self.current_template_id)
            self.current_template_id = None
            self.new_template()
            self.refresh_templates()
            self.refresh_devices()

    def import_template(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("命令模板", "*.txt *.cmd"),
                ("所有文件", "*.*"),
            ]
        )
        if not path:
            return
        raw = Path(path).read_bytes()
        text = None
        for encoding in ("utf-8-sig", "gb18030", "gbk"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = raw.decode("utf-8", errors="replace")

        self.template_text.delete("1.0", "end")
        self.template_text.insert("1.0", text)
        if not self.template_name_var.get():
            self.template_name_var.set(Path(path).stem)

    def apply_template_to_selected(self):
        if not self.current_template_id:
            messagebox.showinfo("提示", "请先选择或保存命令模板")
            return
        if not self.selected_device_ids:
            messagebox.showinfo("提示", "请先在设备管理中勾选设备")
            return

        for device_id in list(self.selected_device_ids):
            device = self.db.get_device(device_id)
            device["template_id"] = self.current_template_id
            self.db.save_device(device, device_id)

        self.refresh_devices()
        self.log(
            f"命令模板已应用到 {len(self.selected_device_ids)} 台设备"
        )

    # ------------------------------------------------------------------
    # Device templates
    # ------------------------------------------------------------------

    def _build_device_template_tab(self):
        self.device_template_tab.grid_rowconfigure(0, weight=1)
        self.device_template_tab.grid_columnconfigure(0, weight=1)
        self.device_template_tab.grid_columnconfigure(1, weight=3)

        left = ttk.LabelFrame(
            self.device_template_tab,
            text="设备模板列表",
        )
        left.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(4, 3),
            pady=4,
        )
        self.device_template_list = tk.Listbox(
            left,
            exportselection=False,
        )
        self.device_template_list.pack(
            fill="both",
            expand=True,
            padx=6,
            pady=6,
        )
        self.device_template_list.bind(
            "<<ListboxSelect>>",
            self._on_device_template_selected,
        )

        left_bar = ttk.Frame(left)
        left_bar.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(
            left_bar,
            text="新增模板",
            command=self.new_device_template,
        ).pack(side="left", padx=3)
        ttk.Button(
            left_bar,
            text="删除模板",
            command=self.delete_device_template,
        ).pack(side="left", padx=3)

        right = ttk.LabelFrame(
            self.device_template_tab,
            text="设备模板配置",
        )
        right.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(3, 4),
            pady=4,
        )
        right.grid_columnconfigure(1, weight=1)
        right.grid_columnconfigure(3, weight=1)

        self.device_template_vars = {
            "name": tk.StringVar(),
            "protocol": tk.StringVar(value="SSH"),
            "port": tk.StringVar(value="22"),
            "username": tk.StringVar(),
            "password": tk.StringVar(),
            "privilege_enabled": tk.BooleanVar(),
            "enable_command": tk.StringVar(value="enable"),
            "enable_password": tk.StringVar(),
            "ftp_enabled": tk.BooleanVar(),
            "ftp_port": tk.StringVar(value="21"),
            "ftp_username": tk.StringVar(),
            "ftp_password": tk.StringVar(),
            "ftp_remote_dir": tk.StringVar(value="/"),
            "command_template": tk.StringVar(),
            "schedule_enabled": tk.BooleanVar(),
            "schedule_time": tk.StringVar(value="02:00"),
            "remark": tk.StringVar(),
        }

        ttk.Label(right, text="模板名称：").grid(
            row=0, column=0, sticky="e", padx=5, pady=4
        )
        ttk.Entry(
            right,
            textvariable=self.device_template_vars["name"],
        ).grid(
            row=0,
            column=1,
            columnspan=2,
            sticky="ew",
            padx=5,
            pady=4,
        )
        ttk.Button(
            right,
            text="保存设备模板",
            command=self.save_device_template,
        ).grid(
            row=0, column=3, sticky="ew", padx=5, pady=4
        )

        ttk.Label(right, text="协议：").grid(
            row=1, column=0, sticky="e", padx=5, pady=4
        )
        ttk.Combobox(
            right,
            textvariable=self.device_template_vars["protocol"],
            values=("SSH", "Telnet"),
            state="readonly",
        ).grid(
            row=1, column=1, sticky="ew", padx=5, pady=4
        )
        ttk.Label(right, text="端口：").grid(
            row=1, column=2, sticky="e", padx=5, pady=4
        )
        ttk.Entry(
            right,
            textvariable=self.device_template_vars["port"],
        ).grid(
            row=1, column=3, sticky="ew", padx=5, pady=4
        )

        self._device_template_entry(
            right, 2, 0, "用户名", "username"
        )
        self._device_template_entry(
            right, 2, 2, "密码", "password", password=True
        )
        ttk.Checkbutton(
            right,
            text="启用特权模式",
            variable=self.device_template_vars["privilege_enabled"],
        ).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="w",
            padx=8,
            pady=4,
        )
        self._device_template_entry(
            right,
            3,
            2,
            "特权密码",
            "enable_password",
            password=True,
        )
        self._device_template_entry(
            right,
            4,
            0,
            "特权命令",
            "enable_command",
            colspan=3,
        )

        ttk.Label(right, text="命令模板：").grid(
            row=5, column=0, sticky="e", padx=5, pady=4
        )
        self.device_template_command_combo = ttk.Combobox(
            right,
            textvariable=self.device_template_vars["command_template"],
            state="readonly",
        )
        self.device_template_command_combo.grid(
            row=5,
            column=1,
            columnspan=3,
            sticky="ew",
            padx=5,
            pady=4,
        )

        ttk.Checkbutton(
            right,
            text="启用FTP下载",
            variable=self.device_template_vars["ftp_enabled"],
        ).grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="w",
            padx=8,
            pady=4,
        )
        self._device_template_entry(
            right, 6, 2, "FTP目录", "ftp_remote_dir"
        )
        self._device_template_entry(
            right, 7, 0, "FTP端口", "ftp_port"
        )
        self._device_template_entry(
            right, 7, 2, "FTP用户", "ftp_username"
        )
        self._device_template_entry(
            right,
            8,
            0,
            "FTP密码",
            "ftp_password",
            password=True,
        )

        ttk.Checkbutton(
            right,
            text="默认启用定时执行",
            variable=self.device_template_vars["schedule_enabled"],
        ).grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="w",
            padx=8,
            pady=4,
        )
        self._device_template_entry(
            right, 9, 2, "执行时间", "schedule_time"
        )
        self._device_template_entry(
            right,
            10,
            0,
            "备注",
            "remark",
            colspan=3,
        )

        bar = ttk.Frame(right)
        bar.grid(
            row=11,
            column=0,
            columnspan=4,
            sticky="e",
            padx=6,
            pady=10,
        )
        ttk.Button(
            bar,
            text="应用到当前设备",
            command=self.apply_device_template_to_current,
        ).pack(side="left", padx=3)
        ttk.Button(
            bar,
            text="用此模板新建设备",
            command=self.new_device_from_selected_template,
        ).pack(side="left", padx=3)

    def _device_template_entry(
        self,
        parent,
        row,
        column,
        label,
        key,
        password=False,
        colspan=1,
    ):
        ttk.Label(parent, text=label + "：").grid(
            row=row,
            column=column,
            sticky="e",
            padx=5,
            pady=4,
        )
        ttk.Entry(
            parent,
            textvariable=self.device_template_vars[key],
            show="*" if password else "",
        ).grid(
            row=row,
            column=column + 1,
            columnspan=colspan,
            sticky="ew",
            padx=5,
            pady=4,
        )

    def refresh_device_templates(self):
        self.device_templates_cache = self.db.list_device_templates()
        if hasattr(self, "device_template_list"):
            self.device_template_list.delete(0, "end")
            for item in self.device_templates_cache:
                self.device_template_list.insert("end", item["name"])

    def _on_device_template_selected(self, _event=None):
        selection = self.device_template_list.curselection()
        if not selection:
            return
        item = self.device_templates_cache[selection[0]]
        self.current_device_template_id = item["id"]
        template = self.db.get_device_template(item["id"])
        if not template:
            return
        command_template = self.db.get_template(
            template.get("command_template_id")
        )

        values = {
            "name": template.get("name") or "",
            "protocol": template.get("protocol") or "SSH",
            "port": template.get("port") or "",
            "username": template.get("username") or "",
            "password": template.get("password") or "",
            "privilege_enabled": bool(
                template.get("privilege_enabled")
            ),
            "enable_command": template.get("enable_command") or "enable",
            "enable_password": template.get("enable_password") or "",
            "ftp_enabled": bool(template.get("ftp_enabled")),
            "ftp_port": template.get("ftp_port") or "",
            "ftp_username": template.get("ftp_username") or "",
            "ftp_password": template.get("ftp_password") or "",
            "ftp_remote_dir": template.get("ftp_remote_dir") or "/",
            "command_template": (
                command_template["name"] if command_template else ""
            ),
            "schedule_enabled": bool(
                template.get("schedule_enabled")
            ),
            "schedule_time": template.get("schedule_time") or "02:00",
            "remark": template.get("remark") or "",
        }
        for key, value in values.items():
            self.device_template_vars[key].set(value)

    def new_device_template(self):
        self.current_device_template_id = None
        settings = self.db.get_settings()
        for variable in self.device_template_vars.values():
            if isinstance(variable, tk.BooleanVar):
                variable.set(False)
            else:
                variable.set("")
        self.device_template_vars["protocol"].set("SSH")
        self.device_template_vars["port"].set(
            settings.get("ssh_port", "22")
        )
        self.device_template_vars["username"].set(
            settings.get("username", "")
        )
        self.device_template_vars["ftp_port"].set(
            settings.get("ftp_port", "21")
        )
        self.device_template_vars["ftp_remote_dir"].set(
            settings.get("ftp_remote_dir", "/")
        )
        self.device_template_vars["enable_command"].set("enable")
        self.device_template_vars["schedule_time"].set("02:00")

    def save_device_template(self):
        try:
            name = self.device_template_vars["name"].get().strip()
            if not name:
                raise ValueError("设备模板名称不能为空")

            schedule_time = (
                self.device_template_vars["schedule_time"].get().strip()
                or "02:00"
            )
            datetime.strptime(schedule_time, "%H:%M")
            port_text = self.device_template_vars["port"].get().strip()
            ftp_port_text = (
                self.device_template_vars["ftp_port"].get().strip()
            )

            data = {
                "name": name,
                "protocol": (
                    self.device_template_vars["protocol"].get()
                    or "SSH"
                ),
                "port": int(port_text) if port_text else None,
                "username": (
                    self.device_template_vars["username"].get().strip()
                ),
                "password": self.device_template_vars["password"].get(),
                "privilege_enabled": int(
                    self.device_template_vars[
                        "privilege_enabled"
                    ].get()
                ),
                "enable_command": (
                    self.device_template_vars["enable_command"]
                    .get()
                    .strip()
                    or "enable"
                ),
                "enable_password": (
                    self.device_template_vars["enable_password"].get()
                ),
                "ftp_enabled": int(
                    self.device_template_vars["ftp_enabled"].get()
                ),
                "ftp_port": (
                    int(ftp_port_text) if ftp_port_text else None
                ),
                "ftp_username": (
                    self.device_template_vars["ftp_username"]
                    .get()
                    .strip()
                ),
                "ftp_password": (
                    self.device_template_vars["ftp_password"].get()
                ),
                "ftp_remote_dir": (
                    self.device_template_vars["ftp_remote_dir"]
                    .get()
                    .strip()
                    or "/"
                ),
                "command_template_id": self.template_name_to_id.get(
                    self.device_template_vars[
                        "command_template"
                    ].get()
                ),
                "schedule_enabled": int(
                    self.device_template_vars[
                        "schedule_enabled"
                    ].get()
                ),
                "schedule_time": schedule_time,
                "remark": (
                    self.device_template_vars["remark"].get().strip()
                ),
            }
            self.current_device_template_id = (
                self.db.save_device_template(
                    data,
                    self.current_device_template_id,
                )
            )
            self.refresh_device_templates()
            self.log(f"设备模板已保存: {name}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def delete_device_template(self):
        if not self.current_device_template_id:
            return
        if messagebox.askyesno("确认删除", "删除当前设备模板？"):
            self.db.delete_device_template(
                self.current_device_template_id
            )
            self.current_device_template_id = None
            self.new_device_template()
            self.refresh_device_templates()

    def _device_template_to_device_form(self, template):
        command_template = self.db.get_template(
            template.get("command_template_id")
        )
        values = {
            "protocol": template.get("protocol") or "SSH",
            "port": template.get("port") or "",
            "username": template.get("username") or "",
            "password": template.get("password") or "",
            "privilege_enabled": bool(
                template.get("privilege_enabled")
            ),
            "enable_command": template.get("enable_command") or "enable",
            "enable_password": template.get("enable_password") or "",
            "ftp_enabled": bool(template.get("ftp_enabled")),
            "ftp_host": "",
            "ftp_port": template.get("ftp_port") or "",
            "ftp_username": template.get("ftp_username") or "",
            "ftp_password": template.get("ftp_password") or "",
            "ftp_remote_dir": template.get("ftp_remote_dir") or "/",
            "template": (
                command_template["name"] if command_template else ""
            ),
            "schedule_enabled": bool(
                template.get("schedule_enabled")
            ),
            "schedule_time": template.get("schedule_time") or "02:00",
            "remark": template.get("remark") or "",
        }
        for key, value in values.items():
            self.device_vars[key].set(value)

    def apply_device_template_to_current(self):
        if not self.current_device_template_id:
            messagebox.showinfo("提示", "请先选择设备模板")
            return
        template = self.db.get_device_template(
            self.current_device_template_id
        )
        if not template:
            return
        self._device_template_to_device_form(template)
        self.notebook.select(self.device_tab)

    def new_device_from_selected_template(self):
        if not self.current_device_template_id:
            messagebox.showinfo("提示", "请先选择设备模板")
            return
        template = self.db.get_device_template(
            self.current_device_template_id
        )
        self.new_device()
        self._device_template_to_device_form(template)
        self.notebook.select(self.device_tab)

    def new_device_from_template(self):
        templates = self.db.list_device_templates()
        if not templates:
            messagebox.showinfo("提示", "当前没有可用设备模板")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("从设备模板新增")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        names = [item["name"] for item in templates]
        selected_name = tk.StringVar(value=names[0])

        ttk.Label(dialog, text="设备模板：").grid(
            row=0, column=0, padx=10, pady=10
        )
        ttk.Combobox(
            dialog,
            textvariable=selected_name,
            values=names,
            state="readonly",
            width=32,
        ).grid(
            row=0, column=1, padx=10, pady=10
        )

        def confirm():
            chosen = next(
                (
                    item
                    for item in templates
                    if item["name"] == selected_name.get()
                ),
                None,
            )
            if not chosen:
                return
            dialog.destroy()
            self.new_device()
            self._device_template_to_device_form(chosen)

        ttk.Button(
            dialog,
            text="确定",
            command=confirm,
        ).grid(
            row=1, column=0, columnspan=2, pady=(0, 10)
        )

    def save_current_as_device_template(self):
        try:
            data = self._collect_device_form()
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("保存为设备模板")
        dialog.transient(self.root)
        dialog.grab_set()
        name_var = tk.StringVar(
            value=f"{data['name']}-模板" if data["name"] else ""
        )

        ttk.Label(dialog, text="模板名称：").grid(
            row=0, column=0, padx=10, pady=10
        )
        ttk.Entry(
            dialog,
            textvariable=name_var,
            width=32,
        ).grid(
            row=0, column=1, padx=10, pady=10
        )

        def confirm():
            template_name = name_var.get().strip()
            if not template_name:
                messagebox.showerror(
                    "保存失败",
                    "模板名称不能为空",
                    parent=dialog,
                )
                return

            template_data = {
                "name": template_name,
                "protocol": data["protocol"],
                "port": data["port"],
                "username": data["username"],
                "password": data["password"],
                "privilege_enabled": data["privilege_enabled"],
                "enable_command": data["enable_command"],
                "enable_password": data["enable_password"],
                "ftp_enabled": data["ftp_enabled"],
                "ftp_port": data["ftp_port"],
                "ftp_username": data["ftp_username"],
                "ftp_password": data["ftp_password"],
                "ftp_remote_dir": data["ftp_remote_dir"],
                "command_template_id": data["template_id"],
                "schedule_enabled": data["schedule_enabled"],
                "schedule_time": data["schedule_time"],
                "remark": data["remark"],
            }
            try:
                self.db.save_device_template(template_data)
                self.refresh_device_templates()
                dialog.destroy()
                self.log(f"设备模板已保存: {template_name}")
            except Exception as exc:
                messagebox.showerror(
                    "保存失败",
                    str(exc),
                    parent=dialog,
                )

        ttk.Button(
            dialog,
            text="保存",
            command=confirm,
        ).grid(
            row=1, column=0, columnspan=2, pady=(0, 10)
        )

    # ------------------------------------------------------------------
    # Schedules and runs
    # ------------------------------------------------------------------

    def _build_schedule_tab(self):
        self.schedule_tab.grid_rowconfigure(0, weight=1)
        self.schedule_tab.grid_columnconfigure(0, weight=1)

        columns = ("device", "ip", "time", "next", "last")
        self.schedule_tree = ttk.Treeview(
            self.schedule_tab,
            columns=columns,
            show="headings",
        )
        definitions = [
            ("device", "设备名称", 260),
            ("ip", "IP地址", 180),
            ("time", "每日执行时间", 140),
            ("next", "下次执行", 180),
            ("last", "最近定时执行日期", 180),
        ]
        for column, heading, width in definitions:
            self.schedule_tree.heading(column, text=heading)
            self.schedule_tree.column(
                column,
                width=width,
                anchor="center",
            )
        self.schedule_tree.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=6,
            pady=6,
        )

    def refresh_schedule_view(self):
        if not hasattr(self, "schedule_tree"):
            return
        self.schedule_tree.delete(
            *self.schedule_tree.get_children()
        )
        for device in self.db.list_devices():
            if not device.get("schedule_enabled"):
                continue
            self.schedule_tree.insert(
                "",
                "end",
                values=(
                    device["name"],
                    device["ip"],
                    device.get("schedule_time") or "",
                    self._next_run_text(device),
                    device.get("last_schedule_date") or "",
                ),
            )

    def _build_run_tab(self):
        self.run_tab.grid_rowconfigure(0, weight=1)
        self.run_tab.grid_columnconfigure(0, weight=1)

        columns = (
            "started",
            "device",
            "ip",
            "trigger",
            "result",
            "summary",
            "path",
        )
        self.run_tree = ttk.Treeview(
            self.run_tab,
            columns=columns,
            show="headings",
        )
        definitions = [
            ("started", "开始时间", 150),
            ("device", "设备名称", 180),
            ("ip", "IP地址", 130),
            ("trigger", "触发方式", 90),
            ("result", "结果", 80),
            ("summary", "摘要", 360),
            ("path", "结果目录", 320),
        ]
        for column, heading, width in definitions:
            self.run_tree.heading(column, text=heading)
            self.run_tree.column(
                column,
                width=width,
                anchor="w",
            )
        self.run_tree.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=6,
            pady=6,
        )

    def refresh_run_view(self):
        if not hasattr(self, "run_tree"):
            return
        self.run_tree.delete(*self.run_tree.get_children())
        for run in self.db.list_runs():
            if run.get("success") is None:
                result = "执行中"
            else:
                result = "成功" if run["success"] else "失败"
            self.run_tree.insert(
                "",
                "end",
                values=(
                    run["started_at"],
                    run["device_name"],
                    run["device_ip"],
                    "定时" if run["trigger_type"] == "schedule" else "手动",
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
            self.log(f"定时任务触发：{len(due)} 台设备")
            self._run_device_ids(due, "schedule")

        self.root.after(15000, self._scheduler_tick)

    # ------------------------------------------------------------------
    # Markdown import/export
    # ------------------------------------------------------------------

    @staticmethod
    def _md_escape(value):
        return (
            str(value or "")
            .replace("\\", "\\\\")
            .replace("|", "\\|")
            .replace("\n", " ")
        )

    @staticmethod
    def _md_split_row(line):
        text = line.strip().strip("|")
        values = []
        current = []
        escaped = False
        for char in text:
            if escaped:
                current.append(char)
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "|":
                values.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        values.append("".join(current).strip())
        return values

    @classmethod
    def _read_markdown_table(cls, path):
        lines = Path(path).read_text(
            encoding="utf-8-sig"
        ).splitlines()

        for index in range(len(lines) - 1):
            header_line = lines[index].strip()
            separator = lines[index + 1].strip()
            if "|" not in header_line:
                continue
            if "|" not in separator or "---" not in separator:
                continue

            headers = cls._md_split_row(header_line)
            rows = []
            for line in lines[index + 2 :]:
                if not line.strip().startswith("|"):
                    if rows:
                        break
                    continue
                values = cls._md_split_row(line)
                if len(values) < len(headers):
                    values.extend(
                        [""] * (len(headers) - len(values))
                    )
                rows.append(
                    dict(zip(headers, values[: len(headers)]))
                )
            return headers, rows

        raise ValueError("未找到有效的 Markdown 表格")

    @classmethod
    def _write_markdown_table(
        cls,
        path,
        title,
        fields,
        rows,
        notes=None,
    ):
        notes = notes or []
        with open(
            path,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            handle.write(f"# {title}\n\n")
            for note in notes:
                handle.write(f"> {note}\n")
            if notes:
                handle.write("\n")

            handle.write(
                "| "
                + " | ".join(cls._md_escape(item) for item in fields)
                + " |\n"
            )
            handle.write(
                "| "
                + " | ".join("---" for _ in fields)
                + " |\n"
            )
            for row in rows:
                handle.write(
                    "| "
                    + " | ".join(
                        cls._md_escape(row.get(field, ""))
                        for field in fields
                    )
                    + " |\n"
                )

    def save_device_import_template(self):
        path = filedialog.asksaveasfilename(
            title="保存设备导入模板",
            initialfile="AirOps-Desktop_设备导入模板.md",
            defaultextension=".md",
            filetypes=[("Markdown文件", "*.md")],
        )
        if not path:
            return

        fields = [
            "设备名称",
            "IP地址",
            "设备模板",
            "用户名",
            "登录密码",
            "特权密码",
            "备注",
        ]
        rows = [
            {"设备模板": "Generic SSH"},
            {"设备模板": "Generic Telnet"},
            {"设备模板": "Huawei VRP"},
        ]
        self._write_markdown_table(
            path,
            "AirOps Desktop 设备导入模板",
            fields,
            rows,
            notes=[
                "必填：设备名称、IP地址、设备模板。",
                "密码可留空，导入后再在软件中填写。",
                "复制对应设备模板行即可批量增加设备；不要修改表头名称。",
            ],
        )
        messagebox.showinfo(
            "模板已生成",
            "Markdown 设备导入模板已生成。",
        )

    def import_devices(self):
        path = filedialog.askopenfilename(
            title="导入设备列表",
            filetypes=[("Markdown文件", "*.md")],
        )
        if not path:
            return

        self.refresh_templates()
        self.refresh_device_templates()
        device_template_map = {
            item["name"]: self.db.get_device_template(item["id"])
            for item in self.device_templates_cache
        }

        imported = 0
        skipped = 0
        try:
            headers, rows = self._read_markdown_table(path)
            if "设备名称" not in headers or "IP地址" not in headers:
                raise ValueError(
                    "MD表格至少需要“设备名称”和“IP地址”两列。"
                )

            for row in rows:
                name = row.get("设备名称", "").strip()
                ip = row.get("IP地址", "").strip()
                if not name and not ip:
                    skipped += 1
                    continue
                if not name or not ip:
                    raise ValueError(
                        "每一条非空记录都必须填写设备名称和IP地址。"
                    )

                template_name = row.get("设备模板", "").strip()
                device_template = device_template_map.get(template_name)

                if device_template:
                    command_template = self.db.get_template(
                        device_template.get("command_template_id")
                    )
                    data = {
                        "name": name,
                        "ip": ip,
                        "protocol": (
                            device_template.get("protocol") or "SSH"
                        ),
                        "port": device_template.get("port"),
                        "username": (
                            row.get("用户名", "").strip()
                            or device_template.get("username")
                            or ""
                        ),
                        "password": (
                            row.get("登录密码", "")
                            or device_template.get("password")
                            or ""
                        ),
                        "privilege_enabled": int(
                            device_template.get(
                                "privilege_enabled"
                            )
                            or 0
                        ),
                        "enable_command": (
                            device_template.get("enable_command")
                            or "enable"
                        ),
                        "enable_password": (
                            row.get("特权密码", "")
                            or device_template.get(
                                "enable_password"
                            )
                            or ""
                        ),
                        "ftp_enabled": int(
                            device_template.get("ftp_enabled") or 0
                        ),
                        "ftp_host": "",
                        "ftp_port": device_template.get("ftp_port"),
                        "ftp_username": (
                            device_template.get("ftp_username") or ""
                        ),
                        "ftp_password": (
                            device_template.get("ftp_password") or ""
                        ),
                        "ftp_remote_dir": (
                            device_template.get("ftp_remote_dir")
                            or "/"
                        ),
                        "template_id": (
                            command_template["id"]
                            if command_template
                            else None
                        ),
                        "schedule_enabled": int(
                            device_template.get(
                                "schedule_enabled"
                            )
                            or 0
                        ),
                        "schedule_time": (
                            device_template.get("schedule_time")
                            or "02:00"
                        ),
                        "remark": row.get("备注", "").strip(),
                    }
                else:
                    settings = self.db.get_settings()
                    data = {
                        "name": name,
                        "ip": ip,
                        "protocol": "SSH",
                        "port": int(settings["ssh_port"]),
                        "username": row.get("用户名", "").strip(),
                        "password": row.get("登录密码", ""),
                        "privilege_enabled": 0,
                        "enable_command": "enable",
                        "enable_password": row.get("特权密码", ""),
                        "ftp_enabled": 0,
                        "ftp_host": "",
                        "ftp_port": int(settings["ftp_port"]),
                        "ftp_username": "",
                        "ftp_password": "",
                        "ftp_remote_dir": "/",
                        "template_id": None,
                        "schedule_enabled": 0,
                        "schedule_time": "02:00",
                        "remark": row.get("备注", "").strip(),
                    }

                self.db.save_device(data)
                imported += 1

            self.refresh_devices()
            self.log(
                f"设备MD列表导入完成: {imported} 台"
                + (
                    f"，跳过空白模板行 {skipped} 行"
                    if skipped
                    else ""
                )
            )
            messagebox.showinfo(
                "导入完成",
                f"成功导入 {imported} 台设备。",
            )
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def export_devices(self):
        path = filedialog.asksaveasfilename(
            title="导出设备列表",
            initialfile="AirOps-Desktop_设备列表.md",
            defaultextension=".md",
            filetypes=[("Markdown文件", "*.md")],
        )
        if not path:
            return

        fields = [
            "设备名称",
            "IP地址",
            "协议",
            "端口",
            "用户名",
            "命令模板",
            "启用定时",
            "执行时间",
            "备注",
        ]
        rows = []
        for device in self.db.list_devices():
            rows.append(
                {
                    "设备名称": device["name"],
                    "IP地址": device["ip"],
                    "协议": device["protocol"],
                    "端口": device.get("port") or "",
                    "用户名": device.get("username") or "",
                    "命令模板": device.get("template_name") or "",
                    "启用定时": int(
                        bool(device.get("schedule_enabled"))
                    ),
                    "执行时间": device.get("schedule_time") or "",
                    "备注": device.get("remark") or "",
                }
            )

        self._write_markdown_table(
            path,
            "AirOps Desktop 设备列表",
            fields,
            rows,
            notes=[
                "导出文件不包含登录密码、特权密码和FTP密码。",
                "如需备份完整凭据，请妥善备份本地 data 目录并做好访问控制。",
            ],
        )
        self.log(f"设备MD列表已导出: {path}")

    # ------------------------------------------------------------------
    # Bottom log
    # ------------------------------------------------------------------

    def _build_log_panel(self):
        frame = ttk.LabelFrame(self.root, text="执行结果 / 日志")
        frame.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=8,
            pady=(2, 8),
        )
        frame.grid_columnconfigure(0, weight=1)

        text_frame = ttk.Frame(frame)
        text_frame.grid(
            row=0,
            column=0,
            columnspan=4,
            sticky="ew",
            padx=6,
            pady=5,
        )
        text_frame.grid_columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            text_frame,
            height=6,
            wrap="word",
        )
        self.log_text.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=self.log_text.yview,
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        ttk.Button(
            frame,
            text="清空日志",
            command=lambda: self.log_text.delete("1.0", "end"),
        ).grid(
            row=1,
            column=1,
            padx=4,
            pady=(0, 5),
            sticky="e",
        )
        ttk.Button(
            frame,
            text="打开结果目录",
            command=self._open_result_dir,
        ).grid(
            row=1,
            column=2,
            padx=4,
            pady=(0, 5),
            sticky="e",
        )
        ttk.Button(
            frame,
            text="开始执行已勾选设备",
            command=self.execute_selected_devices,
        ).grid(
            row=1,
            column=3,
            padx=4,
            pady=(0, 5),
            sticky="e",
        )

    def _open_result_dir(self):
        result_dir = Path(
            self.db.get_settings().get("result_dir") or "results"
        )
        result_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(result_dir)
