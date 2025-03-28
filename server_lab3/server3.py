import socket
import time
import os
import select
from rich.console import Console

BIND_ADDRESS = "0.0.0.0"
BIND_PORT = 12345
OPT_INTERVAL = 10
OPT_COUNT = 3
FRAME_SIZE = 8192

console = Console()

# Track transfer progress
transfer_progress = {}  # {fileno: (total_size, transferred, filename, is_upload, last_update_time)}
PROGRESS_UPDATE_INTERVAL = 1.0  # seconds between progress updates

def setOptions(clientSocket):
    clientSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    clientSocket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    clientSocket.setsockopt(socket.SOL_TCP, socket.TCP_USER_TIMEOUT, 30000)
    clientSocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, OPT_INTERVAL)
    clientSocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, OPT_INTERVAL)
    clientSocket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, OPT_COUNT)

    return clientSocket

def downloadStart(conn, fileName, commandText):
    if not os.path.exists(fileName):
        conn.send("0".encode())
        return (False, f"File \"{fileName}\" not found.")
    
    conn.send("1".encode())
    
    file = open(fileName, 'rb')
    fileSize = os.path.getsize(fileName)
    offset = int(conn.recv(FRAME_SIZE).decode())
    conn.send(str(fileSize).encode())
    file.seek(offset, 0)

    socketsToWrite.append(conn)
    setFileProperties(conn, True, file, fileSize, offset, commandText)
    printStartFileLoading(conn, fileName, False)
    
    # Initialize progress tracking
    fileno = conn.fileno()
    transfer_progress[fileno] = (fileSize, offset, fileName, False, time.time())
    
    return (True, None)

def downloadFile(conn):
    data = properties[conn.fileno()][2].read(FRAME_SIZE)

    if data:
        conn.send(data)
        
        # Update progress
        fileno = conn.fileno()
        if fileno in transfer_progress:
            total, transferred, filename, is_upload, last_update = transfer_progress[fileno]
            transferred += len(data)
            current_time = time.time()
            
            # Print progress update if enough time has passed
            if current_time - last_update >= PROGRESS_UPDATE_INTERVAL:
                percent = (transferred / total) * 100
                console.print(f"[blue]Sending {filename}: {transferred}/{total} bytes ({percent:.1f}%)")
                last_update = current_time
                
            transfer_progress[fileno] = (total, transferred, filename, is_upload, last_update)
            
        return False
    else:
        # Complete progress
        fileno = conn.fileno()
        if fileno in transfer_progress:
            total, transferred, filename, is_upload, _ = transfer_progress[fileno]
            percent = (transferred / total) * 100
            console.print(f"[green]Completed sending {filename}: {transferred}/{total} bytes ({percent:.1f}%)")
            del transfer_progress[fileno]
        return True

def downloadEnd(conn):
    properties[conn.fileno()][2].close()
    socketsToWrite.remove(conn)
    command = properties[sock.fileno()][5]
    setFileProperties(conn, False, None, None, None, "")
    return command, "File transferred successfully."

def uploadStart(conn, fileName, commandText):
    clientHasFile = conn.recv(1).decode()
    if clientHasFile == "0":
        return (False, conn.recv(FRAME_SIZE).decode())

    mode = 'ab' if os.path.exists(fileName) else 'wb+'

    file = open(fileName, mode)
    fileSize = int(conn.recv(FRAME_SIZE).decode())
    conn.send(str(os.path.getsize(fileName)).encode())
    offset = os.path.getsize(fileName)
    file.seek(0, os.SEEK_END)

    setFileProperties(conn, True, file, fileSize, offset, commandText)
    printStartFileLoading(conn, fileName, True)
    
    # Initialize progress tracking
    fileno = conn.fileno()
    remaining = fileSize - offset
    transfer_progress[fileno] = (fileSize, offset, fileName, True, time.time())
    
    return (True, None)

def uploadFile(conn):
    fileno = conn.fileno()
    if properties[fileno][3] > properties[fileno][4]:
        data = conn.recv(min(FRAME_SIZE, properties[fileno][3]))
        properties[fileno][3] -= len(data)
        properties[fileno][2].write(data)
        
        # Update progress
        if fileno in transfer_progress:
            total, transferred, filename, is_upload, last_update = transfer_progress[fileno]
            transferred += len(data)
            current_time = time.time()
            
            # Print progress update if enough time has passed
            if current_time - last_update >= PROGRESS_UPDATE_INTERVAL:
                percent = (transferred / total) * 100
                console.print(f"[green]Receiving {filename}: {transferred}/{total} bytes ({percent:.1f}%)")
                last_update = current_time
                
            transfer_progress[fileno] = (total, transferred, filename, is_upload, last_update)

    if properties[fileno][3] > properties[fileno][4]:
        return False
    else:
        # Complete progress
        if fileno in transfer_progress:
            total, transferred, filename, is_upload, _ = transfer_progress[fileno]
            percent = (transferred / total) * 100
            console.print(f"[blue]Completed receiving {filename}: {transferred}/{total} bytes ({percent:.1f}%)")
            del transfer_progress[fileno]
        return True

