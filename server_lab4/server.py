import os
import select
import socket
import sys

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
)


class Server:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_running = True
        self.active_clients = {}  # Dictionary to track active clients and their state

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
            self.server_socket.setblocking(False)  # Set socket to non-blocking mode

            console.print(
                Panel.fit(
                    f"[bold green]UDP Server started[/]\n"
                    f"Listening on: [cyan]{self.host}:{self.port}[/]\n"
                    f"Upload directory: [yellow]{os.path.abspath(UPLOAD_PATH)}[/]\n"
                    f"Server files: [yellow]{os.path.abspath(SERVER_FILES_PATH)}[/]"
                )
            )

            os.makedirs(UPLOAD_PATH, exist_ok=True)
            os.makedirs(SERVER_FILES_PATH, exist_ok=True)

            self.multiplexed_client_handler()
        except OSError as e:
            log.error(f"Failed to start server: {e}")
            console.print(f"[bold red]ERROR:[/] {e}")

    def stop(self):
        self.server_running = False
        self.server_socket.close()
        log.info("Server stopped")
        console.print("[bold yellow]Server is shutting down. Goodbye![/]")

    def multiplexed_client_handler(self):
        inputs = [self.server_socket]

        while self.server_running:
            try:
                # Use select to multiplex between different clients
                readable, _, exceptional = select.select(inputs, [], inputs, 0.1)

                for sock in readable:
                    if sock is self.server_socket:
                        # Handle incoming data from any client
                        try:
                            msg, client_address = self.server_socket.recvfrom(
                                BUFFER_SIZE
                            )

                            # Create a new commander for this client if it doesn't exist
                            if client_address not in self.active_clients:
                                commander = ServerCommander(self.server_socket)
                                commander.set_client_address(client_address)
                                self.active_clients[client_address] = commander
                            else:
                                commander = self.active_clients[client_address]

                            # Process the command
                            commander.handle_command(msg.decode("utf-8"))

                            # Remove inactive clients
                            if not commander.client_is_active:
                                del self.active_clients[client_address]

                        except BlockingIOError:
                            # No data available, continue to next iteration
                            pass

                # Check for exceptional conditions
                for sock in exceptional:
                    log.error(f"Exception condition on socket {sock}")
                    inputs.remove(sock)
                    sock.close()

            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                log.error(f"Error in multiplexed handler: {e}")
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
