import datetime
import logging
import os
import select
import socket
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)


def setup_logging(log_dir="logs"):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(log_dir, f"udp_server_{current_time}.log")
    
    logger = logging.getLogger("udp_server")
    logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG) 
    file_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    logger.info(f"Logging initialized. Log file: {log_file}")
    return logger

log = setup_logging()

console = Console()

HOST = "0.0.0.0"
PORT = 12348

UPLOAD_PATH = "./upload_files"
SERVER_FILES_PATH = "./server_files/"

READ_BUFFER_SIZE = 16384
WRITE_BUFFER_SIZE = 1024
BUFFER_SIZE = 1024
MAX_BUFFER = 425984
SIZE_FOR_READ = 65536
SIZE_FOR_WRITE = 32768

class File:
    def __init__(self, file_name, mode, socket, address):
        self.file_name = file_name
        self.mode = mode
        self.socket = socket
        self.address = address
        self.file_map = None

    def wait(self, socket):
        readyToRead, _, _ = select.select([socket], [], [], 1)
        return readyToRead

    def send_file(self, offset):
        sended_data_size = 0
        send_time = 0
        with open(self.file_name, self.mode) as file:
            file.seek(int(offset), 0)
            file_size = os.path.getsize(self.file_name)
            total_to_send = file_size - offset
            
            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                "[progress.percentage]{task.percentage:>3.1f}%",
                "•",
                DownloadColumn(),
                "•",
                TransferSpeedColumn(),
                "•",
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"[green]Sending {os.path.basename(self.file_name)}", total=total_to_send)
                seq_num = int(offset/BUFFER_SIZE)
                log.info(f"Sending file {os.path.basename(self.file_name)} from {offset} to {total_to_send}")
                while True:
                    data = file.read(WRITE_BUFFER_SIZE)
                    if not data:
                        break
                   
                    packet = f"{seq_num}:{data.decode('utf-8')}"    
                    seq_num += 1
                    
                    start_time = time.time()
                    self.socket.sendto(packet.encode('utf-8'), self.address)
                    
                    end_time = time.time()
                    
                    send_time += end_time - start_time
                    sended_data_size += len(data)
                    progress.update(task, advance=len(data))
                    
                self.socket.sendto(b"FIN", self.address)
                log.info('FIN I SENT')
                while True:
                    try:
                        self.socket.settimeout(1)
                        log.info("Waiting for missing packets")
                        ack, _ = self.socket.recvfrom(BUFFER_SIZE)
                        ack = ack.decode('utf-8')
                        if ack.startswith("RETRY"):
                            log.info(f"Received RETRY: {ack}")
                            seq_num = int(ack.split(":")[1])
                            position = seq_num * BUFFER_SIZE
                            file.seek(position, 0)
                            data = file.read(BUFFER_SIZE)
                            packet = f"{seq_num}:{data.decode('utf-8')}"
                            self.socket.sendto(packet.encode('utf-8'), self.address)
                            _ = self.socket.recvfrom(BUFFER_SIZE)
                        elif ack.startswith("FIN_ACK"):
                            break
                    except socket.timeout:
                        log.info("Timeout waiting for missing packets")
                        break
                    
            
            return send_time
     
     
    def check_missing_packets(self, received_packets):
        missing_packets = []
        for i in range(max(received_packets.keys()) + 1):
            if i not in received_packets:
                missing_packets.append(i)
        return missing_packets
    
    def retry_missing_packets(self, missing_packets, received_packets):
        log.info(f"Retrying missing packets: {missing_packets} in recursion")
        for seq_num in missing_packets:
            log.info(f"Sending RETRY: {seq_num}")
            retry_message = f"RETRY:{seq_num}"
            self.socket.sendto(retry_message.encode('utf-8'), self.address)
            
            data, address = self.socket.recvfrom(READ_BUFFER_SIZE)
            
            seq_num, file_data = data.split(b':', 1)
            seq_num = int(seq_num.decode('utf-8'))
            log.info(f"Received RETRY: {seq_num}")
            received_packets[seq_num] = file_data
            self.socket.sendto(b"ACK", address)
            log.info(f"Sent ACK: {seq_num}")
        new_missing_packets = self.check_missing_packets(received_packets)
        if new_missing_packets:
            self.retry_missing_packets(new_missing_packets, received_packets)
            
        return received_packets            
    
    def recv_file(self, file_size, offset):
        if file_size == offset:
            log.info(f"File {self.file_name} is already downloaded")
            return
        
        recv_data_size = 0
        with open(self.file_name, self.mode) as file:
            file.seek(0, os.SEEK_END)
            offset = os.path.getsize(self.file_name)
            log.info(f"File {self.file_name} offset: {offset}")
            total_to_receive = file_size - offset
            log.info(f"File {self.file_name} total to receive: {total_to_receive}")
            
            received_packets = {}
            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                "[progress.percentage]{task.percentage:>3.1f}%",
                "•",
                DownloadColumn(),
                "•",
                TransferSpeedColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"[green]Receiving {os.path.basename(self.file_name)}", total=total_to_receive)
                
                start_time = time.time()
                while True:
                    data, address = self.socket.recvfrom(READ_BUFFER_SIZE)
                    recv_data_size += len(data)
                    
                    if data == b"FIN":
                        log.info("Received FIN before missing packets")
                        missing_packets = []
                        for i in range(max(received_packets.keys()) + 1):
                            if i not in received_packets:
                                missing_packets.append(i)
                        
                        
                        missing_packets = self.check_missing_packets(received_packets)
                        if missing_packets:
                            log.info(f"Missing packets: {missing_packets}")
                            received_packets = self.retry_missing_packets(missing_packets, received_packets)
                    
                        log.info("Sending FIN_ACK")
                        self.socket.sendto(b"FIN_ACK", address)
                        _ = self.socket.recvfrom(BUFFER_SIZE)   
                        break
                    
                    if data == b"CTRL_C":
                        log.info("CTRL_C received, stopping")
                        
                        curr_seq = -1
                        for seq_num in sorted(received_packets.keys()):
                            if seq_num - 1 != curr_seq:
                                log.info(f"Missing packet: {seq_num}")
                                break
                            curr_seq = seq_num
                            file.write(received_packets[seq_num])
                        return
                            
                            
                    if not data:
                        log.info(f"File {self.file_name} received, stopping")
                        break
                    
                    seq_num, file_data = data.split(b':', 1)
                    seq_num = int(seq_num.decode('utf-8'))
                    
                    received_packets[seq_num] = file_data
                    
                    progress.update(task, advance=len(file_data))
                
                end_time = time.time()
                transfer_time = end_time - start_time
                
                if transfer_time > 0:
                    speed = recv_data_size / transfer_time / 1024
                    log.info(f"Average receive speed: {speed:.2f} KB/s")
                    
                log.info(f"Writing {len(received_packets)} packets to file")
                sorted_seq_nums = sorted(received_packets.keys())

                for seq_num in sorted_seq_nums:
                    file.write(received_packets[seq_num])
                received_packets.clear()
