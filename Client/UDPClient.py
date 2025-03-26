import socket
import time
import os
import select
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TransferSpeedColumn
from rich.console import Console
from time import sleep

RECONNECT_PERIOD = 10
RECONNECT_ATTEMPTS = 6
BUFFER_SIZE = 1024
RCV_BUFFER_SIZE = 16384
SIZE_FOR_WRITE = 32768
SIZE_FOR_READ = 65536

console = Console()

class UDPClient:
    def __init__(self, server_port, server_address):
        self.server_address = server_address
        self.server_port = server_port
        self.sock = self.initialize_sock()

    def initialize_sock(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, BUFFER_SIZE * SIZE_FOR_WRITE)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 425984)
        console.print(f"[bold green]Initialize completed (address: {self.server_address}, port: {self.server_port})[/bold green]")
        return sock

    def wait(self):
        ready_to_read, _, _ = select.select([self.sock], [], [], 1)
        return ready_to_read

    def upload_command(self, file_path):
        if not os.path.exists(file_path):
            console.print("[bold red]No such file[/bold red]")
            return
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        console.print(f"[bold blue]File size: {file_size} bytes[/bold blue]")
        upload_string = f"UPLOAD {file_name} {file_size}"
        console.print(f"[bold blue]Uploading file {file_name} to the server[/bold blue]")
        self.sock.sendto(upload_string.encode(), (self.server_address, self.server_port))
        offset = int(self.sock.recv(BUFFER_SIZE).decode())
        console.print(f"[bold blue]Offset: {offset} bytes[/bold blue]")
        if offset == file_size:
            console.print(f"[bold green]File {file_name} has already been uploaded to the server[/bold green]")
            return
        if offset > file_size:
            offset = 0
        if offset > 0:
            downloadedPart = float(offset / file_size * 100)
            console.print(f"[bold yellow]Part of this file has already been downloaded, downloading will continue from {downloadedPart}%[/bold yellow]")
        send_time = 0
        packet_number = int(offset / BUFFER_SIZE)
        console.print(f"[bold blue]First packet number: {packet_number}[/bold blue]")
        try:
            with open(file_path, "rb") as file:
                file.seek(offset)
                current_position = offset
                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
                    TimeElapsedColumn(),
                    TransferSpeedColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task("Uploading...", total=file_size - offset)
                    while True:
                        data = file.read(BUFFER_SIZE)
                        if not data:
                            console.print(f"[bold green]File {file_name} has been uploaded to the server[/bold green]")
                            break
                        start_upload_time = time.time()
                        packet = f"{packet_number}:{data.decode()}"
                        self.sock.sendto(packet.encode(), (self.server_address, self.server_port))
                        end_upload_time = time.time()
                        send_time += (end_upload_time - start_upload_time)
                        packet_number += 1
                        current_position += len(data)
                        progress.update(task, advance=len(data))
                self.sock.sendto("FIN".encode(), (self.server_address, self.server_port))
                while True:
                    console.print("[bold blue]Waiting for ACK[/bold blue]")
                    data, _ = self.sock.recvfrom(BUFFER_SIZE)
                    ack = data.decode()
                    console.print(f"[bold blue]ACK: {ack}[/bold blue]")
                    if(ack.startswith("RETRY")):
                        ack = ack.split(":")[1]
                        ack = int(ack)
                        current_position = ack * BUFFER_SIZE
                        file.seek(current_position)
                        data = file.read(BUFFER_SIZE)
                        packet = f"{ack}:{data.decode()}"
                        self.sock.sendto(packet.encode(), (self.server_address, self.server_port))
                        sleep(0.07)
                        ack = self.sock.recv(BUFFER_SIZE).decode()
                        console.print(f"[bold blue]ACK from server: {ack}[/bold blue]")
                    if(ack.startswith("FIN_ACK")):
                        break
        finally:
            self.sock.sendto("CTRL_C".encode(), (self.server_address, self.server_port))
            console.print(f"[bold blue]Closing file {file_name}[/bold blue]")
            file.close()
        end_upload_time = time.time()
        send_size = file_size - offset
        upload_speed = "{:.2f}".format(send_size/send_time/1024)
        console.print(f"\n[bold blue]Upload speed: {upload_speed} Kb/s[/bold blue]")


    def check_missing_packets(self, received_packets, sequence_number):
        missing_packets = []
        for i in range(sequence_number, max(received_packets.keys()) + 1):
            if i not in received_packets:
                missing_packets.append(i)
        console.print(f"[bold yellow]Missing packets: {missing_packets}[/bold yellow]")
        return missing_packets

    def retry_missing_packets(self, missing_packets, received_packets):
        for i in missing_packets:
            retry_message = f"RETRY:{i}"
            console.print(f"[bold yellow]Retrying packet {i}[/bold yellow]")
            self.sock.sendto(retry_message.encode(), (self.server_address, self.server_port))
            data, _ = self.sock.recvfrom(BUFFER_SIZE)
            sequence_number, data = data.split(b":", 1)
            sequence_number = int(sequence_number.decode())
            console.print(f"[bold yellow]Received packet {sequence_number}[/bold yellow]")
            received_packets[sequence_number] = data
            ack = f"ACK:{sequence_number}"
            self.sock.sendto(ack.encode(), (self.server_address, self.server_port))
        new_missing_packets = self.check_missing_packets(received_packets, sequence_number + 1)
        if new_missing_packets:
            console.print(f"[bold yellow]Retrying missing packets: {new_missing_packets}[/bold yellow]")
            self.retry_missing_packets(new_missing_packets, received_packets)
        return received_packets

    def download_command(self, file_path):
        download_string = f"DOWNLOAD {file_path}"
        self.sock.sendto(download_string.encode(), (self.server_address, self.server_port))
        file_size = int(self.sock.recv(BUFFER_SIZE).decode())
        if file_size == 0:
            console.print("[bold red]No such file[/bold red]")
            return

        path_parts = file_path.split("/")
        file_name = path_parts[-1]
        downloads_path = "./download_files"
        full_file_path = os.path.join(downloads_path, file_name)
        console.print(f"[bold blue]File size: {file_size} bytes[/bold blue]")
        console.print(f"[bold blue]Downloading file {file_name} from the server[/bold blue]")
        console.print(f"[bold blue]File path: {full_file_path}[/bold blue]")
        if os.path.exists(full_file_path):
            offset = os.path.getsize(full_file_path)
            downloadedPart = offset / file_size * 100
            if offset < file_size:
                console.print(f"[bold yellow]Part of this file has already been downloaded, downloading will continue from {downloadedPart}%[/bold yellow]")
            else:
                console.print(f"[bold green]File {file_name} has already been downloaded to the client[/bold green]")
                return
            mode = "ab"
        else:
            offset = 0
            mode = "wb+"
        console.print(f"[bold blue]Offset: {offset} bytes[/bold blue]")
        self.sock.sendto(str(offset).encode(), (self.server_address, self.server_port))
        receive_packets = {}
        sequence_number = -1

        flag = True
        try:
            with open(full_file_path, mode) as file:
                file.seek(0, os.SEEK_END)
                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
                    TimeElapsedColumn(),
                    TransferSpeedColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task("Downloading...", total=file_size - offset)
                    while self.wait():
                        data = self.sock.recv(RCV_BUFFER_SIZE)
                        if data == b"FIN":
                            console.print(f"[bold green]File {file_name} has been downloaded to the client[/bold green]")
                            missing_packets = self.check_missing_packets(receive_packets, sequence_number)
                            if missing_packets:
                                receive_packets = self.retry_missing_packets(missing_packets, receive_packets)
                            console.print(f"[bold green]Writing file {file_name} and send FIN_ACK[/bold green]")
                            self.sock.sendto(b"FIN_ACK", (self.server_address, self.server_port))
                            flag = False
                            break
                        sequence_number, data = data.split(b":", 1)
                        sequence_number = int(sequence_number.decode())
                        receive_packets[sequence_number] = data
                        offset = offset + len(data)
                        progress.update(task, advance=len(data))
                    for i in sorted(receive_packets.keys()):
                        file.write(receive_packets[i])
        finally:
            try:
                if flag:
                    file = open(full_file_path, mode)
                    console.print(f"[bold blue]Closing file {file_name}[/bold blue]")
                    if receive_packets:
                        x = -1
                        for i in receive_packets.keys():
                            console.print(f"[bold yellow]Writing packet {i}[/bold yellow]")
                            if (i - 1 == x):
                                file.write(receive_packets[i])
                            else:
                                break
                            x = i
                        receive_packets.clear()

                    file.close()
            except Exception as e:
                console.print(f"[bold red]Error: {e}[/bold red]")

