import socket
import time
import os
import sys
import select
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TransferSpeedColumn
from rich.console import Console
from time import sleep

mainCycleFlag = True
RECONNECT_PERIOD = 10
RECONNECT_ATTEMPTS = 6
BUFFER_SIZE = 1024
RCV_BUFFER_SIZE = 16384
SIZE_FOR_WRITE = 32768
SIZE_FOR_READ = 65536
server_address = "192.168.1.107"
client_address = "192.168.1.105"
port = 0

console = Console()

def sendInfo(info, sock): #+
    sock.sendto(str(info).encode('utf-8'), (server_address, port))


def receiveInfo(sock): #+
    ready_to_read, _, _ = select.select([sock], [], [], 1)
    if ready_to_read:
        data, _ = sock.recvfrom(BUFFER_SIZE)
        return data.decode('utf-8')
    return "ABRACADABRA"


def wait(sock):
    ready_to_read, _, _ = select.select([sock], [], [], 1)
    return ready_to_read


def uploadCommand(filePath, sock):
    if not os.path.exists(filePath):
        console.print("[bold red]No such file[/bold red]")
        return
    fileName = os.path.basename(filePath)
    fileSize = os.path.getsize(filePath)
    console.print(f"[bold blue]File size: {fileSize} bytes[/bold blue]")
    uploadString = f"UPLOAD {fileName} {fileSize}"
    console.print(f"[bold blue]Uploading file {fileName} to the server[/bold blue]")
    sendInfo(uploadString, sock)
    offset = int(receiveInfo(sock))
    console.print(f"[bold blue]Offset: {offset} bytes[/bold blue]")
    if offset == fileSize:
        console.print(f"[bold green]File {fileName} has already been uploaded to the server[/bold green]")
        return
    if offset > fileSize:
        offset = 0
    if offset > 0:
        downloadedPart = float(offset / fileSize * 100)
        console.print(f"[bold yellow]Part of this file has already been downloaded, downloading will continue from {downloadedPart}%[/bold yellow]")
    sendTime = 0
    packet_number = 0
    try:
        with open(filePath, "rb") as file:
            file.seek(offset)
            currentPosition = offset
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
                TimeElapsedColumn(),
                TransferSpeedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Uploading...", total=fileSize - offset)
                while True:
                    data = file.read(BUFFER_SIZE)
                    if not data:
                        console.print(f"[bold green]File {fileName} has been uploaded to the server[/bold green]")
                        break
                    startUploadTime = time.time()
                    packet = f"{packet_number}:{data.decode()}"
                    # console.print(f"[bold blue]Packet: {packet}[/bold blue]")
                    sock.sendto(packet.encode(), (server_address, port))
                    endUploadTime = time.time()
                    sendTime += (endUploadTime - startUploadTime)
                    packet_number += 1
                    currentPosition += len(data)
                    progress.update(task, advance=len(data))
            sock.sendto("FIN".encode(), (server_address, port))
            while True:
                console.print("[bold blue]Waiting for ACK[/bold blue]")
                data, _ = sock.recvfrom(BUFFER_SIZE)
                ack = data.decode()
                console.print(f"[bold blue]ACK: {ack}[/bold blue]")
                if(ack.startswith("RETRY")):
                    ack = ack.split(":")[1]
                    ack = int(ack)
                    currentPosition = ack * BUFFER_SIZE
                    file.seek(currentPosition)
                    data = file.read(BUFFER_SIZE)
                    packet = f"{ack}:{data.decode()}"
                    sock.sendto(packet.encode(), (server_address, port))
                    ack = receiveInfo(sock)
                    console.print(f"[bold blue]ACK: {ack}[/bold blue]")
                if(ack.startswith("FIN_ACK")):
                    break
    finally:
        file.close()
    endUploadTime = time.time()
    sendSize = fileSize - offset
    uploadSpeed = "{:.2f}".format(sendSize/sendTime/1024)
    console.print(f"\n[bold blue]Upload speed: {uploadSpeed} Kb/s[/bold blue]")


