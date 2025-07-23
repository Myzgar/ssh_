import asyncio
import os
import json
import time
import paramiko
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from status import StatusUpdater

# Config yükle
with open("config.json", "r") as f:
    config = json.load(f)

REMOTE_PATH = config["target"]
LOCAL_PATH = config["windows_target"]
SSH_USER = config["user"]
SSH_PASS = config["pass"]
SSH_PORT = config["port"]
SSH_IP = config["ip"]

# SSH bağlantısı için fonksiyon
def create_ssh_client():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SSH_IP, port=SSH_PORT, username=SSH_USER, password=SSH_PASS)
    return ssh

def upload_file(local_path, remote_path):
    ssh = create_ssh_client()
    sftp = ssh.open_sftp()

    def ensure_remote_dir(sftp, remote_directory):
        dirs = remote_directory.strip("/").split("/")
        path = ""
        for d in dirs:
            if not d:
                continue
            path = f"{path}/{d}"
            try:
                sftp.stat(path)
            except FileNotFoundError:
                try:
                    sftp.mkdir(path)
                    print(f"[CREATED] {path}")
                except PermissionError:
                    print(f"[NO PERMISSION] Can't create {path}, skipping...")
            except PermissionError:
                print(f"[NO PERMISSION] Can't access {path}")

    remote_dir = os.path.dirname(remote_path)
    ensure_remote_dir(sftp, remote_dir)

    sftp.put(local_path, remote_path)
    print(f"[UPLOADED] {local_path} -> {remote_path}")

    sftp.close()
    ssh.close()

# Dosya değişimlerini izleyen handler
class ChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory:
            relative_path = os.path.relpath(event.src_path, LOCAL_PATH)
            remote_path = os.path.join(REMOTE_PATH, relative_path).replace('\\', '/')
            upload_file(event.src_path, remote_path)

    def on_created(self, event):
        self.on_modified(event)

def start_watcher():
    observer = Observer()
    event_handler = ChangeHandler()
    observer.schedule(event_handler, path=LOCAL_PATH, recursive=True)
    observer.start()
    print(f"[STARTED] Watching '{LOCAL_PATH}' folder...")

    return observer

async def main():
    # StatusUpdater nesnesini oluştur
    status_updater = StatusUpdater(interval=10)

    # Dosya izleyiciyi başlat (sync)
    observer = start_watcher()

    try:
        # Status updater'ı async olarak arka planda başlat
        status_task = asyncio.create_task(status_updater.run())

        # Ana döngü: dosya izleyici sync olduğu için burada sadece bekle
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("Stopping...")

    finally:
        # Durum güncelleyiciyi durdur
        status_updater.stop()

        # Observer'ı durdur
        observer.stop()
        observer.join()

        # Status updater task'ını iptal et
        status_task.cancel()
        try:
            await status_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    asyncio.run(main())
