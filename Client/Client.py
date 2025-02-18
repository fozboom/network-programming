import socket
import os
import time
from rich.progress import Progress, BarColumn, TimeElapsedColumn, TransferSpeedColumn, Console


class Client:
    """
    A client for file transfer operations using a socket connection.

    Attributes
    ----------
    server_host : str
        The IP address of the server.
    server_port : int
        The port number of the server.
    console : Console
        Rich console for logging and progress display.
    """

    def __init__(self, server_host: str, server_port: int) -> None:
        """
        Initializes the FileTransferClient with server details.

        Parameters
        ----------
        server_host : str
            The IP address of the server.
        server_port : int
            The port number of the server.
        """
        self.server_host = server_host
        self.server_port = server_port
        self.console = Console()

    def send_command(self, sock: socket.socket, command: str) -> None:
        """
        Sends a command to the server and logs the response.

        Parameters
        ----------
        sock : socket.socket
            The connected socket object.
        command : str
            The command to send.
        """
        sock.sendall(command.encode())
        response = sock.recv(1024).decode()
        self.console.log(response)

    def upload_file(self, sock: socket.socket, filename: str) -> None:
        """
        Uploads a file to the server.

        Parameters
        ----------
        sock : socket.socket
            The connected socket object.
        filename : str
            The name of the file to upload.
        """
        if not os.path.exists(filename):
            self.console.log("File not found")
            return

        file_size = os.path.getsize(filename)

        try:
            start_time = time.time()
            with open(filename, "rb") as f, Progress(
                    "[blue]{task.description}",
                    BarColumn(),
                    TimeElapsedColumn(),
                    TransferSpeedColumn(),
                    "[bold blue]{task.percentage:.0f}%[/bold blue]"
            ) as progress:
                task = progress.add_task(f"[cyan]Uploading {filename}...", total=file_size)

                sock.sendall(f"UPLOAD {filename}\n".encode())
                ack = sock.recv(1024).decode().strip()

                if ack == "READY":
                    sock.sendall(str(file_size).encode())
                    sock.recv(1024).decode()

                    while chunk := f.read(1024):
                        sock.sendall(chunk)
                        progress.update(task, advance=len(chunk))
                else:
                    self.console.log("[red]File upload error")

            elapsed_time = time.time() - start_time
            bitrate = file_size / elapsed_time / 1024 / 1024
            self.console.log(f"[green]File {filename} uploaded ({bitrate:.2f} MB/s)[/green]")
        except Exception as e:
            self.console.log(f"[red]Error: {e}")

    def download_file(self, sock: socket.socket, filename: str) -> None:
        """
        Downloads a file from the server.

        Parameters
        ----------
        sock : socket.socket
            The connected socket object.
        filename : str
            The name of the file to download.
        """
        sock.sendall(f"DOWNLOAD {filename}\n".encode())
        ack: str = sock.recv(1024).decode().strip()

        mode = "wb"
        start_pos = 0
        if ack.startswith("RESUME"):
            mode = "ab"
            start_pos = int(ack.split()[1])

            if not os.path.exists(filename):
                sock.sendall("NOT FOUND".encode())
                mode = "wb"
                start_pos = 0
            else:
                sock.sendall("FOUND".encode())

            ack = sock.recv(1024).decode().strip()

        if ack.startswith("READY"):
            start_time = time.time()
            with open(f"{filename}", mode) as f, Progress(
                    "[blue]{task.description}",
                    BarColumn(),
                    TimeElapsedColumn(),
                    TransferSpeedColumn(),
                    "[bold blue]{task.percentage:.0f}%[/bold blue]"
            ) as progress:

                size_buf = size = int(ack.split()[1])
                sock.sendall("size is got".encode())
                task = progress.add_task(f"[cyan]Downloading {filename}...", total=size + start_pos)
                progress.update(task, completed=start_pos)

                while size > 0:
                    chunk = sock.recv(1024)
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))
                    size -= len(chunk)

            elapsed_time = time.time() - start_time
            bitrate = size_buf / elapsed_time / 1024 / 1024
            self.console.log(f"[green]File {filename} downloaded ({bitrate:.2f} MB/s)[/green]")
        else:
            self.console.log("[red]File not found on server")

    def run(self) -> None:
        """
        Starts the client and handles user commands interactively.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((self.server_host, self.server_port))
            self.console.log(f"[green]Connected to {self.server_host}:{self.server_port}")

            while True:
                command = input("> ").strip()
                if not command:
                    continue

                if command.upper() == "CLOSE":
                    self.send_command(sock, command)
                    break

                elif command.upper().startswith("UPLOAD"):
                    filename = command.split(" ", 1)[1] if " " in command else ""
                    self.upload_file(sock, filename)

                elif command.upper().startswith("DOWNLOAD"):
                    filename = command.split(" ", 1)[1] if " " in command else ""
                    self.download_file(sock, filename)

                else:
                    self.send_command(sock, command)


if __name__ == "__main__":
    client = Client("192.168.1.102", 12346)
    client.run()
