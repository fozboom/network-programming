"""Configuration settings for the UDP server."""

import os
from logging_setup import setup_logging
from rich.console import Console
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

log = setup_logging()
console = Console()

def ensure_directories():
    """Create necessary directories if they don't exist."""
    os.makedirs(UPLOAD_PATH, exist_ok=True)
    os.makedirs(SERVER_FILES_PATH, exist_ok=True)
