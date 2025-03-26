import argparse
import subprocess

def main():
    parser = argparse.ArgumentParser(description="Выбор клиента: TCP или UDP")
    parser.add_argument("--tcp", action="store_true", help="Запустить TCP клиента")
    parser.add_argument("--udp", action="store_true", help="Запустить UDP клиента")

    args = parser.parse_args()

    if args.tcp:
        subprocess.run(["uv", "run", "Client/TCPClient.py"])
    elif args.udp:
        subprocess.run(["uv", "run", "Client/UDPClient.py"])
    else:
        print("Укажите --tcp или --udp для выбора клиента.")

if __name__ == "__main__":
    main()
