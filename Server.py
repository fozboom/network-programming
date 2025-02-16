import datetime
import os
import socket
import threading
import time
from typing import Dict, List, Tuple

from rich.progress import (
    BarColumn,
    Console,
    Progress,
    TimeElapsedColumn,
    TransferSpeedColumn,
)

console = Console()


class TCPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 12346):
        """
        Initialize the TCP server with given host and port.

        Parameters
        ----------
        host : str, optional
            The IP address to bind the server to, by default "0.0.0.0"
        port : int, optional
            The port number to listen on, by default 12346
        """
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        self.interrupted_downloads: Dict[str, str | int] = dict()

    def start(self) -> None:
        """
        Starts the server and begins listening for connections.
        """
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        console.log(
            f"[bold green]Server started on {self.host}:{self.port}[/bold green]"
        )

        while True:
            client_socket, addr = self.server_socket.accept()
            console.log(f"[cyan]New connection from {addr}[/cyan]")

            threading.Thread(
                target=self.handle_client, args=(client_socket, addr)
            ).start()

    def handle_client(
        self, client_socket: socket.socket, addr: Tuple[str, int]
    ) -> None:
        """
        Handles an individual client connection.

        Parameters
        ----------
        client_socket : socket.socket
            The socket object representing the client connection.
        addr : tuple
            The client address (IP, port).
        """
        with client_socket:
            while True:
                try:
                    data = client_socket.recv(1024).decode().strip()
                    if not data:
                        break

                    console.log(f"[blue]{addr} -> {data}[/blue]")
                    command = data.split(" ", 1)
                    response = self.process_command(command, client_socket)

                    if response:
                        client_socket.sendall(response.encode())
                except Exception as e:
                    console.log(f"[red]Error with {addr}: {e}[/red]")
                    break

        console.log(f"[magenta]Disconnected {addr}[/magenta]")

    def process_command(self, command: List[str], client_socket: socket.socket) -> str:
        """
        Processes client commands and returns a response.

        Parameters
        ----------
        command : list
            A list containing the command and its arguments.
        client_socket : socket.socket
            The socket object representing the client connection.

        Returns
        -------
        str
            The response message to be sent back to the client.
        """
        cmd: str = command[0].upper()
        arg: str = command[1] if len(command) > 1 else ""

        if cmd == "ECHO":
            return f"ECHO: {arg}\n"

        elif cmd == "TIME":
            return f"TIME: {datetime.datetime.now()}\n"

        elif cmd in ("CLOSE", "EXIT", "QUIT"):
            return "Соединение закрыто\n"

        elif cmd == "UPLOAD":
            return self._handle_upload_file(client_socket, arg)

        elif cmd == "DOWNLOAD":
            return self._handle_download_file(client_socket, arg)

        else:
            return "Unknown command\n"

    def _handle_upload_file(self, client_socket: socket.socket, filename: str) -> str:
        """
        Handles file upload command.

        Parameters
        ----------
        client_socket : socket.socket
            The socket object representing the client connection.
        filename : str
            The name of the file to be uploaded.

        Returns
        -------
        str
            A response message indicating the success or failure of the operation.
        """
        if not filename:
            return "Error: No filename provided\n"

        client_socket.sendall(b"READY\n")
        filesize = int(client_socket.recv(1024).decode())
        _ = client_socket.sendall(b"OK\n")  # ACK

        start_time = time.time()
        with (
            open(filename, "wb") as f,
            Progress(
                "[blue]{task.description}",
                BarColumn(),
                TimeElapsedColumn(),
                TransferSpeedColumn(),
            ) as progress,
        ):
            task = progress.add_task(f"[green]Uploading {filename}...", total=filesize)

            received = 0
            while received < filesize:
                chunk = client_socket.recv(1024)
                if not chunk:
                    break

                f.write(chunk)
                received += len(chunk)
                progress.update(task, advance=len(chunk))
        elapsed_time = time.time() - start_time
        bitrate = filesize / elapsed_time / (1024 * 1024)
        console.log(f"[bold blue]Transfer speed: {bitrate:.2f} MB/s[/bold blue]")

        console.log(
            f"[bold green]File {filename} uploaded ({filesize} bytes)[/bold green]"
        )

    def _handle_download_file(self, client_socket: socket.socket, filename: str) -> str:
        """
        Handles file download for a client without terminal progress output.

        Parameters
        ----------
        client_socket : socket.socket
            The socket object representing the client connection.
        filename : str
            The name of the file to be downloaded.

        Returns
        -------
        str
            A response message indicating the success or failure of the operation.
        """
        if not os.path.exists(filename):
            return "File not found\n"

        filesize = os.path.getsize(filename)
        starts_from, bytes_to_send = self.__determine_starting_position(
            client_socket, filename, filesize
        )

        client_socket.sendall(f"READY {bytes_to_send}".encode())
        console.log(
            f"[bold blue]Sending {filename} ({filesize} bytes) starting from {starts_from}[/bold blue]"
        )

        _ = client_socket.recv(1024)  # Client confirmation

        return self._send_file_chunks(client_socket, filename, starts_from, filesize)

    def __determine_starting_position(
        self, client_socket: socket.socket, filename: str, filesize: int
    ) -> Tuple[int, int]:
        """
        Determines the starting position for resumed downloads and calculates remaining bytes.

        Parameters
        ----------
        client_socket : socket.socket
            The socket object representing the client connection.
        filename : str
            The name of the file.
        filesize : int
            The total size of the file.

        Returns
        -------
        Tuple[int, int]
            The start position and bytes to send.
        """
        starts_from = 0
        bytes_to_send = filesize
        client_ip = client_socket.getpeername()[0]

        if client_ip == self.interrupted_downloads.get(
            "client_ip", ""
        ) and filename == self.interrupted_downloads.get("filename", ""):
            starts_from = self.interrupted_downloads["position"] + 1
            bytes_to_send = filesize - starts_from
            client_socket.sendall(f"RESUME {starts_from}".encode())

            if client_socket.recv(1024).decode() == "NOT FOUND":
                starts_from = 0
                bytes_to_send = filesize

            console.log(f"[yellow]Resuming {filename} from {starts_from}[/yellow]")

        return starts_from, bytes_to_send

    def _send_file_chunks(
        self,
        client_socket: socket.socket,
        filename: str,
        starts_from: int,
        filesize: int,
    ) -> str:
        """
        Sends the file to the client in chunks.

        Parameters
        ----------
        client_socket : socket.socket
            The socket object representing the client connection.
        filename : str
            The name of the file.
        starts_from : int
            The byte position to start sending from.
        filesize : int
            The total size of the file.

        Returns
        -------
        str
            A confirmation message upon completion.
        """
        start_time = time.time()

        try:
            with open(filename, "rb") as f:
                f.seek(starts_from)
                sent_bytes = starts_from

                with Progress(
                    "[blue]{task.description}",
                    BarColumn(),
                    TimeElapsedColumn(),
                    TransferSpeedColumn(),
                    "[bold blue]{task.percentage:.0f}%[/bold blue]",
                ) as progress:
                    task = progress.add_task(
                        f"[blue]Sending {filename}...", total=filesize
                    )
                    progress.update(task, completed=starts_from)

                    while chunk := f.read(1024):
                        client_socket.sendall(chunk)
                        sent_bytes += len(chunk)
                        progress.update(task, advance=len(chunk))

        except socket.error as e:
            console.log(f"[red]Connection error: {e}[/red]")
            self.interrupted_downloads.update(
                {
                    "client_ip": client_socket.getpeername()[0],
                    "filename": filename,
                    "position": sent_bytes,
                }
            )

        elapsed_time = time.time() - start_time
        bitrate = filesize / elapsed_time / (1024 * 1024)
        console.log(f"[bold blue]Transfer speed: {bitrate:.2f} MB/s[/bold blue]")
        console.log(f"[bold blue]File {filename} sent ({filesize} bytes)[/bold blue]")

        return "Download complete\n"


if __name__ == "__main__":
    server = TCPServer()
    server.start()
