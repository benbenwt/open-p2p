# WSL2 环境安装指南（Windows 用户的推荐路径）

> 适用场景：Windows 上做**训练 / 离线推理 / 在线推理服务端**，Windows 侧保留 Recap 做实时联机。
> 原因：`elefant_rust`（Rust 扩展）依赖 `ffmpeg-sys-next` + `zmq-sys`，在 Windows 原生编译需要
> vcpkg + CMake + NASM + FFmpeg 开发库；且 `torchcodec`（视频解码，训练数据预处理必需）只在
> `sys_platform == 'linux'` 下安装，Windows 原生跑不了完整训练链路。

本文所有命令均已在 **Windows 11 25H2 + WSL 2.4.13 + Ubuntu 24.04.5** 上实测通过。

---

## 0. 前置：启用 WSL2 所需系统功能（管理员 PowerShell，一次性）

本机初始状态：`vmcompute.exe` 不存在，WSL 启动报 `HCS_E_SERVICE_NOT_AVAILABLE`。

```powershell
# 管理员 PowerShell
dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

**执行完必须重启**，然后验证：

```powershell
Test-Path C:\Windows\System32\vmcompute.exe   # 应为 True
wsl --status
wsl -l -v
```

安装发行版（如果列表里没有 24.04）：

```powershell
wsl --install -d Ubuntu-24.04
wsl --set-default Ubuntu-24.04
```

> ⚠️ `wsl --set-default Ubuntu-24.04wsl -l -v` 这类**两条命令连在一起**会报
> `WSL_E_DISTRO_NOT_FOUND`（发行版名被解析成 `Ubuntu-24.04wsl`），必须分行执行。

### 若发行版启动报 `MountVhd/HCS/ERROR_FILE_NOT_FOUND`

说明该发行版的 `ext4.vhdx` 丢失（注册信息还在但磁盘镜像没了）：

```powershell
wsl --unregister Ubuntu      # 清理空壳（确认 LocalState 目录为空再删）
wsl --install -d Ubuntu-24.04
```

---

## 1. `.wslconfig`：内存 + **mirrored 网络**

编辑 `C:\Users\<你的用户名>\.wslconfig`：

```ini
[wsl2]
memory=12GB
processors=12
swap=8GB
# 让 WSL 与 Windows 共用网络栈
networkingMode=mirrored
# 自动继承 Windows 的系统代理
autoProxy=true
dnsTunneling=true
```

> **为什么必须 mirrored**：Windows 上的代理（Clash 等）默认只监听 `127.0.0.1`，
> WSL 默认的 NAT 模式下**访问不到**宿主机 localhost 代理，git 拉大仓库会频繁
> `Connection reset by peer`。改成 `mirrored` 后，WSL 内的 `127.0.0.1:20624`
> 就是 Windows 的 `127.0.0.1:20624`，可直接用 env 变量配代理。

生效方式（会中断正在运行的 WSL 进程）：

```powershell
wsl --shutdown
```

---

## 2. 进入 Ubuntu，安装系统依赖

### 2.1 换国内 apt 镜像（重要，官方源可能慢到超时）

```bash
sudo cp /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources.bak
sudo tee /etc/apt/sources.list.d/ubuntu.sources >/dev/null <<'EOF'
Types: deb
URIs: http://mirrors.aliyun.com/ubuntu/
Suites: noble noble-updates noble-backports
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: http://mirrors.aliyun.com/ubuntu/
Suites: noble-security
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
sudo apt-get update
```

### 2.2 基础构建依赖

```bash
sudo apt-get install -y --no-install-recommends \
  software-properties-common git curl ca-certificates build-essential cmake pkg-config \
  clang libclang-dev libsodium-dev libsasl2-dev libssl-dev zlib1g-dev libnss3-dev socat
