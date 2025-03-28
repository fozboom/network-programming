import socket
import os
import time
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TransferSpeedColumn
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

console = Console()

SERVER_ADDRESS = "192.168.1.107"
SERVER_PORT = 12345
OPT_INTERVAL = 10
OPT_COUNT = 3
BUF_SIZE = 1024

exitFlag = False

def format_size(size):
    """Formats file size dynamically (B, KB, MB, GB)"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.2f} MB"
    else:
        return f"{size / 1024 ** 3:.2f} GB"

def setOptions(clientSocket):
    clientSocket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    clientSocket.setsockopt(socket.SOL_TCP, socket.TCP_USER_TIMEOUT, 30000)
    clientSocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, OPT_INTERVAL)
    clientSocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, OPT_INTERVAL)
    clientSocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, OPT_COUNT)
    return clientSocket

def connect(clientSocket):
    clientSocket = setOptions(clientSocket)
    clientSocket.connect((SERVER_ADDRESS, SERVER_PORT))
    return clientSocket

def reconnectPrompt():
    console.print(Panel.fit("[red]Connection lost.[/red]", title="Error"))
    return Prompt.ask("Do you want to try reconnecting?", choices=["y", "n"]) == "y"

def upload(filePath):
    if not os.path.exists(filePath):
        clientSocket.send("0".encode())
        clientSocket.send(f"File \"{filePath}\" not found.".encode())
        return clientSocket.recv(BUF_SIZE).decode()

    clientSocket.send("1".encode())
    offset, fileSize = uploadFile(filePath)
    return clientSocket.recv(BUF_SIZE).decode()

def uploadFile(filePath):
    with open(filePath, 'rb') as file:
        fileSize = os.path.getsize(filePath)
        clientSocket.send(str(fileSize).encode())
        offset = int(clientSocket.recv(BUF_SIZE).decode())
        file.seek(offset, 0)

        console.print(Panel.fit(f"[cyan]Uploading file:[/cyan] [bold]{filePath}[/bold] ([green]{format_size(fileSize)}[/green])", title="Upload"))

        start_time = time.time()

        with Progress(
            TextColumn("[bold blue]Uploading[/bold blue]"),
            BarColumn(),
            TransferSpeedColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task("upload", total=fileSize, completed=offset)

            while offset < fileSize:
                data = file.read(BUF_SIZE)
                clientSocket.send(data)
                offset += len(data)
                progress.update(task, completed=offset)

        total_time = time.time() - start_time
        speed = fileSize / total_time / 1024  # KB/s

        console.print(f"[green]Upload complete![/green] Time: [cyan]{total_time:.2f} sec[/cyan], Speed: [yellow]{speed:.2f} KB/s[/yellow]\n")

    return offset, fileSize

def download(filePath):
    serverHasFile = clientSocket.recv(1).decode()
    if serverHasFile == "0":
        return clientSocket.recv(BUF_SIZE).decode()
    
    offset, fileSize = downloadFile(filePath)
    return clientSocket.recv(BUF_SIZE).decode()
    
def downloadFile(fileName):
    mode = 'ab' if os.path.exists(fileName) else 'wb+'

    with open(fileName, mode) as file:
        offset = os.path.getsize(fileName)
        clientSocket.send(str(offset).encode())
        fileSize = int(clientSocket.recv(BUF_SIZE).decode())
        file.seek(0, os.SEEK_END)

        console.print(Panel.fit(f"[cyan]Downloading file:[/cyan] [bold]{fileName}[/bold] ([green]{format_size(fileSize)}[/green])", title="Download"))

        start_time = time.time()

        with Progress(
            TextColumn("[bold yellow]Downloading[/bold yellow]"),
            BarColumn(),
            TransferSpeedColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task("download", total=fileSize, completed=offset)

            while fileSize > offset:
                data = clientSocket.recv(min(BUF_SIZE, fileSize - offset))
                file.write(data)
                offset += len(data)
                progress.update(task, completed=offset)

        total_time = time.time() - start_time
        speed = fileSize / total_time / 1024  # KB/s

        console.print(f"[green]Download complete![/green] Time: [cyan]{total_time:.2f} sec[/cyan], Speed: [yellow]{speed:.2f} KB/s[/yellow]\n")

    return offset, fileSize

def exit():
    global exitFlag
    exitFlag = True

def otherCommand(userInput):
    return clientSocket.recv(BUF_SIZE).decode()

def handleCommand(userInput):
    command, argument = userInput.partition(" ")[::2]

    match command.lower():
        case "upload":
            response = upload(argument)
        case "download":
            response = download(argument)
        case _:
            response = otherCommand(userInput)

    if userInput.lower() == "exit":
        exit()

    return response

#------------

try:
    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    clientSocket = connect(clientSocket)
    console.print(Panel.fit("[green]Connection established.[/green]", title="Status"))

    while not exitFlag:
        try:
            userInput = Prompt.ask("[bold blue]>[/bold blue]").strip()
            while not userInput:
                userInput = Prompt.ask("[bold blue]>[/bold blue]").strip()
            clientSocket.send(userInput.encode())
            response = handleCommand(userInput)
            console.print(Panel.fit(response, title="Server Response", border_style="green"))
 
        except socket.error:
            clientSocket.close()
            try:
                if reconnectPrompt():
                    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    clientSocket = connect(clientSocket)
                    console.print(Panel.fit("[green]Connection restored.[/green]", title="Status"))
                else:
                    exitFlag = True
            except socket.error:
                console.print(Panel.fit("[red]Failed to reconnect.[/red]", title="Error"))
                exitFlag = True

except socket.error:
    console.print(Panel.fit("[red]Server unavailable.[/red]", title="Error"))
except KeyboardInterrupt:
    console.print(Panel.fit("[red]Exiting program.[/red]", title="Exit"))
    
finally:
    clientSocket.close()