def uploadEnd(conn):
    properties[conn.fileno()][2].close()
    command = properties[sock.fileno()][5]
    setFileProperties(conn, False, None, None, None, "")
    return command, "File uploaded successfully."

def echo(data):
    return data 

def _time():
    currentTime = time.asctime(time.localtime())
    return "Server time: " + currentTime

def exit():
    return "Disconnecting from server..."

def handleCommand(conn, clientInput):
    command, argument = clientInput.partition(" ")[::2]

    match (command.lower()):
        case "echo":
            response = echo(argument)

        case "time":
            response = _time()

        case "download":
            response = downloadStart(conn, argument, clientInput)

        case "upload":
            response = uploadStart(conn, argument, clientInput)

        case "exit":
            response = exit()

        case _:
            response = "Command not found!"

    return command, response

def printLog(clientInput, response, addr):
    print(f"User command from {addr}")
    print(f"Content: {clientInput}")
    print(f"Response: {response}\n")

def printStartFileLoading(conn, fileName, dir):
    if dir:
        print(f"\nStarted receiving file {fileName}\n"
              f"Sender: {properties[conn.fileno()][0][0]}\n")
    else:
        print(f"\nStarted sending file {fileName}\n"
              f"Recipient: {properties[conn.fileno()][0][0]}\n")

def unregClient(conn):
    # Clean up progress tracking if client disconnects during transfer
    fileno = conn.fileno()
    if fileno in transfer_progress:
        del transfer_progress[fileno]
    
    del properties[conn.fileno()]
    connections.remove(conn)
    conn.close()
    print("Total connected:", len(connections) - 1, '\n')

def regClient(conn, addr):
    connections.append(conn)
    properties[conn.fileno()] = [addr, False, None, None, None, ""]
    print("Total connected:", len(connections) - 1, '\n')

def setFileProperties(conn, loading, fd, bytesRemaining, offset, commandText):
    properties[conn.fileno()] = [properties[conn.fileno()][0], loading, fd, bytesRemaining, offset, commandText]

#------------

try:
    connections = []
    socketsToWrite = []
    properties = {}
    # properties[0] = адрес
    # properties[1] = наличие загрузки файла
    # properties[2] = файловый дескриптор
    # properties[3] = байтов осталось
    # properties[4] = смещение
    # properties[5] = текст команды

    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serverSocket = setOptions(serverSocket)
    serverSocket.bind((BIND_ADDRESS, BIND_PORT))
    serverSocket.listen()

    serverSocket.setblocking(False)

    connections.append(serverSocket)

    print("Server started.\n")

    while (True):
        readReady, writeReady, socketsWithErrors = select.select(connections, socketsToWrite, connections)

        for sock in readReady:
            if sock == serverSocket:
                clientConn, clientAddr = serverSocket.accept()
                print("New connection detected\n" + "Address:", clientAddr[0])
                regClient(clientConn, clientAddr)
                continue

            try:
                if properties[sock.fileno()][1] == True:
                    end = uploadFile(sock)
                    if (end):
                        command, response = uploadEnd(sock)
                        sock.send(response.encode())
                        printLog(command, response, properties[sock.fileno()][0])
                    continue

                clientInput = sock.recv(FRAME_SIZE).decode()
                if not clientInput:
                    print('Connection lost with', properties[sock.fileno()][0])
                    if sock in socketsToWrite:
                        socketsToWrite.remove(sock)
                    unregClient(sock)
                    continue

                else:
                    command, response = handleCommand(sock, clientInput)
                    if ((command == 'upload' or command == 'download') and response[0] == True):
                        continue
                    
                    sock.send((response[1] if type(response) is tuple else response).encode())
                    printLog(clientInput, response[1] if type(response) is tuple else response, properties[sock.fileno()][0])

                    if clientInput == 'exit':
                        print('Client', properties[sock.fileno()][0], 'disconnected.')
                        unregClient(sock)

            except socket.error:
                print('\nConnection error with', properties[sock.fileno()][0])
                if sock in socketsToWrite:
                    socketsToWrite.remove(sock)
                unregClient(sock)
        
        for sock in writeReady:
            try:
                if properties[sock.fileno()][1] == True:
                    end = downloadFile(sock)
                    if (end):
                        command, response = downloadEnd(sock)
                        sock.send(response.encode())
                        printLog(command, response, properties[sock.fileno()][0])

            except socket.error:
                print('\nConnection error with', properties[sock.fileno()][0])
                if sock in socketsToWrite:
                    socketsToWrite.remove(sock)
                unregClient(sock)

        for sock in socketsWithErrors:
            print('\nConnection error with', properties[sock.fileno()][0])
            if sock in socketsToWrite:
                socketsToWrite.remove(sock)
            unregClient(sock)

except KeyboardInterrupt:
    print("\nShutting down.\n")