```

### 2.3 FFmpeg 必须是 7.x

`elefant_rust` 锁定 `ffmpeg-next`（rev `c3876e09`）→ `ffmpeg-sys-next 7.1.3`，**只认 FFmpeg 7.1**。
Ubuntu 24.04 自带 6.1，必须换 PPA：

```bash
sudo add-apt-repository -y ppa:ubuntuhandbook1/ffmpeg7
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  ffmpeg libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
  libavdevice-dev libavfilter-dev
```

自检：

```bash
ffmpeg -version | head -1            # ffmpeg version 7.x
pkg-config --modversion libavutil    # 61.x  → 对应 FFmpeg 7.1
pkg-config --modversion libsodium
```

> 注意：Ubuntu 24.04 **没有 `libavresample-dev`** 这个包（ffmpeg 5+ 已把 libavresample 并入
> avutil），装了会报 `Unable to locate package libavresample-dev`。

---

## 3. 安装 Rust 与 uv

### 3.1 Rust（官方域名被 DNS 拦截，走清华镜像）

```bash
export RUSTUP_DIST_SERVER="https://mirrors.tuna.tsinghua.edu.cn/rustup"
export RUSTUP_UPDATE_ROOT="https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup"
curl --proto '=https' --tlsv1.2 -sSfL \
  https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup/dist/x86_64-unknown-linux-gnu/rustup-init \
  -o /tmp/rustup-init
chmod +x /tmp/rustup-init
/tmp/rustup-init -y --profile minimal --default-toolchain stable
export PATH="$HOME/.cargo/bin:$PATH"
rustc --version        # 需要 >= 1.85（elefant_rust 用 edition 2024）
```

### 3.2 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

### 3.3 配置代理（env 变量 + git 全局配置，双保险）

> WSL 默认是 NAT 模式，**访问不到 Windows 上的 `127.0.0.1` 代理**，必须先完成第 1 步的
> `networkingMode=mirrored` 并 `wsl --shutdown` 重启，否则下面所有代理配置都无效
> （WSL 会提示「检测到 localhost 代理配置但未镜像到 WSL」）。

**① 写进 `~/.bashrc` 持久化**（每次开 shell 自动生效）：

```bash
cat >> ~/.bashrc <<'EOF'
export http_proxy="http://127.0.0.1:20624"
export https_proxy="http://127.0.0.1:20624"
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
export no_proxy="localhost,127.0.0.1,::1"
export NO_PROXY="$no_proxy"
EOF
```

**② 再配一份 git 全局代理**（`env` 不覆盖的场景，比如某些脚本会清空环境变量）：

```bash
git config --global http.proxy  http://127.0.0.1:20624
git config --global https.proxy http://127.0.0.1:20624
```

**③ 验证**：

```bash
git ls-remote https://github.com/huggingface/transformers HEAD | head -1
# 实测：136 MB 浅克隆耗时 18 s（≈7.5 MB/s）
```

**方案 B（备选）：URL 重写到可用镜像（完全不依赖代理）**

```bash
git config --global url."https://ghfast.top/https://github.com/".insteadOf "https://github.com/"
```

> 代理可用时**不需要**方案 B；两者同时存在时 `insteadOf` 会优先命中、绕过代理。
> 实测：本机可用的 GitHub 镜像只有 `ghfast.top`；`ghproxy.net` / `gitclone.com` /
> `github.moeyy.xyz` / `hub.gitmirror.com` 均不可达。

再配合抗中断参数：

```bash
git config --global http.postBuffer 1048576000
git config --global http.lowSpeedLimit 0
git config --global http.lowSpeedTime 999999
git config --global core.compression 0
git config --global http.maxRequests 1
git config --global fetch.parallel 1
git config --global http.version HTTP/1.1
```

---

## 4. 拿到项目代码（**放在 WSL 的 Linux 文件系统里**）

> ⚠️ 不要在 `/mnt/e/...` 下执行 `uv sync` / 编译：跨文件系统 IO 会让构建慢 10 倍以上。

```bash
mkdir -p ~/cache/open-p2p
cd /mnt/e/PycharmProjects/pixel2palyWorkspace/open-p2p
tar -cf - --exclude=./.venv --exclude=./dataset --exclude=./target \
    --exclude=./elefant_rust/target --exclude='*.ckpt' . | (cd ~/cache/open-p2p && tar -xf -)
