"""
Descobre o IP deste computador na rede local (Wi-Fi/LAN) — é esse endereço
que o celular vai usar pra falar com o backend, em vez de 127.0.0.1 (que só
funciona dentro da própria máquina).

Rodar:
    python find_lan_ip.py
"""

import socket


def get_lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # não envia nada de verdade — só usa o SO pra descobrir qual interface
        # de rede seria usada pra alcançar a internet, e pega o IP dela
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


if __name__ == "__main__":
    ip = get_lan_ip()
    port = 8787
    print(f"\nIP deste computador na rede local: {ip}")
    print(f"\nNo celular (mesma Wi-Fi), configure a Agnes (⚙) pra usar:")
    print(f"   http://{ip}:{port}   (veja o README sobre HTTPS se a página do app for https)")
    print(f"\nRode o backend assim pra ele aceitar conexões de outros aparelhos:")
    print(f"   uvicorn main:app --host 0.0.0.0 --port {port}\n")
