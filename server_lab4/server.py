import os
import select
import socket
import sys
import threading

from rich.panel import Panel

from commander import ServerCommander
from config import (
    BUFFER_SIZE,
    UPLOAD_PATH,
    SERVER_FILES_PATH,
    SIZE_FOR_WRITE,
    MAX_BUFFER,
    WRITE_BUFFER_SIZE,
    HOST,
    PORT,
    console,
    log,
    ensure_directories,
)


class Server:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_running = True
        self.active_clients = {}  # Dictionary to track active clients and their state
        self.lock = threading.Lock()  # Lock for thread-safe operations
        self.thread_count = 0  # Счетчик созданных потоков

    def start(self):
        self.server_socket.setsockopt(
            socket.SOL_SOCKET, socket.SO_SNDBUF, WRITE_BUFFER_SIZE * SIZE_FOR_WRITE
        )
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, MAX_BUFFER)
        log.info(
            f"READ BUFFER: {self.server_socket.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)}"
        )

        try:
            self.server_socket.bind((self.host, self.port))
            ensure_directories()

            console.print(
                Panel.fit(
                    f"[bold green]UDP Server started[/]\n"
                    f"Listening on: [cyan]{self.host}:{self.port}[/]\n"
                    f"Upload directory: [yellow]{os.path.abspath(UPLOAD_PATH)}[/]\n"
                    f"Server files: [yellow]{os.path.abspath(SERVER_FILES_PATH)}[/]"
                )
            )

            self.request_listener()
        except OSError as e:
            log.error(f"Failed to start server: {e}")
            console.print(f"[bold red]ERROR:[/] {e}")

    def stop(self):
        self.server_running = False
        self.server_socket.close()
        log.info(f"Server stopped. Total threads created: {self.thread_count}")
        console.print(f"[bold yellow]Server is shutting down. Total threads created: {self.thread_count}. Goodbye![/]")

    def handle_client_request(self, msg, client_address):
        """Handle a client request in a separate thread"""
        thread_id = threading.get_ident()
        log.info(f"Thread {thread_id} started for client {client_address}")
        
        try:
            # Create a new commander for this client if it doesn't exist
            with self.lock:
                if client_address not in self.active_clients:
                    commander = ServerCommander(self.server_socket)
                    commander.set_client_address(client_address)
                    self.active_clients[client_address] = commander
                    log.info(f"New client {client_address} registered in thread {thread_id}")
                else:
                    commander = self.active_clients[client_address]
                    log.info(f"Using existing commander for client {client_address} in thread {thread_id}")

            # Process the command
            log.info(f"Thread {thread_id} processing command from {client_address}: {msg.decode('utf-8')[:50]}...")
            commander.handle_command(msg.decode("utf-8"))
            log.info(f"Thread {thread_id} completed command processing for {client_address}")

            # Remove inactive clients
            with self.lock:
                if not commander.client_is_active:
                    del self.active_clients[client_address]
                    log.info(f"Client {client_address} removed from active clients in thread {thread_id}")
                
                active_count = len(self.active_clients)
                log.info(f"Active clients count: {active_count}")
        except Exception as e:
            log.error(f"Error in thread {thread_id} handling request from {client_address}: {e}")
        finally:
            log.info(f"Thread {thread_id} for client {client_address} finished")

    def request_listener(self):
        """Listen for incoming requests and spawn threads to handle them"""
        log.info("Request listener started")
        
        while self.server_running:
            try:
                # Use select to check if data is available
                readable, _, _ = select.select([self.server_socket], [], [], 0.1)

                if self.server_socket in readable:
                    try:
                        # Receive data from any client
                        msg, client_address = self.server_socket.recvfrom(BUFFER_SIZE)
                        
                        # Increment thread counter
                        with self.lock:
                            self.thread_count += 1
                            current_thread_count = self.thread_count
                        
                        # Log the incoming request and thread creation
                        log.info(f"Received request from {client_address}, spawning thread #{current_thread_count}")
                        console.print(f"[cyan]New request from {client_address} - creating thread #{current_thread_count}[/]")
                        
                        # Create and start a new thread to handle this request
                        client_thread = threading.Thread(
                            target=self.handle_client_request,
                            args=(msg, client_address),
                            daemon=True,
                            name=f"ClientThread-{current_thread_count}-{client_address[0]}:{client_address[1]}"
                        )
                        client_thread.start()
                        
                        # Log active threads
                        active_thread_count = threading.active_count()
                        log.info(f"Active threads: {active_thread_count}, Total created: {current_thread_count}")
                        
                    except BlockingIOError:
                        # No data available, continue to next iteration
                        pass

            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                log.error(f"Error in request listener: {e}")
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