cd ~/cache/open-p2p
```

### 关于 `uv.lock` 与 `platform_machine`

`pyproject.toml` 的 `[tool.uv] environments` 已调整为：

```toml
environments = [
    "sys_platform == 'linux' and platform_machine == 'x86_64'",
    "sys_platform == 'win32'",     # 不限定 platform_machine：uv 在 Windows 上解析为 AMD64
    "sys_platform == 'darwin'",
]
```

在 WSL 内 `platform_machine == 'x86_64'`，与原 lock 一致；这条修改只是为了让 Windows 侧
的 `uv` 不再报 "current Python platform is not compatible"。

---

## 5. 安装项目依赖（会编译 Rust 扩展）

```bash
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
export CARGO_NET_GIT_FETCH_WITH_CLI=true
cd ~/cache/open-p2p
uv sync
```

首次会拉 torch cu128（~859MB）+ nvidia-* 系列（~2GB）并编译 `elefant_rust`（pyo3 + ffmpeg + zmq），
耗时较长（实测 20 分钟以上）。

---

## 6. 下载权重与数据

```bash
uv run python scripts/download_checkpoints.py 150M
uv run python scripts/download_data.py --toy
uv run python scripts/download_data.py --start 1 --end 100   # 全量分批
```

---

## 7. 启动推理服务（WSL 内）

> 📖 完整的验证步骤（含等待 socket、跑客户端、结果解读）见 **[smoke-test.md](smoke-test.md)**，
> 一键脚本：`scripts/smoke_test.sh {serve-bg|status|client|stop}`。

### 7.1 无文本推理（论文主设置，推荐）

```bash
uv run elefant/policy_model/inference.py \
  --config config/policy_model/150M_local_notoken.yaml \
  --checkpoint_path checkpoints/150M/checkpoint-step=00500000.ckpt
