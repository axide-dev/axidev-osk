"""Provision and run interactive compositor test machines."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tarfile
from pathlib import Path
from typing import Any

from common import (
    CACHE_ROOT,
    LINUX_DIR,
    BuildError,
    capture,
    download,
    load_lock,
    require_commands,
    run,
    sha256,
)


VM_ROOT = CACHE_ROOT / "vm"
VM_USER = "axidev"
VM_DISPLAY_MODE = "1920x1080"
VM_PASSWORD = "axidev"
INSTALL_SOURCE_NAME = "install-source"
INSTALL_MOUNT = "/run/axidev-osk-install-source"
INSTALLER_NAME = "axidev-osk-install"
PAYLOAD_ARCHIVE_NAME = "axidev-osk-linux-x86_64.tar.gz"
TEST_KEY_ROOT = LINUX_DIR / "testing" / "ssh"
TEST_PRIVATE_KEY = TEST_KEY_ROOT / "axidev-osk-vm"
TEST_PUBLIC_KEY = TEST_KEY_ROOT / "axidev-osk-vm.pub"
CACHED_PRIVATE_KEY = VM_ROOT / "ssh" / "axidev-osk-vm"


def _profile(name: str) -> dict[str, Any]:
    return load_lock()["virtual_machines"][name]


def _paths(name: str, details: dict[str, Any]) -> tuple[Path, Path, Path]:
    images = VM_ROOT / "images"
    machine = VM_ROOT / name
    base = images / details["image"]
    return base, machine / "disk.qcow2", machine / "seed.iso"


def _desktop_commands(name: str) -> list[str]:
    if name == "hyprland":
        return [
            "pacman -Syu --noconfirm greetd greetd-regreet hyprland kitty layer-shell-qt "
            "mesa noto-fonts noto-fonts-emoji otf-font-awesome pyside6 polkit qt6-wayland "
            "waybar wofi xdg-desktop-portal-hyprland",
            "usermod -aG video,input axidev",
            "install -d -o axidev -g axidev /home/axidev/.config/hypr && "
            "cp /usr/share/hypr/hyprland.lua /home/axidev/.config/hypr/hyprland.lua && "
            "sed -i -e 's/mode     = \"preferred\"/mode     = \"1920x1080@60\"/' "
            "-e 's/scale    = \"auto\"/scale    = 1/' "
            "/home/axidev/.config/hypr/hyprland.lua && "
            "printf '%s\\n' 'hl.on(\"hyprland.start\", function ()' "
            "'  hl.exec_cmd(\"waybar\")' '  hl.exec_cmd(\"kitty\")' "
            "'  hl.exec_cmd(\"/usr/local/bin/axidev-osk\")' 'end)' "
            ">> /home/axidev/.config/hypr/hyprland.lua && "
            "chown -R axidev:axidev /home/axidev/.config",
            "printf '%s\\n' 'monitor = Virtual-1,1920x1080@60,auto,1' "
            "'exec-once = regreet; hyprctl dispatch exit' 'misc {' "
            "'  disable_hyprland_logo = true' '  disable_splash_rendering = true' "
            "'  disable_hyprland_guiutils_check = true' '}' > /etc/greetd/hyprland.conf",
            "printf '%s\\n' '[terminal]' 'vt = 1' '[default_session]' "
            "'command = \"dbus-run-session start-hyprland -- -c "
            "/etc/greetd/hyprland.conf\"' 'user = \"greeter\"' > /etc/greetd/config.toml",
            "systemctl enable greetd.service",
            "systemctl set-default graphical.target",
        ]
    if name == "lightdm-x11":
        return [
            "pacman -Syu --noconfirm lightdm lightdm-gtk-greeter xfce4 xorg-server "
            "xorg-xrandr layer-shell-qt mesa noto-fonts noto-fonts-emoji pyside6 qt6-wayland",
            "usermod -aG video,input axidev",
            "install -Dm0755 /dev/stdin /usr/local/libexec/axidev-osk-lightdm-display <<'EOF'\n"
            "#!/bin/sh\n"
            "xrandr --output Virtual-1 --mode 1920x1080\n"
            "EOF",
            "install -d /etc/lightdm/lightdm.conf.d && "
            "printf '%s\\n' '[Seat:*]' 'greeter-session=lightdm-gtk-greeter' "
            "'user-session=xfce' "
            "'display-setup-script=/usr/local/libexec/axidev-osk-lightdm-display' "
            "> /etc/lightdm/lightdm.conf.d/20-axidev-osk-vm.conf",
            "systemctl enable lightdm.service",
            "systemctl set-default graphical.target",
        ]
    if name == "kde":
        return [
            "dnf group install -y kde-desktop-environment",
            "dnf install -y layer-shell-qt python3-pyside6 qt6-qtwayland",
            "systemctl enable plasmalogin.service",
            "systemctl set-default graphical.target",
        ]
    return [
        "dnf group install -y gnome-desktop",
        "dnf install -y layer-shell-qt python3-pyside6 qt6-qtwayland",
        "systemctl enable gdm.service",
        "systemctl set-default graphical.target",
    ]


def _post_install_commands(name: str) -> list[str]:
    manager = {
        "hyprland": "greetd",
        "kde": "plasma-login",
        "lightdm-x11": "lightdm",
    }.get(name)
    commands = [] if manager is None else [f"axidev-osk linux setup-greeter --manager {manager}"]
    if name in {"kde", "gnome", "lightdm-x11"}:
        commands.append(f"axidev-osk linux setup-autostart --user {VM_USER}")
    return commands


def _cloud_config(name: str, public_key: str, payload_checksum: str) -> str:
    commands = [
        f"install -d {INSTALL_MOUNT}",
        f"mount -t 9p -o trans=virtio,ro axidev_host {INSTALL_MOUNT}",
        "modprobe uinput",
        *_desktop_commands(name),
        f"bash {INSTALL_MOUNT}/{INSTALLER_NAME} install "
        f"--payload {INSTALL_MOUNT}/{PAYLOAD_ARCHIVE_NAME} "
        f"--checksum {payload_checksum} --user {VM_USER}",
        *_post_install_commands(name),
        f"umount {INSTALL_MOUNT}",
        f"rmdir {INSTALL_MOUNT}",
    ]
    indented = "\n".join(
        f"  - [bash, -lc, {json.dumps(command)}]" for command in commands
    )
    return f"""#cloud-config