class ServerCommander:
    def __init__(self, server_socket):
        self.server_socket = server_socket
        self.client_is_active = True

    
    def send_msg(self, data):
        self.server_socket.sendto(str(data).encode("utf-8"), self.client_address)


    def recv_msg(self):
        recv_data, recv_address = self.server_socket.recvfrom(BUFFER_SIZE)
        return (recv_data.decode("utf-8"), recv_address)


    def exec_quit(self):
        self.client_is_active = False
        log.info(f"Client {self.client_address} disconnected")


    def exec_time(self):
        current_time_formatted = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
            
            file = File(SERVER_FILES_PATH + file_name, "rb", self.server_socket, self.client_address)
            send_time = file.send_file(file_offset)
            
            if send_time > 0:
                speed = (file_size - file_offset) / send_time / 1024
                log.info(f"Download completed. Speed: {speed:.2f} KB/s")
                console.print(Panel(f"[bold green]Download completed[/]\nSpeed: [yellow]{speed:.2f} KB/s[/]"))


    def exec_upload(self, args):
        path_parts = ' '.join(args.split()[:-1]).split("/")
        full_file_name = os.path.join(UPLOAD_PATH, path_parts[-1])
        

        if os.path.exists(full_file_name):
            mode = 'ab'
            file_offset = os.path.getsize(full_file_name)
        else:
            mode = 'wb+'
            file_offset = 0 
            
        file_size = int(args.split()[-1])
        log.info(f"Upload request: {path_parts[-1]}, size: {file_size}, offset: {file_offset}")
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
            console.print(Panel(f"[bold green]Upload completed[/]\nSpeed: [yellow]{speed:.2f} KB/s[/]"))


    def handle_command(self, msg):
        if len(msg) == 0:
            return
            
        log.info(f"Request from {self.client_address}: {msg}")
        
        full_cmd = msg.split(maxsplit=1)
        command = full_cmd[0].strip().upper()
        arguments = "" if len(full_cmd) == 1 else full_cmd[1].strip()

        console.print(Panel(f"[bold]Command:[/] [cyan]{command}[/]", 
                           subtitle=f"From: {self.client_address[0]}:{self.client_address[1]}"))

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

        
class Server:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_running = True
    

    def start(self):
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, WRITE_BUFFER_SIZE * SIZE_FOR_WRITE)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, MAX_BUFFER)
        log.info(f"READ BUFFER: {self.server_socket.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)}")
        
        try:
            self.server_socket.bind((self.host, self.port))
            console.print(Panel.fit(
                f"[bold green]UDP Server started[/]\n"
                f"Listening on: [cyan]{self.host}:{self.port}[/]\n"
                f"Upload directory: [yellow]{os.path.abspath(UPLOAD_PATH)}[/]\n"
                f"Server files: [yellow]{os.path.abspath(SERVER_FILES_PATH)}[/]"
            ))
            
            os.makedirs(UPLOAD_PATH, exist_ok=True)
            os.makedirs(SERVER_FILES_PATH, exist_ok=True)
            
            self.client_handler()
        except OSError as e:
            log.error(f"Failed to start server: {e}")
            console.print(f"[bold red]ERROR:[/] {e}")


    def stop(self):
        self.server_running = False
        self.server_socket.close()
        log.info("Server stopped")
        console.print("[bold yellow]Server is shutting down. Goodbye![/]")

    
    def client_handler(self):
        commander = ServerCommander(self.server_socket)
        
        while commander.client_is_active:
            try:
                msg, client_address = self.server_socket.recvfrom(BUFFER_SIZE)
                self.client_address = client_address
                commander.set_client_address(client_address)
                commander.handle_command(msg.decode("utf-8"))
            except socket.timeout:
                pass
            except Exception as e:
                log.error(f"Error handling client: {e}")
                console.print(f"[bold red]ERROR:[/] {e}")
        
        self.server_socket.close()


if __name__ == "__main__":
    try:
        console.print("[bold blue]===== UDP File Server =====")
        server = Server(HOST, PORT)
        server.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Keyboard interrupt detected[/]")
        server.stop()
        sys.exit(0)
    except Exception as e:
        log.exception("Unhandled exception")
        console.print(f"[bold red]FATAL ERROR:[/] {e}")
        sys.exit(1)