import time
import os
import datetime
from config import BUFFER_SIZE, UPLOAD_PATH, SERVER_FILES_PATH, console, log
from rich.panel import Panel
from file_handler import File


class ServerCommander:
    def __init__(self, server_socket):
        self.server_socket = server_socket
        self.client_is_active = True
        self.client_address = None

    def send_msg(self, data):
        if self.client_address:
            self.server_socket.sendto(str(data).encode("utf-8"), self.client_address)
        else:
            log.error("Cannot send message: client_address not set")

    def recv_msg(self):
        recv_data, recv_address = self.server_socket.recvfrom(BUFFER_SIZE)
        return (recv_data.decode("utf-8"), recv_address)

    def exec_quit(self):
        self.client_is_active = False
        log.info(f"Client {self.client_address} disconnected")

    def exec_time(self):
        current_time_formatted = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.info(f"Sending current time: {current_time_formatted}")
        self.send_msg(current_time_formatted)

    def exec_echo(self, args):
        log.info(f"Echo: {args}")
        self.send_msg(args)

    def exec_download(self, file_name):
        if not os.path.exists(SERVER_FILES_PATH + file_name):
            self.send_msg("0")
            log.warning(f"Download request for non-existent file: {file_name}")
        else:
            file_size = os.path.getsize(SERVER_FILES_PATH + file_name)

            self.send_msg(file_size)
            log.info(f"Sending file size: {file_size}")

            file_offset, _ = self.recv_msg()
            file_offset = int(file_offset)
            log.info(f"Client requested offset: {file_offset}")
            if file_offset == file_size:
                log.info(f"File {file_name} is already downloaded")
                return

            file = File(
                SERVER_FILES_PATH + file_name,
                "rb",
                self.server_socket,
                self.client_address,
            )
            send_time = file.send_file(file_offset)

            if send_time > 0:
                speed = (file_size - file_offset) / send_time / 1024
                log.info(f"Download completed. Speed: {speed:.2f} KB/s")
                console.print(
                    Panel(
                        f"[bold green]Download completed[/]\nSpeed: [yellow]{speed:.2f} KB/s[/]"
                    )
                )

    def exec_upload(self, args):
        path_parts = " ".join(args.split()[:-1]).split("/")
        full_file_name = os.path.join(UPLOAD_PATH, path_parts[-1])

        if os.path.exists(full_file_name):
            mode = "ab"
            file_offset = os.path.getsize(full_file_name)
        else:
            mode = "wb+"
            file_offset = 0

        file_size = int(args.split()[-1])
        log.info(
            f"Upload request: {path_parts[-1]}, size: {file_size}, offset: {file_offset}"
        )
        self.send_msg(file_offset)

        os.makedirs(UPLOAD_PATH, exist_ok=True)

        file = File(full_file_name, mode, self.server_socket, self.client_address)
        start_time = time.time()
        file.recv_file(file_size, file_offset)

        end_time = time.time()

        transfer_time = end_time - start_time
        if transfer_time > 0:
            speed = (file_size - file_offset) / transfer_time / 1024
            log.info(f"Upload completed. Speed: {speed:.2f} KB/s")
            console.print(
                Panel(
                    f"[bold green]Upload completed[/]\nSpeed: [yellow]{speed:.2f} KB/s[/]"
                )
            )

    def handle_command(self, msg):
        if len(msg) == 0:
            return

        log.info(f"Request from {self.client_address}: {msg}")

        full_cmd = msg.split(maxsplit=1)
        command = full_cmd[0].strip().upper()
        arguments = "" if len(full_cmd) == 1 else full_cmd[1].strip()

        console.print(
            Panel(
                f"[bold]Command:[/] [cyan]{command}[/]",
                subtitle=f"From: {self.client_address[0]}:{self.client_address[1]}",
            )
        )

        if command == "QUIT":
            self.exec_quit()
        elif command == "TIME":
            self.exec_time()
        elif msg.startswith("ECHO"):
            self.exec_echo(msg[5:])
        elif command == "DOWNLOAD":
            self.exec_download(arguments)
        elif command == "UPLOAD":
            self.exec_upload(arguments)
        else:
            log.error(f"Unknown command: {command}")
            console.print("[bold red]Error:[/] Unknown command")

    def set_client_address(self, client_address):
        self.client_address = client_address