users:
  - default
  - name: {VM_USER}
    groups: [wheel]
    lock_passwd: false
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - {json.dumps(public_key)}
chpasswd:
  expire: false
  users:
    - name: {VM_USER}
      password: {VM_PASSWORD}
      type: text
ssh_pwauth: true
package_update: true
runcmd:
{indented}
  - [systemd-run, --on-active=5s, --unit=axidev-osk-vm-reboot, systemctl, reboot]
final_message: "Axidev OSK {name} VM provisioning finished"
"""


def _prepare_test_key() -> str:
    try:
        public_key = TEST_PUBLIC_KEY.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise BuildError(f"cannot read VM test public key: {exc}") from exc
    if not public_key.startswith("ssh-ed25519 "):
        raise BuildError(f"invalid VM test public key: {TEST_PUBLIC_KEY}")

    if not TEST_PRIVATE_KEY.is_file():
        raise BuildError(f"VM test private key is missing: {TEST_PRIVATE_KEY}")
    CACHED_PRIVATE_KEY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEST_PRIVATE_KEY, CACHED_PRIVATE_KEY)
    CACHED_PRIVATE_KEY.chmod(0o600)
    derived = capture(["ssh-keygen", "-y", "-f", str(CACHED_PRIVATE_KEY)])
    if derived.split()[:2] != public_key.split()[:2]:
        CACHED_PRIVATE_KEY.unlink(missing_ok=True)
        raise BuildError("VM test public and private keys do not match")
    return public_key


def _prepare_install_source(name: str, payload: Path) -> str:
    launcher = payload / "bin" / "axidev-osk"
    metadata = payload / "release.json"
    if not payload.is_dir() or not launcher.is_file() or not metadata.is_file():
        raise BuildError(f"invalid Axidev OSK payload tree: {payload}")

    machine = VM_ROOT / name
    source = machine / INSTALL_SOURCE_NAME
    staging = machine / f".{INSTALL_SOURCE_NAME}.new"
    backup = machine / f".{INSTALL_SOURCE_NAME}.old"
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    staging.mkdir(parents=True)
    archive = staging / PAYLOAD_ARCHIVE_NAME
    try:
        with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as bundle:
            bundle.add(payload, arcname="axidev-osk", recursive=True)
        installer = staging / INSTALLER_NAME
        shutil.copy2(LINUX_DIR / "install.sh", installer)
        installer.chmod(0o755)
        checksum = sha256(archive)

        if source.exists():
            source.replace(backup)
        try:
            staging.replace(source)
        except OSError:
            if backup.exists():
                backup.replace(source)
            raise
        shutil.rmtree(backup, ignore_errors=True)
        return checksum
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise BuildError(f"cannot prepare VM install source: {exc}") from exc


def prepare_vm(namespace: argparse.Namespace) -> int:
    require_commands("qemu-img", "cloud-localds", "ssh-keygen")
    details = _profile(namespace.profile)
    public_key = _prepare_test_key()
    payload = Path(namespace.payload).resolve()
    payload_checksum = _prepare_install_source(namespace.profile, payload)
    base, disk, seed = _paths(namespace.profile, details)
    base = download(details["url"], base, details["sha256"])
    disk.parent.mkdir(parents=True, exist_ok=True)

    if not disk.exists():
        run(
            [
                "qemu-img",
                "create",
                "-f",
                "qcow2",
                "-F",
                "qcow2",
                "-b",
                str(base),
                str(disk),
                "80G",
            ]
        )

    cloud_dir = disk.parent / "cloud-init"
    cloud_dir.mkdir(exist_ok=True)
    user_data = cloud_dir / "user-data"
    meta_data = cloud_dir / "meta-data"
    user_data.write_text(
        _cloud_config(namespace.profile, public_key, payload_checksum), encoding="utf-8"
    )
    meta_data.write_text(
        f"instance-id: axidev-osk-{namespace.profile}\nlocal-hostname: {namespace.profile}\n",
        encoding="utf-8",
    )
    run(["cloud-localds", str(seed), str(user_data), str(meta_data)])
    print(f"prepared {namespace.profile}: {disk}")
    return 0


def _kvm_arguments() -> list[str]:
    kvm = Path("/dev/kvm")
    if kvm.exists() and os.access(kvm, os.R_OK | os.W_OK):
        return ["-enable-kvm", "-cpu", "host"]
    print("warning: /dev/kvm is unavailable; using slow software emulation")
    return ["-machine", "accel=tcg", "-cpu", "max"]


def run_vm(namespace: argparse.Namespace) -> int:
    require_commands("qemu-system-x86_64")
    details = _profile(namespace.profile)
    _, disk, seed = _paths(namespace.profile, details)
    if not disk.is_file() or not seed.is_file():
        raise BuildError(f"prepare the {namespace.profile} VM before running it")

    install_source = disk.parent / INSTALL_SOURCE_NAME
    if not (install_source / PAYLOAD_ARCHIVE_NAME).is_file() or not (
        install_source / INSTALLER_NAME
    ).is_file():
        raise BuildError(f"prepare the {namespace.profile} VM install source before running it")
    command = [
        "qemu-system-x86_64",
        "-name",
        f"axidev-osk-{namespace.profile}",
        "-m",
        str(details["memory_mb"]),
        "-smp",
        str(details["cpus"]),
        *_kvm_arguments(),
        "-drive",
        f"if=virtio,file={disk},format=qcow2",
        "-drive",
        f"if=virtio,file={seed},format=raw,readonly=on",
        "-device",
        f"virtio-vga,xres={VM_DISPLAY_MODE.split('x')[0]},yres={VM_DISPLAY_MODE.split('x')[1]}",
        "-display",
        "gtk",
        "-device",
        "virtio-net-pci,netdev=network",
        "-netdev",
        f"user,id=network,hostfwd=tcp:127.0.0.1:{details['ssh_port']}-:22",
        "-virtfs",
        f"local,path={install_source},mount_tag=axidev_host,security_model=none,readonly=on",
    ]
    print(
        f"SSH diagnostics: python packaging/build.py linux vm ssh {namespace.profile}",
        flush=True,
    )
    run(command)
    return 0


def _ssh_command(name: str, details: dict[str, Any], remote_command: list[str]) -> list[str]:
    known_hosts = VM_ROOT / name / "known_hosts"
    command = [
        "ssh",
        "-i",
        str(CACHED_PRIVATE_KEY),
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-p",
        str(details["ssh_port"]),
        f"{VM_USER}@127.0.0.1",
    ]
    if remote_command[:1] == ["--"]:
        remote_command = remote_command[1:]
    return [*command, *remote_command]


def ssh_vm(namespace: argparse.Namespace) -> int:
    require_commands("ssh")
    if not CACHED_PRIVATE_KEY.is_file():
        raise BuildError(f"prepare a VM before opening SSH: {CACHED_PRIVATE_KEY}")
    details = _profile(namespace.profile)
    run(_ssh_command(namespace.profile, details, namespace.remote_command))
    return 0


def reset_vm(namespace: argparse.Namespace) -> int:
    details = _profile(namespace.profile)
    _, disk, seed = _paths(namespace.profile, details)
    for path in (disk, seed, disk.parent / "known_hosts"):
        path.unlink(missing_ok=True)
    shutil.rmtree(disk.parent / "cloud-init", ignore_errors=True)
    shutil.rmtree(disk.parent / INSTALL_SOURCE_NAME, ignore_errors=True)
    print(f"reset {namespace.profile}")
    return 0
