import Server.tcp_server.TCPServer as TCPServer
import Server.udp_server.server as server

if __name__ == "__main__":
    tcp_server = TCPServer.TCPServer()
    udp_server = server.UDPServer()
    tcp_server.start()
    udp_server.start()
