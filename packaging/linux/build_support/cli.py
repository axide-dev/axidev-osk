"""Command-line interface for repository Linux builds."""

from __future__ import annotations

import argparse
import os

from common import BuildError, fail
from payload import build_payload, build_release, verify_payload
from vm import prepare_vm, reset_vm, run_vm, ssh_vm


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python build.py")
    platforms = parser.add_subparsers(dest="platform", required=True)
    linux = platforms.add_parser("linux", help="build and test Linux distribution artifacts")
    commands = linux.add_subparsers(dest="linux_command", required=True)

    payload = commands.add_parser("payload", help="build the Linux payload through Docker")
    payload.add_argument("--output", type=str)
    payload.add_argument("--engine", default=os.environ.get("DOCKER", "docker"))
    payload.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    payload.set_defaults(handler=build_payload)

    verify = commands.add_parser("verify", help="verify an assembled Linux payload")
    verify.add_argument("payload", nargs="?", type=str)
    verify.set_defaults(handler=verify_payload)

    release = commands.add_parser("release", help="assemble signed Linux release assets")
    release.add_argument("--output", type=str)
    release.add_argument("--engine", default=os.environ.get("DOCKER", "docker"))
    release.add_argument("--signing-key", type=str)
    release.set_defaults(handler=build_release)

    vm = commands.add_parser("vm", help="manage interactive Linux test machines")
    vm_commands = vm.add_subparsers(dest="vm_command", required=True)
    for name, handler in (
        ("prepare", prepare_vm),
        ("run", run_vm),
        ("ssh", ssh_vm),
        ("reset", reset_vm),
    ):
        command = vm_commands.add_parser(name)
        command.add_argument(
            "profile", choices=("hyprland", "kde", "gnome", "lightdm-x11")
        )
        if name == "prepare":
            command.add_argument("--payload", type=str, required=True)
        if name == "ssh":
            command.add_argument("remote_command", nargs=argparse.REMAINDER)
        command.set_defaults(handler=handler)
    return parser


def main() -> int:
    namespace = build_parser().parse_args()
    try:
        return namespace.handler(namespace)
    except BuildError as exc:
        return fail(str(exc))
