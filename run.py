import os
import socket
import uvicorn


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


if __name__ == "__main__":
    local_ip = get_local_ip()
    port = int(os.environ.get("PORT", 8000))
    print("\n" + "=" * 65)
    print("  Cambodia Population & Family Census Management System")
    print("=" * 65)
    print(f"  Local Access:      http://localhost:{port}")
    print(f"  Wi-Fi / LAN Link:  http://{local_ip}:{port}")
    print(f"  API Docs:          http://{local_ip}:{port}/docs")
    print(f"  Print Form:        http://{local_ip}:{port}/print")
    print("=" * 65)
    print(f"  [INFO] Other devices on the same Wi-Fi can open:")
    print(f"  >>> http://{local_ip}:{port} <<<\n")
    print("=" * 65 + "\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)

