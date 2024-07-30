import json
import os
import socket
from gi.repository import GObject
from ignis.gobject import IgnisGObject
from ignis.utils import Utils
from typing import List
from ignis.logging import logger

HYPRLAND_INSTANCE_SIGNATURE = os.getenv("HYPRLAND_INSTANCE_SIGNATURE")
XDG_RUNTIME_DIR = os.getenv("XDG_RUNTIME_DIR")
SOCKET_DIR = f"{XDG_RUNTIME_DIR}/hypr/{HYPRLAND_INSTANCE_SIGNATURE}"

class HyprlandService(IgnisGObject):
    """
    Hyprland IPC client.

    Properties:
        - **workspaces** (``List[dict]``, read-only): List of workspaces.
        - **active_workspace** (``dict``, read-only): Currently active workspace.
        - **kb_layout** (``str``, read-only): Currenly active keyboard layout.
        - **active_window** (``dict``, read-only): Currenly focused window.

    **Example usage:**

    .. code-block:: python

        from ignis.service import Service

        hyprland = Service.get("hyprland")

        print(hyprland.workspaces)
        print(hyprland.kb_layout)

        hyprland.connect("notify::kb-layout", lambda x, y: print(hyprland.kb_layout))
    """

    def __init__(self):
        super().__init__()
        if not os.path.exists(SOCKET_DIR):
            logger.critical("Hyprland IPC not found! To use the Hyprland service, ensure that you are running Hyprland.")
            exit(1)

        self._workspaces = []
        self._active_workspace = {}
        self._kb_layout = ""
        self._active_window = ""

        self.__listen_socket()
        self.__sync_kb_layout()
        self.__sync_workspaces()
        self.__sync_active_window()

    @GObject.Property
    def workspaces(self) -> List[dict]:
        return self._workspaces

    @GObject.Property
    def active_workspace(self) -> dict:
        return self._active_workspace

    @GObject.Property
    def kb_layout(self) -> str:
        return self._kb_layout

    @GObject.Property
    def active_window(self) -> dict:
        return self._active_window

    @Utils.run_in_thread
    def __listen_socket(self) -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(f"{SOCKET_DIR}/.socket2.sock")
            while True:
                try:
                    data = sock.recv(1024).decode("utf-8")
                    self.__on_data_received(data)
                except Exception as e:
                    logger.error(f"Error in Hyprland service: {e}")

    def __on_data_received(self, data: str) -> None:
        data_list = data.split("\n")
        for d in data_list:
            if (
                d.startswith("workspace>>")
                or d.startswith("destroyworkspace>>")
                or d.startswith("focusedmon>>")
            ):
                self.__sync_workspaces()
            elif d.startswith("activelayout>>"):
                self.__sync_kb_layout()

            elif d.startswith("activewindow>>"):
                self.__sync_active_window()

    def __sync_workspaces(self) -> None:
        self._workspaces = sorted(
            json.loads(self.send_command("j/workspaces")), key=lambda x: x["id"]
        )
        self._active_workspace = json.loads(self.send_command("j/activeworkspace"))
        self.notify("workspaces")
        self.notify("active-workspace")


    def __sync_kb_layout(self) -> None:
        for kb in json.loads(self.send_command("j/devices"))["keyboards"]:
            if kb["main"]:
                self._kb_layout = kb["active_keymap"]
                self.notify("kb_layout")

    def __sync_active_window(self) -> None:
        self._active_window = json.loads(self.send_command("j/activewindow"))
        self.notify("active_window")


    def send_command(self, cmd: str) -> str:
        """
        Send command to Hyprland IPC.
        Supported the same commands as in hyprctl.
        If you want to get response as JSON use this syntax: ``j/COMMAND``.

        Args:
            cmd (``str``): A command.

        Returns:
            Response from Hyprland IPC.
        """
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(f"{SOCKET_DIR}/.socket.sock")
            sock.send(cmd.encode())
            resp = sock.recv(4096).decode()
            return resp

    def switch_kb_layout(self) -> None:
        """
        Just switch to next keyboard layout.
        """
        for kb in json.loads(self.send_command("j/devices"))["keyboards"]:
            if kb["main"]:
                self.send_command(f"switchxkblayout {kb['name']} next")

    def switch_to_workspace(self, workspace_id: int) -> None:
        """
        Switch to workspace by ID.

        Args:
            workspace_id (``int``): ID of workspace to be switched to
        """
        self.send_command(f"dispatch workspace {workspace_id}")

