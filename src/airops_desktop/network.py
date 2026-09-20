import ftplib
import re
import socket
import time
from datetime import datetime
from pathlib import Path

import paramiko


ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def decode_bytes(data):
    for encoding in ("utf-8", "gb18030", "gbk", "latin1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def clean_output(text):
    return ANSI_RE.sub("", text).replace("\r", "")


def test_tcp(host, port, timeout=5):
    with socket.create_connection((host, int(port)), timeout=float(timeout)):
        return True


def parse_commands(text):
    commands = []
    for line in (text or "").splitlines():
        command = line.strip()
        if command and not command.startswith("#"):
            commands.append(command)
    return commands


def _looks_like_cli_prompt(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return False
    tail = lines[-1]
    if len(tail) > 180:
        return False
    if re.fullmatch(r"<[^<>\r\n]{1,160}>", tail):
        return True
    if re.fullmatch(r"\[[^\[\]\r\n]{1,160}\]", tail):
        return True
    return bool(
        re.fullmatch(
            r"[A-Za-z0-9_.:/-]+(?:\s?\([^()\r\n]+\))*[>#]",
            tail,
        )
    )


def _command_read_policy(command, base_timeout):
    base = max(1.0, float(base_timeout))
    lowered = (command or "").strip().lower()

    if "running-config" in lowered or "current-configuration" in lowered:
        return {
            "hard_timeout": 3600.0,
            "idle_fallback": max(30.0, base),
            "first_byte_timeout": min(max(5.0, base), 30.0),
        }

    if "logging" in lowered or "logbuffer" in lowered:
        return {
            "hard_timeout": 900.0,
            "idle_fallback": max(15.0, min(base, 60.0)),
            "first_byte_timeout": min(max(5.0, base), 30.0),
        }

    return {
        "hard_timeout": max(60.0, base),
        "idle_fallback": min(max(8.0, base / 2.0), 30.0),
        "first_byte_timeout": min(max(3.0, base / 3.0), 10.0),
    }


def _tail_text(tail_bytes):
    return clean_output(decode_bytes(tail_bytes[-4096:]))


def _read_ssh_shell(
    shell,
    timeout=30,
    idle_after_prompt=0.20,
    idle_fallback=8.0,
    first_byte_timeout=3.0,
    hard_timeout=None,
):
    started = time.monotonic()
    last_data = started
    chunks = []
    tail = b""
    prompt_seen = False
    hard_limit = float(hard_timeout if hard_timeout is not None else timeout)

    while True:
        if shell.recv_ready():
            data = shell.recv(65535)
            if data:
                chunks.append(data)
                tail = (tail + data)[-4096:]
                last_data = time.monotonic()
                prompt_seen = _looks_like_cli_prompt(_tail_text(tail))
                continue

        now = time.monotonic()
        if prompt_seen and now - last_data >= idle_after_prompt:
            break
        if chunks and not prompt_seen and now - last_data >= idle_fallback:
            break
        if not chunks and now - started >= min(hard_limit, first_byte_timeout):
            break
        if now - started >= hard_limit:
            break
        time.sleep(0.05)

    return clean_output(decode_bytes(b"".join(chunks)))


def run_ssh(device, settings, commands, log):
    host = device["ip"]
    port = int(device.get("port") or settings["ssh_port"])
    username = device.get("username") or settings["username"]
    password = device.get("password") or settings["password"]
    timeout = float(settings["connect_timeout"])
    command_timeout = float(settings["command_timeout"])

    client = paramiko.SSHClient()
    # Offline-first does not mean host-key verification is solved.
    # v0.1 keeps compatibility behavior and documents this limitation.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    log(f"SSH connect {host}:{port}")
    client.connect(
        host,
        port=port,
        username=username,
        password=password,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
        look_for_keys=False,
        allow_agent=False,
    )

    shell = client.invoke_shell(width=240, height=1000)
    time.sleep(0.4)
    initial = _read_ssh_shell(shell, timeout=3, idle_fallback=0.5)
    output = [initial] if initial.strip() else []

    if int(device.get("privilege_enabled") or 0):
        enable_command = device.get("enable_command") or "enable"
        enable_password = device.get("enable_password") or ""
        log(f"Privilege mode: {enable_command}")
        shell.send(enable_command + "\n")
        text = _read_ssh_shell(shell, timeout=command_timeout)
        if text:
            output.append(text)

        lowered = text.lower()
        if "password" in lowered or "passwd" in lowered:
            if not enable_password:
                client.close()
                raise RuntimeError(
                    "Device requested a privilege password, but none is configured."
                )
            shell.send(enable_password + "\n")
            text = _read_ssh_shell(shell, timeout=command_timeout)
            if text:
                output.append(text)

    try:
        for index, command in enumerate(commands, 1):
            log(f"[{index}/{len(commands)}] {command}")
            if command.strip().lower() in ("ctrl+c", "^c"):
                shell.send("\x03")
            else:
                shell.send(command + "\n")

            policy = _command_read_policy(command, command_timeout)
            text = _read_ssh_shell(
                shell,
                timeout=command_timeout,
                hard_timeout=policy["hard_timeout"],
                idle_fallback=policy["idle_fallback"],
                first_byte_timeout=policy["first_byte_timeout"],
            )
            if text:
                output.append(text)
    finally:
        client.close()

    return "\n".join(part.rstrip() for part in output if part.strip()) + "\n"


def _set_telnet_window_size(tn, width=240, height=1000):
    try:
        import struct
        import telnetlib

        payload = struct.pack("!HH", int(width), int(height))

        def send_naws(sock):
            sock.sendall(
                telnetlib.IAC
                + telnetlib.SB
                + telnetlib.NAWS
                + payload
                + telnetlib.IAC
                + telnetlib.SE
            )

        def negotiate(sock, command, option):
            if option == telnetlib.NAWS and command == telnetlib.DO:
                sock.sendall(telnetlib.IAC + telnetlib.WILL + telnetlib.NAWS)
                send_naws(sock)
            elif command in (telnetlib.DO, telnetlib.DONT):
                sock.sendall(telnetlib.IAC + telnetlib.WONT + option)
            elif command in (telnetlib.WILL, telnetlib.WONT):
                sock.sendall(telnetlib.IAC + telnetlib.DONT + option)

        tn.set_option_negotiation_callback(negotiate)
        sock = tn.get_socket()
        sock.sendall(telnetlib.IAC + telnetlib.WILL + telnetlib.NAWS)
        send_naws(sock)
    except Exception:
        pass


def _telnet_login(tn, username, password):
    time.sleep(0.4)
    banner = tn.read_very_eager()
    lowered = banner.lower()

    sent_username = False
    if b"password" not in lowered and b"passwd" not in lowered and username:
        tn.write((username + "\r\n").encode())
        sent_username = True
        time.sleep(0.4)
        banner += tn.read_very_eager()
        lowered = banner.lower()

    if password and (
        b"password" in lowered
        or b"passwd" in lowered
        or sent_username
    ):
        tn.write((password + "\r\n").encode())
        time.sleep(0.5)
        banner += tn.read_very_eager()

    return clean_output(decode_bytes(banner))


def _read_telnet_idle(
    tn,
    timeout=30,
    idle_after_prompt=0.20,
    idle_fallback=8.0,
    first_byte_timeout=3.0,
    hard_timeout=None,
):
    started = time.monotonic()
    last_data = started
    chunks = []
    tail = b""
    prompt_seen = False
    hard_limit = float(hard_timeout if hard_timeout is not None else timeout)

    while True:
        data = tn.read_very_eager()
        if data:
            chunks.append(data)
            tail = (tail + data)[-4096:]
            last_data = time.monotonic()
            prompt_seen = _looks_like_cli_prompt(_tail_text(tail))
        else:
            now = time.monotonic()
            if prompt_seen and now - last_data >= idle_after_prompt:
                break
            if chunks and not prompt_seen and now - last_data >= idle_fallback:
                break
            if not chunks and now - started >= min(hard_limit, first_byte_timeout):
                break
            if now - started >= hard_limit:
                break
        time.sleep(0.05)

    return clean_output(decode_bytes(b"".join(chunks)))


def run_telnet(device, settings, commands, log):
    import telnetlib

    host = device["ip"]
    port = int(device.get("port") or settings["telnet_port"])
    username = device.get("username") or settings["username"]
    password = device.get("password") or settings["password"]
    timeout = float(settings["connect_timeout"])
    command_timeout = float(settings["command_timeout"])

    log(f"Telnet connect {host}:{port}")
    tn = telnetlib.Telnet(host, port, timeout)
    _set_telnet_window_size(tn, width=240, height=1000)

    initial = _telnet_login(tn, username, password)
    output = [initial] if initial.strip() else []

    if int(device.get("privilege_enabled") or 0):
        enable_command = device.get("enable_command") or "enable"
        enable_password = device.get("enable_password") or ""
        log(f"Privilege mode: {enable_command}")
        tn.write((enable_command + "\r\n").encode())
        text = _read_telnet_idle(tn, timeout=command_timeout)
        if text:
            output.append(text)

        lowered = text.lower()
        if "password" in lowered or "passwd" in lowered:
            if not enable_password:
                tn.close()
                raise RuntimeError(
                    "Device requested a privilege password, but none is configured."
                )
            tn.write((enable_password + "\r\n").encode())
            text = _read_telnet_idle(tn, timeout=command_timeout)
            if text:
                output.append(text)

    try:
        for index, command in enumerate(commands, 1):
            log(f"[{index}/{len(commands)}] {command}")
            if command.strip().lower() in ("ctrl+c", "^c"):
                tn.write(b"\x03")
            else:
                tn.write((command + "\r\n").encode())

            policy = _command_read_policy(command, command_timeout)
            text = _read_telnet_idle(
                tn,
                timeout=command_timeout,
                hard_timeout=policy["hard_timeout"],
                idle_fallback=policy["idle_fallback"],
                first_byte_timeout=policy["first_byte_timeout"],
            )
            if text:
                output.append(text)
    finally:
        tn.close()

    return "\n".join(part.rstrip() for part in output if part.strip()) + "\n"


def download_ftp(device, settings, target_dir, log):
    if not int(device.get("ftp_enabled") or 0):
        return []

    host = device.get("ftp_host") or device["ip"]
    port = int(device.get("ftp_port") or settings["ftp_port"])
    username = device.get("ftp_username") or settings["ftp_username"]
    password = device.get("ftp_password") or settings["ftp_password"]
    remote_dir = device.get("ftp_remote_dir") or settings["ftp_remote_dir"]
    timeout = float(settings["connect_timeout"])

    target = Path(target_dir) / "ftp"
    target.mkdir(parents=True, exist_ok=True)

    log(f"FTP connect {host}:{port}, directory {remote_dir}")
    ftp = ftplib.FTP()
    ftp.connect(host, port, timeout=timeout)
    ftp.login(username, password)
    ftp.cwd(remote_dir)

    downloaded = []
    try:
        for name in ftp.nlst():
            local = target / Path(name).name
            try:
                with local.open("wb") as handle:
                    ftp.retrbinary(f"RETR {name}", handle.write)
                downloaded.append(str(local))
                log(f"FTP downloaded: {name}")
            except ftplib.all_errors:
                if local.exists():
                    local.unlink()
                log(f"FTP skipped: {name}")
    finally:
        try:
            ftp.quit()
        except ftplib.all_errors:
            ftp.close()

    return downloaded


def _safe_filename(text):
    value = re.sub(r'[<>:"/\\|?*]+', "_", str(text or "").strip())
    return value.rstrip(". ") or "device"


def execute_device(
    device,
    template,
    settings,
    trigger_type,
    db,
    log,
    batch_stamp=None,
):
    commands = parse_commands(template["commands"] if template else "")
    run_id = db.create_run(device["id"], trigger_type)
    stamp = batch_stamp or datetime.now().strftime("%Y%m%d%H%M%S")
    base = Path(settings["result_dir"]) / stamp
    base.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(device["name"])
    output_file = base / f"{safe_name}_{stamp}.log"
    ftp_base = base / f"{safe_name}_attachments"

    try:
        if not commands:
            raise RuntimeError("No executable commands are bound to this device.")

        protocol = (device.get("protocol") or "SSH").upper()
        if protocol == "SSH":
            output = run_ssh(device, settings, commands, log)
        elif protocol == "TELNET":
            output = run_telnet(device, settings, commands, log)
        else:
            raise RuntimeError(f"Unsupported protocol: {protocol}")

        header = (
            f"===== Device {device['ip']} ({device['name']}) [{stamp}] =====\n"
            f"Connection: {protocol.lower()} {device['ip']}:{device.get('port') or ''}\n"
            "===== CLI output start =====\n"
        )
        footer = "\n===== CLI output end =====\n"
        output_file.write_text(
            header + output.rstrip() + footer,
            encoding="utf-8",
            errors="replace",
        )

        files = download_ftp(device, settings, ftp_base, log)
        summary = (
            f"{len(commands)} commands, {len(files)} FTP files, "
            f"log={output_file.name}"
        )
        db.finish_run(run_id, True, summary, str(base))
        db.update_device_status(device["id"], "OK")
        return True, summary, str(base)

    except Exception as exc:
        summary = f"{type(exc).__name__}: {exc}"
        try:
            output_file.write_text(
                f"===== Device execution failed [{stamp}] =====\n{summary}\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        db.finish_run(run_id, False, summary, str(base))
        db.update_device_status(device["id"], "Failed")
        return False, summary, str(base)
