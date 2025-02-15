import socket
import threading
import datetime
import os
from rich.progress import Progress, BarColumn, TimeElapsedColumn, TransferSpeedColumn, Console
import time


from typing import Dict, Tuple
console = Console()


class TCPServer:
    def __init__(self, host="0.0.0.0", port=12346):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        self.interrupted_downloads: Dict[str, str | int] = dict()


    def start(self):
        """Запускает сервер и начинает прослушивание подключений."""
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        console.log(f"[bold green]Сервер запущен на {self.host}:{self.port}[/bold green]")

        while True:
            client_socket, addr = self.server_socket.accept()
            console.log(f"[cyan]Новое подключение от {addr}[/cyan]")
  
            # client_socket.sendall(b"HELLO\n")
            thread = threading.Thread(target=self.handle_client, args=(client_socket, addr))
            thread.start()

    def handle_incomplete_transfer(self, client_socket, addr):
        """Обрабатывает незавершенную передачу файла."""
        filename, filesize = self.incomplete_transfers[addr[0]]
        message = f'RESUME {filename} {filesize}\n'
        client_socket.sendall(b"RESUME\n")





    def handle_client(self, client_socket, addr):
        """Обрабатывает подключенного клиента."""
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
                    console.log(f"[red]Ошибка с {addr}: {e}[/red]")
                    break
                    
        console.log(f"[magenta]Отключение {addr}[/magenta]")

    def process_command(self, command, client_socket):
        """Обрабатывает команды клиента и возвращает ответ."""
        cmd = command[0].upper()
        arg = command[1] if len(command) > 1 else ""

        if cmd == "ECHO":
            return f"ECHO: {arg}\n"

        elif cmd == "TIME":
            return f"TIME: {datetime.datetime.now()}\n"

        elif cmd in ("CLOSE", "EXIT", "QUIT"):
            return "Соединение закрыто\n"

        elif cmd == "UPLOAD":
            return self.upload_file(client_socket, arg)

        elif cmd == "DOWNLOAD":
            return self.download_file(client_socket, arg)

        else:
            return "Неизвестная команда\n"



    def upload_file(self, client_socket, filename):
        """Принимает файл от клиента и сохраняет его с прогресс-баром."""
        if not filename:
            return "Ошибка: имя файла не указано\n"

        client_socket.sendall(b"READY\n")
        filesize = int(client_socket.recv(1024).decode())  # Получаем размер файла
        client_socket.sendall(b"OK\n")  # Подтверждаем получение размера

        start_time = time.time()
        with open(filename, "wb") as f, Progress(
                                                "[blue]{task.description}",
                                                 BarColumn(),
        TimeElapsedColumn(),  # Показывает прошедшее время вместо ETA
        TransferSpeedColumn(),  # Показывает скорость передачи:
        ) as progress:
            task = progress.add_task(f"[green]Загрузка {filename}...", total=filesize)

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
        console.log(f"[bold blue]Скорость передачи: {bitrate:.2f} MB/s[/bold blue]")

        console.log(f"[bold green]Файл {filename} загружен ({filesize} байт)[/bold green]")

    def download_file(self, client_socket: socket.socket , filename):
        """Отправляет файл клиенту с прогресс-баром."""
        if not filename or not os.path.exists(filename):
            return "Файл не найден\n"
        
        filesize = os.path.getsize(filename)
        starts_from = 0
        bytes_to_send = filesize
        
        client_ip = client_socket.getpeername()[0]
        if client_ip== self.interrupted_downloads.get("client_ip", "") and filename == self.interrupted_downloads.get("filename", ""):
            starts_from = self.interrupted_downloads['position'] + 1
            bytes_to_send = filesize - starts_from
            client_socket.sendall(f"RESUME {starts_from}".encode())
            if client_socket.recv(1024).decode() == "NOT FOUND":
                starts_from = 0
                bytes_to_send = filesize
            console.log(f"[yellow]Продолжение загрузки файла {filename} с позиции {starts_from}[/yellow]")
        
        client_socket.sendall(f"READY {bytes_to_send}".encode())
        console.log(f"[bold blue]Отправка файла {filename} размером {filesize} байт[/bold blue]")
        console.log(f"[bold blue]Наичинаем отправку с позиции {starts_from}[/bold blue]")
      
        _ = client_socket.recv(1024)  # OK                                                                                                                                                                                                                                                      


        start_time = time.time()
        try:
            with open(filename, "rb") as f, Progress(
                                                "[blue]{task.description}",
                                                 BarColumn(),
        TimeElapsedColumn(),  # Показывает прошедшее время вместо ETA
        TransferSpeedColumn(),  # Показывает скорость передачи
        "[bold blue]{task.percentage:.0f}%[/bold blue]"
    ) as progress:
                task = progress.add_task(f"[blue]Отправка {filename}...", total=filesize)
                progress.update(task, completed=starts_from)

                f.seek(starts_from)

                sent_bytes = 0
                while (chunk := f.read(1024)):
                    client_socket.sendall(chunk)
                    sent_bytes += len(chunk)
                    progress.update(task, advance=len(chunk))
        except socket.error as e:
            console.log(f"[red]Ошибка соединения {e}[/red]")
            self.interrupted_downloads["client_ip"] = client_ip
            self.interrupted_downloads["filename"] = filename
            self.interrupted_downloads["position"] = sent_bytes


        elapsed_time = time.time() - start_time
        bitrate = filesize/ elapsed_time / (1024 * 1024)
        console.log(f"[bold blue]Скорость передачи: {bitrate:.2f} MB/s[/bold blue]")

        console.log(f"[bold blue]Файл {filename} отправлен ({filesize} байт)[/bold blue]")

if __name__ == "__main__":
    server = TCPServer()
    server.start()