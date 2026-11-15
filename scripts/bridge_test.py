#!/usr/bin/env python3
"""
Recap ↔ open-p2p 推理服务的 WSL 桥接诊断脚本（Windows 侧运行，无需任何第三方依赖）。

复刻 Recap 内部 crates/wsl-tools/src/lib.rs 的做法：
    wsl socat -b 200000 STDIO UNIX-CONNECT:/tmp/uds.recap,sndbuf=65536,rcvbuf=131072
并用最小手写 protobuf 编解码验证 4 字节长度前缀的帧协议。

用法：
    python bridge_test.py                # 默认 10 帧
    python bridge_test.py 30             # 测 30 帧并统计延迟
"""

import struct
import subprocess
import sys
import time

UDS_PATH = "/tmp/uds.recap"


# ---------- 手写 protobuf（只实现需要的部分） ----------
def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def field_int(num: int, value: int) -> bytes:
    return bytes([num << 3 | 0]) + varint(value)


def field_bytes(num: int, value: bytes) -> bytes:
    return bytes([num << 3 | 2]) + varint(len(value)) + value


def encode_frame(width: int, height: int, data: bytes, frame_id: int) -> bytes:
    # Frame { int32 width=1; int32 height=2; bytes data=3; int32 id=4; }
    return (
        field_int(1, width)
        + field_int(2, height)
        + field_bytes(3, data)
        + field_int(4, frame_id)
    )


def decode_action(buf: bytes) -> dict:
    """解析 Action { repeated string keys=1; int32 id=2; MouseAction mouse_action=3; }"""
    result = {"keys": [], "id": None, "mouse_delta": None, "buttons": []}
    i = 0
    while i < len(buf):
        key, i = read_varint(buf, i)
        fno, ftype = key >> 3, key & 7
        if ftype == 2:
            ln, i = read_varint(buf, i)
            payload = buf[i : i + ln]
            i += ln
            if fno == 1:
                result["keys"].append(payload.decode("utf-8", "replace"))
            elif fno == 3:
                parse_mouse(payload, result)
        elif ftype == 0:
            val, i = read_varint(buf, i)
            if fno == 2:
                result["id"] = val
        elif ftype == 5:
            i += 4
        elif ftype == 1:
            i += 8
        else:
            break
    return result


def parse_mouse(buf: bytes, result: dict) -> None:
    """MouseAction { oneof mouse_change { Vec2Int mouse_delta_px=1; Vec2Float mouse_pos=2; }
                     Vec2Int scroll_delta_px=3; repeated string buttons_down=4; }"""
    i = 0
    while i < len(buf):
        key, i = read_varint(buf, i)
        fno, ftype = key >> 3, key & 7
        if ftype == 2:
            ln, i = read_varint(buf, i)
            payload = buf[i : i + ln]
            i += ln
            if fno == 1:  # Vec2Int mouse_delta_px
                x, y = read_sint_pair(payload)
                result["mouse_delta"] = (x, y)
            elif fno == 4:  # buttons_down
                result["buttons"].append(payload.decode("utf-8", "replace"))
        elif ftype == 0:
            _, i = read_varint(buf, i)
        elif ftype == 5:
            i += 4
        elif ftype == 1:
            i += 8
        else:
            break


def read_varint(buf: bytes, i: int):
    shift = 0
    val = 0
    while True:
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7


def read_sint_pair(buf: bytes):
    """Vec2Int { int32 x=1; int32 y=2; }"""
    x = y = 0
    i = 0
    while i < len(buf):
        key, i = read_varint(buf, i)
        fno, ftype = key >> 3, key & 7
        if ftype == 0:
            v, i = read_varint(buf, i)
            if fno == 1:
                x = v
            elif fno == 2:
                y = v
        else:
            break
    return x, y


def read_exactly(f, n):
    buf = b""
    while len(buf) < n:
        chunk = f.read(n - len(buf))
        if not chunk:
            raise EOFError(f"连接提前关闭，只收到 {len(buf)}/{n} 字节")
        buf += chunk
    return buf


# ---------- 主流程 ----------
def main() -> int:
    n_frames = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    # Windows 控制台默认 GBK，强制 UTF-8 输出避免 UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print(f"[*] 启动桥接: wsl socat STDIO UNIX-CONNECT:{UDS_PATH}")
    proc = subprocess.Popen(
        [
            "wsl.exe",
            "socat",
            "-b",
            "200000",
            "STDIO",
            f"UNIX-CONNECT:{UDS_PATH},sndbuf=65536,rcvbuf=131072",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

    # 等待 socat 起来（可能已经因连接失败退出）
    time.sleep(1.5)
    if proc.poll() is not None:
        err = proc.stderr.read().decode("utf-8", "replace")
        print(f"[FAIL] 桥接进程立即退出 (code={proc.returncode})")
        print(f"    stderr: {err.strip()}")
        if "No such file" in err:
            print("    -> 推理服务还没起来，WSL 里检查: ls -la /tmp/uds.recap")
        elif "Connection refused" in err:
            print("    -> socket 存在但没人监听，检查推理服务是否已启动完成")
        return 1

    print("[OK] 桥接已建立，开始发送帧")
    latencies = []
    try:
        for i in range(n_frames):
            frame = encode_frame(192, 192, bytes(192 * 192 * 3), i + 1)
            t0 = time.perf_counter()
            proc.stdin.write(struct.pack("<I", len(frame)) + frame)
            proc.stdin.flush()

            n = struct.unpack("<I", read_exactly(proc.stdout, 4))[0]
            payload = read_exactly(proc.stdout, n)
            dt = (time.perf_counter() - t0) * 1000
            latencies.append(dt)

            act = decode_action(payload)
            print(
                f"[{i+1:3d}] {dt:7.2f} ms  keys={act['keys']} "
                f"mouse_delta={act['mouse_delta']} buttons={act['buttons']}"
            )
    except EOFError as e:
        print(f"[FAIL] {e}")
        err = proc.stderr.read().decode("utf-8", "replace")
        if err.strip():
            print(f"    socat stderr: {err.strip()}")
        return 1
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.terminate()

    if latencies:
        avg = sum(latencies) / len(latencies)
        worst = max(latencies)
        best = min(latencies)
        print()
        print(f"=== 统计 ({len(latencies)} 帧) ===")
        print(f"  平均 : {avg:.2f} ms")
        print(f"  最快 : {best:.2f} ms")
        print(f"  最慢 : {worst:.2f} ms")
        print(f"  FPS  : {1000.0 / avg:.2f}")
    print("\n[OK] 桥接 + 协议 + 推理服务 全链路 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
