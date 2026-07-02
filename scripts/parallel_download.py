"""
多线程分块下载脚本。

用法: python parallel_download.py <URL> <输出路径> [线程数]
"""
import sys
import os
import time
import ssl
import socket
import threading
import http.client
import urllib.request

# 需要固定解析的域名
DNS_MAP = {
    "zenodo.org": "188.184.98.114",
}


class ForcedIPHTTPConnection(http.client.HTTPConnection):
    """按 DNS_MAP 指定的地址建立 HTTP 连接。"""

    def connect(self):
        host = self.host
        ip = DNS_MAP.get(host, host)
        self.sock = socket.create_connection((ip, self.port), self.timeout)


class ForcedIPHTTPSConnection(http.client.HTTPSConnection):
    """按 DNS_MAP 指定的地址建立 HTTPS 连接。"""

    def connect(self):
        host = self.host
        ip = DNS_MAP.get(host, host)
        self.sock = socket.create_connection((ip, self.port), self.timeout)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        self.sock = ssl_context.wrap_socket(self.sock, server_hostname=host)


class ForcedIPHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(ForcedIPHTTPSConnection, req)


def get_file_size(url):
    req = urllib.request.Request(url, method="HEAD")
    req.add_header("User-Agent", "Mozilla/5.0")
    opener = urllib.request.build_opener(ForcedIPHandler())
    with opener.open(req, timeout=30) as resp:
        accept_ranges = resp.headers.get("Accept-Ranges", "none")
        size = int(resp.headers.get("Content-Length", 0))
        return size, accept_ranges == "bytes"


class ChunkDownloader(threading.Thread):
    def __init__(self, url, out_path, start, end, chunk_id, progress_by_chunk):
        super().__init__(daemon=True)
        self.url = url
        self.out_path = out_path
        self.start = start
        self.end = end
        self.chunk_id = chunk_id
        self.progress = progress_by_chunk
        self.downloaded = 0
        self.done = False

    def run(self):
        retries = 3
        for attempt in range(retries):
            try:
                req = urllib.request.Request(self.url)
                req.add_header("User-Agent", "Mozilla/5.0")
                req.add_header("Range", f"bytes={self.start}-{self.end - 1}")

                opener = urllib.request.build_opener(ForcedIPHandler())
                with opener.open(req, timeout=120) as resp:
                    with open(self.out_path, "r+b") as f:
                        f.seek(self.start)
                        while True:
                            chunk = resp.read(256 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)
                            self.downloaded += len(chunk)
                            self.progress[self.chunk_id] = self.downloaded
                self.done = True
                return
            except Exception as exc:
                if attempt < retries - 1:
                    time.sleep(2)
                else:
                    print(f"\n[分块 {self.chunk_id}] 失败: {exc}")


def main():
    if len(sys.argv) < 3:
        print("用法: python parallel_download.py <URL> <输出路径> [线程数]")
        sys.exit(1)

    url = sys.argv[1]
    out_path = sys.argv[2]
    num_threads = int(sys.argv[3]) if len(sys.argv) > 3 else 8

    print("正在获取文件大小...")
    file_size, supports_range = get_file_size(url)
    print(f"文件大小: {file_size / (1024**3):.2f} GB")
    print(f"支持 Range: {supports_range}")

    if not supports_range or file_size == 0:
        print("不支持分块下载，使用单线程")
        num_threads = 1
        chunk_size = file_size
    else:
        chunk_size = file_size // num_threads

    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    if not os.path.exists(out_path):
        with open(out_path, "wb") as f:
            f.truncate(file_size)

    progress = {}
    threads = []
    for i in range(num_threads):
        start = i * chunk_size
        end = file_size if i == num_threads - 1 else (i + 1) * chunk_size
        worker = ChunkDownloader(url, out_path, start, end, i, progress)
        threads.append(worker)
        progress[i] = 0

    print(f"启动 {num_threads} 个线程下载...")
    for worker in threads:
        worker.start()

    start_time = time.time()
    try:
        while True:
            time.sleep(3)
            downloaded_bytes = sum(progress.values())
            elapsed = max(time.time() - start_time, 0.1)
            speed = downloaded_bytes / elapsed
            pct = (downloaded_bytes / file_size * 100) if file_size > 0 else 0
            eta = (file_size - downloaded_bytes) / speed if speed > 0 else 0

            print(f"\r进度: {pct:.1f}% | "
                  f"{downloaded_bytes/(1024**2):.0f}/{file_size/(1024**2):.0f} MB | "
                  f"速度: {speed/(1024**2):.2f} MB/s | "
                  f"剩余: {eta/60:.0f}分  ",
                  end="", flush=True)

            if all(worker.done for worker in threads):
                break
    except KeyboardInterrupt:
        print("\n中断，进度已保留 (重跑可续传)")

    downloaded_bytes = sum(progress.values())
    elapsed = time.time() - start_time
    if downloaded_bytes >= file_size:
        print(f"\n完成，耗时 {elapsed/60:.1f}分")
    else:
        print(f"\n未完全下载 ({downloaded_bytes/(1024**2):.0f}/{file_size/(1024**2):.0f} MB)")


if __name__ == "__main__":
    main()
