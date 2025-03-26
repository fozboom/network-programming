import argparse
from UDPClient import main as udp_main
from TCPClient import TCPClient

def main():
    parser = argparse.ArgumentParser(description="Выбор клиента: TCP или UDP")
    parser.add_argument("--tcp", action="store_true", help="Запустить TCP клиента")
    parser.add_argument("--udp", action="store_true", help="Запустить UDP клиента")

    args = parser.parse_args()

    if args.tcp:
        client = TCPClient("192.168.1.107", 12346)
        client.run()
    elif args.udp:
        udp_main()
    else:
        print("Укажите --tcp или --udp для выбора клиента.")

if __name__ == "__main__":
    main()