class CommandHandler:
    def __init__(self, client):
        self.client = client
        self.main_cycle_flag = True

    def time_command(self):
        self.client.sock.sendto("TIME".encode(), (self.client.server_address, self.client.server_port))
        server_time = self.client.sock.recv(BUFFER_SIZE).decode()
        console.print(f"[bold blue]Server time: {server_time}[/bold blue]")

    def echo_command(self, info):
        if info != "":
            self.client.sock.sendto(f"ECHO {info}".encode(), (self.client.server_address, self.client.server_port))
            echo_string = self.client.sock.recv(BUFFER_SIZE).decode()
            console.print(f"[bold blue]Echo from server: {echo_string}[/bold blue]")
        else:
            console.print("[bold red]You should enter command \"ECHO (parameters)\". Try again[/bold red]")

    def quit_command(self):
        self.main_cycle_flag = False
        self.client.sock.sendto("QUIT".encode(), (self.client.server_address, self.client.server_port))
        console.print("[bold green]Successful exit[/bold green]")

    def main_cycle(self):
        while self.main_cycle_flag:
            key_command = input("> ")

            key_command_arr = key_command.split(maxsplit=1)
            if len(key_command_arr) == 0:
                continue
            first_word = key_command_arr[0].strip().upper()
            arguments = "" if len(key_command_arr) == 1 else key_command_arr[1].strip()

            if first_word == "UPLOAD":
                self.client.upload_command(arguments)
            elif first_word == "DOWNLOAD":
                self.client.download_command(arguments)
            elif first_word == "TIME":
                self.time_command()
            elif first_word == "ECHO":
                self.echo_command(arguments)
            elif first_word == "QUIT" or first_word == "EXIT":
                self.quit_command()
            else:
                console.print("[bold red]Unknown command, try again[/bold red]")
            
        self.client.sock.close()


def main():
    try:
        client = UDPClient(server_port = 12346, server_address="192.168.1.107")
        command_handler = CommandHandler(client)
    except socket.error:
        console.print("[bold red]Connection error[/bold red]")
        exit()
    except (TypeError, ValueError, OverflowError):
        console.print("[bold red]Invalid parameters[/bold red]")
        exit()
    command_handler.main_cycle()


if __name__ == "__main__":
    main()