def downloadCommand(filePath, sock):
    downloadString = f"DOWNLOAD {filePath}"
    sendInfo(downloadString, sock)
    fileSize = int(receiveInfo(sock))
    if fileSize == 0:
        console.print("[bold red]No such file[/bold red]")
        return

    pathParts = filePath.split("/")
    fileName = pathParts[-1]
    downloadsPath = "./download_files"
    fullFilePath = os.path.join(downloadsPath, fileName)
    if os.path.exists(fullFilePath):
        offset = os.path.getsize(fullFilePath)
        downloadedPart = offset / fileSize * 100
        if offset < fileSize:
            console.print(f"[bold yellow]Part of this file has already been downloaded, downloading will continue from {downloadedPart}%[/bold yellow]")
        else:
            console.print(f"[bold green]File {fileName} has already been downloaded to the client[/bold green]")
            return
        mode = "ab"
    else:
        offset = 0
        mode = "wb+"
    sendInfo(offset, sock)
    try:
        with open(fullFilePath, mode) as file:
            file.seek(0, os.SEEK_END)
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
                TimeElapsedColumn(),
                TransferSpeedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Downloading...", total=fileSize)
                receive_packets = {}
                while wait(sock):
                    data = sock.recv(RCV_BUFFER_SIZE)
                    if data == b"FIN":
                        break
                    sequenceNumber, data = data.split(b":", 1)
                    sequenceNumber = int(sequenceNumber.decode())
                    receive_packets[sequenceNumber] = data
                    ack = f"ACK:{sequenceNumber}"
                    sock.sendto(ack.encode(), (server_address, port))
                    offset = offset + len(data)
                    progress.update(task, advance=len(data))
                for i in sorted(receive_packets.keys()):
                    file.write(receive_packets[i])
                receive_packets.clear()
    finally:
        file.close()


def timeCommand(sock): #+
    sendInfo("TIME", sock)
    serverTime = receiveInfo(sock)
    console.print(f"[bold blue]Server time: {serverTime}[/bold blue]")


def echoCommand(info, sock): #+
    if info != "":
        sendInfo(f"ECHO {info}", sock)
        echoString = receiveInfo(sock)
        console.print(f"[bold blue]Echo from server: {echoString}[/bold blue]")
    else:
        console.print("[bold red]You should enter command \"ECHO (parameters)\". Try again[/bold red]")


def quitCommand(sock): #+
    global mainCycleFlag
    mainCycleFlag = False
    sendInfo("QUIT", sock)
    console.print("[bold green]Successful exit[/bold green]")


def mainCycle(sock): #+
    global mainCycleFlag
    while mainCycleFlag:
        # console.print("=================================")
        keyCommand = input("> ")

        keyCommandArr = keyCommand.split(maxsplit=1)
        if len(keyCommandArr) == 0:
            continue
        first_word = keyCommandArr[0].strip().upper()
        arguments = "" if len(keyCommandArr) == 1 else keyCommandArr[1].strip()

        if first_word == "UPLOAD":
            uploadCommand(arguments, sock)
        elif first_word == "DOWNLOAD":
            downloadCommand(arguments, sock)
        elif first_word == "TIME":
            timeCommand(sock)
        elif first_word == "ECHO":
            echoCommand(arguments, sock)
        elif first_word == "QUIT" or first_word == "EXIT":
            quitCommand(sock)
        else:
            console.print("[bold red]Unknown command, try again[/bold red]")
        
    sock.close()


def initializeSock(): #+
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, BUFFER_SIZE * SIZE_FOR_WRITE)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 425984)
    sock.bind((client_address, port))
    console.print(f"[bold green]Initialize completed (address: {client_address}, port: {port})[/bold green]")
    return sock


def main(): #+
    global client_address, server_address, port
    try:
        port = 12345
        sock = initializeSock()
    except socket.error:
        console.print("[bold red]Connection error[/bold red]")
        exit()
    except (TypeError, ValueError, OverflowError):
        console.print("[bold red]Invalid parameters[/bold red]")
        exit()
    mainCycle(sock)


if __name__ == "__main__":
    main()