import socket
import os
import time

from rich.console import Console
from rich.progress import Progress

SERVER_HOST = "192.168.1.107"
SERVER_PORT = 12346
console = Console()


def send_command(sock, command):
    sock.sendall(command.encode())
    response = sock.recv(1024).decode()
    console.log(response)


def upload_file(sock, filename):
    if not os.path.exists(filename):
        console.log("Файл не найден")
        return

    file_size = os.path.getsize(filename)

    try:
        start_time = time.time()
        with open(filename, "rb") as f, Progress() as progress:
            task = progress.add_task(f"[cyan]Загрузка {filename}...", total=file_size)

            sock.sendall(f"UPLOAD {filename}\n".encode())
            ack = sock.recv(1024).decode().strip()

            if ack == "READY":
                sock.sendall(str(file_size).encode())
                sock.recv(1024).decode()

                while chunk := f.read(1024):
                    sock.sendall(chunk)
                    progress.update(task, advance=len(chunk))

            else:
                console.log("[red]Ошибка загрузки файла")
        elapsed_time = time.time() - start_time
        bitrate = (file_size * 8) / elapsed_time / 1024  # Кбит/с
        console.log(f"[green]Файл {filename} загружен ({bitrate:.2f} Кбит/с)[/green]")
    except Exception as e:
        console.log(f"[red]Ошибка: {e}")


def download_file(sock, filename):
    sock.sendall(f"DOWNLOAD {filename}\n".encode())
    ack = sock.recv(1024).decode().strip()

    if ack == "READY":
        start_time = time.time()
        with open(f"downloaded_{filename}", "wb") as f, Progress() as progress:
            size_buf = size = int(sock.recv(1024).decode())
            sock.sendall(str(size).encode())
            task = progress.add_task(f"[cyan]Скачивание {filename}...", total=size)

            while size > 0:
                chunk = sock.recv(1024)
                f.write(chunk)
                progress.update(task, advance=len(chunk))
                size -= len(chunk)

        elapsed_time = time.time() - start_time
        bitrate = (size_buf * 8) / elapsed_time / 1024  # Кбит/с
        console.log(f"[green]Файл {filename} скачан ({bitrate:.2f} Кбит/с)[/green]")
    else:
        console.log("[red]Файл не найден на сервере")


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((SERVER_HOST, SERVER_PORT))
        console.log(f"[green]Подключено к {SERVER_HOST}:{SERVER_PORT}")



        ack = str(sock.recv(1024).decode())
        if len(ack.split()) > 1:
            file_name = ack.split()[1]
            file_size = ack.split()[2]


        while True:
            command = input("> ").strip()
            if not command:
                continue

            if command.upper() == "CLOSE":
                send_command(sock, command)
                break

            elif command.upper().startswith("UPLOAD"):
                filename = command.split(" ", 1)[1] if " " in command else ""
                upload_file(sock, filename)

            elif command.upper().startswith("DOWNLOAD"):
                filename = command.split(" ", 1)[1] if " " in command else ""
                download_file(sock, filename)

            else:
                send_command(sock, command)


if __name__ == "__main__":
    main()
