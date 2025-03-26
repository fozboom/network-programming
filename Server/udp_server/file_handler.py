import os
import time
import select
import socket

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from config import BUFFER_SIZE, READ_BUFFER_SIZE, WRITE_BUFFER_SIZE, console, log


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
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"[green]Sending {os.path.basename(self.file_name)}",
                    total=total_to_send,
                )
                seq_num = int(offset / BUFFER_SIZE)
                log.info(
                    f"Sending file {os.path.basename(self.file_name)} from {offset} to {total_to_send}"
                )
                while True:
                    data = file.read(WRITE_BUFFER_SIZE)
                    if not data:
                        break

                    packet = f"{seq_num}:{data.decode('utf-8')}"
                    seq_num += 1

                    start_time = time.time()
                    self.socket.sendto(packet.encode("utf-8"), self.address)

                    end_time = time.time()

                    send_time += end_time - start_time
                    sended_data_size += len(data)
                    progress.update(task, advance=len(data))

                self.socket.sendto(b"FIN", self.address)
                log.info("FIN I SENT")
                while True:
                    try:
                        self.socket.settimeout(1)
                        log.info("Waiting for missing packets")
                        ack, _ = self.socket.recvfrom(BUFFER_SIZE)
                        ack = ack.decode("utf-8")
                        if ack.startswith("RETRY"):
                            log.info(f"Received RETRY: {ack}")
                            seq_num = int(ack.split(":")[1])
                            position = seq_num * BUFFER_SIZE
                            file.seek(position, 0)
                            data = file.read(BUFFER_SIZE)
                            packet = f"{seq_num}:{data.decode('utf-8')}"
                            self.socket.sendto(packet.encode("utf-8"), self.address)
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
            self.socket.sendto(retry_message.encode("utf-8"), self.address)

            data, address = self.socket.recvfrom(READ_BUFFER_SIZE)

            seq_num, file_data = data.split(b":", 1)
            seq_num = int(seq_num.decode("utf-8"))
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
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"[green]Receiving {os.path.basename(self.file_name)}",
                    total=total_to_receive,
                )

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
                            received_packets = self.retry_missing_packets(
                                missing_packets, received_packets
                            )

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

                    seq_num, file_data = data.split(b":", 1)
                    seq_num = int(seq_num.decode("utf-8"))

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
