import os
import time
import select
import socket
import threading
from config import BUFFER_SIZE, READ_BUFFER_SIZE, WRITE_BUFFER_SIZE, console, log


class File:
    def __init__(self, file_name, mode, socket, address):
        self.file_name = file_name
        self.mode = mode
        self.socket = socket
        self.address = address
        self.file_map = None
        self.lock = threading.Lock()

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

            log.info(f"Sending file {os.path.basename(self.file_name)} from {offset} to {file_size} ({total_to_send} bytes)")
            console.print(f"[green]Sending {os.path.basename(self.file_name)} to {self.address}[/]")
            
            seq_num = int(offset / BUFFER_SIZE)
            start_time = time.time()
            
            while True:
                data = file.read(WRITE_BUFFER_SIZE)
                if not data:
                    break

                packet = f"{seq_num}:{data.decode('utf-8')}"
                seq_num += 1

                packet_start_time = time.time()
                with self.lock:
                    self.socket.sendto(packet.encode('utf-8'), self.address)
                packet_end_time = time.time()

                send_time += packet_end_time - packet_start_time
                sended_data_size += len(data)
                
            

            with self.lock:
                self.socket.sendto(b"FIN", self.address)
            log.info(f"FIN sent to {self.address}")
            
            while True:
                try:
                    self.socket.settimeout(1)
                    log.info(f"Waiting for missing packets from {self.address}")
                    ack, _ = self.socket.recvfrom(BUFFER_SIZE)
                    ack = ack.decode("utf-8")
                    if ack.startswith("RETRY"):
                        log.info(f"Received RETRY: {ack} from {self.address}")
                        seq_num = int(ack.split(":")[1])
                        position = seq_num * BUFFER_SIZE
                        file.seek(position, 0)
                        data = file.read(BUFFER_SIZE)
                        packet = f"{seq_num}:{data.decode('utf-8')}"
                        with self.lock:
                            self.socket.sendto(packet.encode("utf-8"), self.address)
                        _ = self.socket.recvfrom(BUFFER_SIZE)
                    elif ack.startswith("FIN_ACK"):
                        break
                except socket.timeout:
                    log.info(f"Timeout waiting for missing packets from {self.address}")
                    break

            end_time = time.time()
            total_time = end_time - start_time
            if total_time > 0:
                speed = (file_size - offset) / total_time / 1024
                log.info(f"File {os.path.basename(self.file_name)} sent to {self.address}. Speed: {speed:.2f} KB/s")
                console.print(f"[bold green]Download completed for {self.address}[/] - Speed: [yellow]{speed:.2f} KB/s[/]")

            return send_time

    def check_missing_packets(self, received_packets):
        missing_packets = []
        for i in range(max(received_packets.keys()) + 1):
            if i not in received_packets:
                missing_packets.append(i)
        return missing_packets

    def retry_missing_packets(self, missing_packets, received_packets):
        log.info(f"Retrying missing packets for {self.address}: {missing_packets}")
        for seq_num in missing_packets:
            log.info(f"Sending RETRY: {seq_num} to {self.address}")
            retry_message = f"RETRY:{seq_num}"
            with self.lock:
                self.socket.sendto(retry_message.encode("utf-8"), self.address)

            data, address = self.socket.recvfrom(READ_BUFFER_SIZE)

            seq_num, file_data = data.split(b":", 1)
            seq_num = int(seq_num.decode("utf-8"))
            log.info(f"Received RETRY: {seq_num} from {self.address}")
            received_packets[seq_num] = file_data
            with self.lock:
                self.socket.sendto(b"ACK", address)
            log.info(f"Sent ACK: {seq_num} to {self.address}")
        
        new_missing_packets = self.check_missing_packets(received_packets)
        if new_missing_packets:
            self.retry_missing_packets(new_missing_packets, received_packets)

        return received_packets

    def recv_file(self, file_size, offset):
        if file_size == offset:
            log.info(f"File {self.file_name} is already downloaded from {self.address}")
            return

        recv_data_size = 0
        with open(self.file_name, self.mode) as file:
            file.seek(0, os.SEEK_END)
            offset = os.path.getsize(self.file_name)
            log.info(f"File {self.file_name} offset: {offset} for {self.address}")
            total_to_receive = file_size - offset
            log.info(f"File {self.file_name} total to receive: {total_to_receive} from {self.address}")
            console.print(f"[green]Receiving {os.path.basename(self.file_name)} from {self.address}[/]")

            received_packets = {}
            start_time = time.time()
            
            while True:
                data, address = self.socket.recvfrom(READ_BUFFER_SIZE)
                recv_data_size += len(data)

                if data == b"FIN":
                    log.info(f"Received FIN from {self.address}")
                    missing_packets = self.check_missing_packets(received_packets)
                    if missing_packets:
                        log.info(f"Missing packets from {self.address}: {missing_packets}")
                        received_packets = self.retry_missing_packets(
                            missing_packets, received_packets
                        )

                    log.info(f"Sending FIN_ACK to {self.address}")
                    with self.lock:
                        self.socket.sendto(b"FIN_ACK", address)
                    _ = self.socket.recvfrom(BUFFER_SIZE)
                    break

                if data == b"CTRL_C":
                    log.info(f"CTRL_C received from {self.address}, stopping")

                    curr_seq = -1
                    for seq_num in sorted(received_packets.keys()):
                        if seq_num - 1 != curr_seq:
                            log.info(f"Missing packet from {self.address}: {seq_num}")
                            break
                        curr_seq = seq_num
                        file.write(received_packets[seq_num])
                    return

                if not data:
                    log.info(f"File {self.file_name} received from {self.address}, stopping")
                    break

                seq_num, file_data = data.split(b":", 1)
                seq_num = int(seq_num.decode("utf-8"))

                received_packets[seq_num] = file_data
                
                # Периодически выводим статус приема
                if len(received_packets) % 100 == 0:
                    progress_percent = min(100, int((recv_data_size / total_to_receive) * 100))
                    log.info(f"Receiving progress from {self.address}: {progress_percent}% ({recv_data_size}/{total_to_receive} bytes)")

            end_time = time.time()
            transfer_time = end_time - start_time

            if transfer_time > 0:
                speed = recv_data_size / transfer_time / 1024
                log.info(f"Average receive speed from {self.address}: {speed:.2f} KB/s")
                console.print(f"[bold green]Upload completed from {self.address}[/] - Speed: [yellow]{speed:.2f} KB/s[/]")

            log.info(f"Writing {len(received_packets)} packets to file from {self.address}")
            sorted_seq_nums = sorted(received_packets.keys())

            for seq_num in sorted_seq_nums:
                file.write(received_packets[seq_num])
            received_packets.clear()