```

> ⚠️ **不要加 `--no-compile`**。关掉 compile 后 FlexAttention 会退化成未融合实现
> （materializes the full scores matrix），实测 fps 从正常的几十降到 **6.4**，warmup 几百秒都跑不完。
> 日志里出现 `flex_attention called without torch.compile()` 就说明踩了这个坑。

### 7.2 为什么用 `150M_local_notoken.yaml`

`config/policy_model/150M.yaml` 里 `text_tokenizer_name: "gemma"` 会去拉
**`google/embeddinggemma-300M`，这是 HF 的 gated repo**，未登录时会报：

```
OSError: You are trying to access a gated repo.
401 Client Error ... google/embeddinggemma-300M
```

本仓库已提供 `config/policy_model/150M_local_notoken.yaml`（只比原文件差一行）：

```yaml
text_tokenizer_name: null      # 原为 "gemma"
text_embedding_shape: [1, 768]  # 不变
```

置为 `null` 后 `text_tokenizer_model = None`，走 `inference.py` 里
「the policy transformer will not take any text embedding so the input will be ignored」
那条分支，传入全零 text embedding，再由 `policy_transformer._impute_no_text_embedding()`
替换成模型内可学习的 `text_embedding_for_no_text_input` 参数（checkpoint 里已训练好）。

**与用 gemma 但不传文本（`text=None`）完全等价**，因为那条分支同样产生全零 embedding。

> 若要使用**文本指令**功能，则必须去 https://huggingface.co/google/embeddinggemma-300M
> 申请访问权限，并 `uv run huggingface-cli login`（新版为 `hf auth login`），
> 此时用原始的 `config/policy_model/150M.yaml` 并加 `--input_text`。

### 7.3 启动耗时与 socket

服务启动时会先跑 **warmup 203 帧 + FPS 测试 10000 帧**，**期间 Unix socket 尚未创建**，
需要等 socket 出现（`/tmp/uds.recap`）才能被 Windows 侧 Recap 发现。

```bash
# 另开一个终端观察进度
watch -n 5 'grep -c "^Action:" /path/to/tmp_smoke_server.log'
```

带文本指令时加 `--input_text`（**必须在启动时指定，运行期不可切换**）。

服务监听 Unix socket `/tmp/uds.recap`，由 Windows 侧 Recap 自动发现。

GPU 检查：`nvidia-smi` 在 WSL 内需 Windows 侧 NVIDIA 驱动 ≥ 525。

---

## 8. Windows 侧（Recap 实时联机）

1. 安装 Recap：https://github.com/elefant-ai/recap
2. 在 Recap 仓库目录执行 `just trace`
3. 填写元信息 → 选择要捕获的游戏窗口（如 Roblox）
4. 快捷键：
   | 操作 | 按键 |
   |------|------|
   | 开始推理控制 | `Shift` + `]` |
   | 打断模型控制 | 移动鼠标或按键 |
   | 恢复模型控制 | `[` |
   | 结束会话 | `Shift` + `]` |

---

## 9. Windows 原生也能做的事（不装 WSL 也能跑）

纯 Python 下载脚本无需编译 Rust 扩展，用 `--no-project` 绕过整个环境同步：

```powershell
uv run --no-project --python 3.13 --with huggingface_hub python scripts/download_data.py --toy
```

已验证可用（toy 数据集约 1 GB，落在 `./dataset`）。

---

## 10. 故障速查

| 现象 | 原因 | 处理 |
|---|---|---|
| `HCS_E_SERVICE_NOT_AVAILABLE` | VirtualMachinePlatform 未启用 | 第 0 步 `dism` + 重启 |
| `MountVhd/HCS/ERROR_FILE_NOT_FOUND` | 发行版 `ext4.vhdx` 丢失 | `wsl --unregister` 后重装 |
| `WSL_E_DISTRO_NOT_FOUND` | 两条 wsl 命令连在一起 | 分行执行 |
| `Could not resolve host: sh.rustup.rs` | 官方域名被 DNS 拦 | 用清华镜像装 rustup（第 3.1 步） |
| `Unable to locate package libavresample-dev` | Ubuntu 24.04 无此包 | 去掉该包 |
| git `Connection reset by peer` / `invalid index-pack output` | GitHub 直连被重置 | 第 3.3 步方案 A（代理）或方案 B（镜像） |
| `ffmpeg-sys-next` 找不到 `libavutil` | ffmpeg 版本不对 | 确认 `pkg-config --modversion libavutil` 为 61.x |
| `torchcodec` 装不上 | 该包仅 linux | 只能在 Linux/WSL 装 |
| `OSError: You are trying to access a gated repo` | `google/embeddinggemma-300M` 是 gated repo | 改用 `config/policy_model/150M_local_notoken.yaml`（第 7.2 节），或申请权限后 `hf auth login` |
| `Eager assert failed: torch.Size([1, 2048]) != (1, 768)` | 用 `dummy` tokenizer 冒充 gemma（dummy 写死 2048 维） | 不要用 `text_tokenizer_name: "dummy"`，改用 `null` |
| `flex_attention called without torch.compile()` | 误加了 `--no-compile` | 去掉该参数（第 7.1 节） |
| socket `/tmp/uds.recap` 迟迟不出现 | 服务还在跑 warmup 203 帧 + FPS 测试 10000 帧 | 属正常，等 `grep -c '^Action:' server.log` 计数上涨 |
| WSL 里 curl 提示「localhost 代理未镜像到 WSL」 | `networkingMode` 还是 nat | 第 1 步改 `mirrored` 并 `wsl --shutdown` |