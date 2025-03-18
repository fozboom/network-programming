import socket

from rich.progress import (
    Console,
)

console = Console()

class UDPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 12346):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.host, self.port))

    def start(self) -> None:
        console.log(f"[bold green]UDP Server started on {self.host}:{self.port}[/bold green]")
        while True:
            data, addr = self.socket.recvfrom(1024)
            console.log(f"[bold blue]Received data from {addr}: {data.decode()}[/bold blue]")
