# open-p2p 推理冒烟测试步骤

本文记录**在没有真实游戏画面、没有 Recap** 的情况下，如何验证 open-p2p 的推理管线是通的。

环境搭建（WSL2 安装、依赖编译、权重下载）见 [install-wsl.md](install-wsl.md)。

---

## 一、这个测试验证什么

| | 验证项 |
|---|---|
| ✅ | 真 checkpoint 能加载，参数不是随机初始化 |
| ✅ | 模型前向推理能跑通，KV cache 能正常增长 |
| ✅ | 产出的 `StructuredAction` 是**真实模型输出**（见第五节判别方法） |
| ✅ | Unix socket `/tmp/uds.recap` 能建立，客户端发帧能收到动作 |
| ✅ | torch.compile / FlexAttention 融合 kernel 生效（性能达标的前提） |
| ❌ | **不验证真实游戏延迟** —— 输入是随机噪声帧 |
| ❌ | **不验证动作质量** —— 模型没看过噪声图，输出无意义 |
| ❌ | 不验证 Recap 联机、截屏、动作注入 |

---

## 二、前置条件

在 WSL 内确认（一条命令全查）：

```bash
wsl -d Ubuntu-24.04 -- bash -lc "
  cd ~/cache/open-p2p &&
  echo 'project : ' && pwd &&
  echo 'python  : ' && .venv/bin/python -V &&
  echo 'torch   : ' && .venv/bin/python -c 'import torch;print(torch.__version__, torch.cuda.is_available())' &&
  echo 'rust ext: ' && .venv/bin/python -c 'import elefant_rust;print(\"OK\")' &&
  echo 'ckpt    : ' && ls -la checkpoints/150M/ &&
  echo 'config  : ' && grep text_tokenizer_name config/policy_model/150M_local_notoken.yaml"
```

预期输出（已实测）：

```
project : /root/cache/open-p2p
python  : Python 3.13.2
torch   : 2.9.1+cu128 True
rust ext: OK
ckpt    : checkpoint-step=00500000.ckpt (2198488343 bytes)
config  : text_tokenizer_name: null
```

> ⚠️ `config/policy_model/150M_local_notoken.yaml` 是**推理专用**配置，与原 `150M.yaml` 只差一行
> （`text_tokenizer_name: "gemma"` → `null`）。原因见第六节。

---

## 三、启动方式

### 方式 A：一键脚本（推荐）

脚本在仓库里：[scripts/smoke_test.sh](scripts/smoke_test.sh)

```bash
# Windows PowerShell 里执行
wsl -d Ubuntu-24.04 -- bash /mnt/e/PycharmProjects/pixel2palyWorkspace/open-p2p/scripts/smoke_test.sh serve-bg
```

五个子命令：

| 命令 | 作用 |
|---|---|
| `serve-bg` | 后台启动服务（不占终端，推荐） |
| `status` | 查看启动进度 / socket 是否就绪 |
| `client` | 跑 30s 负载客户端 |
| `serve` | 前台启动（想直接看实时日志时用） |
| `stop` | 停止后台服务 |

### 方式 B：手动命令

```bash
# 1) 进 WSL
wsl -d Ubuntu-24.04

# 2) 进项目
cd ~/cache/open-p2p

# 3) 启动推理服务
uv run elefant/policy_model/inference.py \
  --config config/policy_model/150M_local_notoken.yaml \
  --checkpoint_path checkpoints/150M/checkpoint-step=00500000.ckpt
```

> ⚠️ **绝对不要加 `--no-compile`**。关掉编译后 FlexAttention 退化为未融合实现，
> 实测 fps 从 **35 掉到 6.4**，warmup 跑几十分钟都结束不了。
> 日志出现 `flex_attention called without torch.compile()` 就是踩了这个坑。

---

## 四、等待 socket 就绪（关键：不是卡死，是在做 1 万帧测试）

服务启动后会**先跑两轮压测再创建 socket**，整个过程约 **10～11 分钟**：

| 阶段 | 内容 | 实测耗时 | 日志表现 |
|---|---|---|---|
| ① 加载 | 读 2.2GB checkpoint | **4.9s** | `[TIMER] Stage3 model instantiation / checkpoint load: 4.93s` |
| ② 编译 | torch.compile 编译 FlexAttention kernel | **~200s** | 无输出，进程 CPU ~100% |
| ③ warmup | 跑 `n_seq_timesteps + 3` = **203 帧** | **~200s** | 逐帧打印 `Action: ...` |
| ④ FPS 测试 | 跑 **10000 帧** | **~285s** | 持续打印 `Action: ...` |
| ⑤ 建 socket | `Server started on /tmp/uds.recap` | — | 这时才能被客户端连接 |

**观察进度**（另开一个终端）：

```bash
wsl -d Ubuntu-24.04 -- bash -lc "
  echo '已产帧数: ' \$(grep -c '^Action:' ~/cache/open-p2p/inference_server.log)
  echo 'socket  : ' \$([ -S /tmp/uds.recap ] && echo READY || echo '未就绪')
  grep -E 'TIMER|Warm-up|fps =|Server started' ~/cache/open-p2p/inference_server.log | tail -8"
```

帧数走势应该是：**0 → 0 → 0（编译中）→ 203（warmup 结束）→ 10203（FPS 测试结束）**，
然后 socket 出现。

---

## 五、跑客户端 + 读结果

### 5.1 跑客户端

```bash
wsl -d Ubuntu-24.04 -- bash /mnt/e/PycharmProjects/pixel2palyWorkspace/open-p2p/scripts/smoke_test.sh client
```

或手动：

```bash
wsl -d Ubuntu-24.04 -- bash -lc "cd ~/cache/open-p2p && timeout 30 uv run elefant/inference/script/inference_load_test.py"
```

客户端每帧发一张 **192×192×3 的随机噪声图**，等模型回一个动作。

### 5.2 两个耗时数字分别是什么

日志里会看到两个不同的耗时，**别混为一谈**：

**① 服务端 `fps_test`（inference.py L616-644）** —— 纯 GPU 推理吞吐

```python
start_time_i = time.time_ns()
next_frame = torch.randint(0, 255, (3, 192, 192), ...)   # 随机帧生成也计入耗时
action = self.inference_state.get_action(next_frame)      # 真正的模型推理
time_taken_ns = time.time_ns() - start_time_i
```

输出：`Time taken: 284.85 seconds, fps = 35.106`
→ 单帧 = 284.85s ÷ 10000 帧 = **28.48 ms**

**② 客户端 `inference_load_test.py`（L59-70）** —— 端到端往返

```python
start_send_frame = time.time_ns()
writer.write(frame_data); await writer.drain()   # protobuf 序列化 + UDS 发送
action = await reader.readexactly(action_len)   # 收动作
frame_processing_times.append(time.time_ns() - start_send_frame)
```

输出：`Frame processing time: 28.58 ms (max: 29.66 ms)`

**客户端比服务端多出的几毫秒 = protobuf 编解码 + socket 传输开销。**

### 5.3 怎么判断"模型真的在工作"（而不是随机数）

输入是噪声，输出看着很乱，但**键位组合有规律**：

```
Action: StructuredAction(keys=['UpArrow', 'e', 'f', 'q'], mouse_buttons=['1'], mouse_delta_x=2,   mouse_delta_y=151)
Action: StructuredAction(keys=['LeftShift', 'q', 'z'],  mouse_buttons=[],    mouse_delta_x=-68, mouse_delta_y=-19)
Action: StructuredAction(keys=['Space', 'a', 'q', 'w'], mouse_buttons=['2'], mouse_delta_x=-6,  mouse_delta_y=-4)
```

`w/a/s/d` + `q/z/f/e` + 数字键 + `Space` + `UpArrow/DownArrow` —— 这正是 **Minecraft 的移动与操作键位**。
模型在"看白噪声"时输出训练分布里最高频的键组合，说明：

- checkpoint 权重确实加载了（不是随机初始化）
- 前向计算确实执行了（不是恒定输出）
- 动作解码器（`action_mapping.py`）工作正常

### 5.4 停止服务

```bash
wsl -d Ubuntu-24.04 -- bash /mnt/e/PycharmProjects/pixel2palyWorkspace/open-p2p/scripts/smoke_test.sh stop
```

或直接 `Ctrl+C`（前台模式）。

---

## 六、踩过的坑

### 6.1 `text_tokenizer_name` 不能用 `"gemma"`

原始 config 里写的是 `"gemma"`，会尝试下载 **`google/embeddinggemma-300M` —— 这是 HF 的 gated repo**，
未登录时直接报错：

```
OSError: You are trying to access a gated repo.
401 Client Error ... Cannot access gated repo for url
https://huggingface.co/google/embeddinggemma-300M/resolve/main/config.json
```

**解决**：推理用 `config/policy_model/150M_local_notoken.yaml`，里面是 `text_tokenizer_name: null`。

置 `null` 后 `text_tokenizer_model = None`，走 [inference.py L248-258](elefant/policy_model/inference.py#L248-L258)
那条分支（注释原文：*"the policy transformer will not take any text embedding so the input will be ignored"*），
传入全零 text embedding，再由 `policy_transformer._impute_no_text_embedding()` 替换成模型内可学习的
`text_embedding_for_no_text_input` 参数（checkpoint 里已训练好）。

**与"用 gemma 但不传文本"完全等价** —— 那条分支同样产生全零 embedding。

> 若要启用**文本指令**功能，必须去
> https://huggingface.co/google/embeddinggemma-300M 申请访问权限，
> 并执行 `uv run huggingface-cli login`（新版为 `hf auth login`），
> 此时改用原始 `config/policy_model/150M.yaml` 并加 `--input_text`。

### 6.2 `text_tokenizer_name` 也不能用 `"dummy"`

`DummyTextTokenizer` 的 `embed_dim` 硬编码成 **2048**，与模型期望的 **768** 不符，会崩：

```
AssertionError: Eager assert failed: torch.Size([1, 2048]) != (1, 768)
```

正确做法是 `null`，不是 `dummy`。

### 6.3 不要用 `--no-compile`

见第三节。关掉编译 → FlexAttention 未融合 → 全量 scores 矩阵 → fps 从 35 掉到 6.4。

### 6.4 socket 迟迟不出现 ≠ 卡死

服务要跑完 203 帧 warmup **和** 10000 帧 FPS 测试才建 socket，一共约 10～11 分钟。
期间用第四节的方法看帧数是否在涨。

---

## 七、实测记录（RTX 4060 Laptop / WSL2 Ubuntu 24.04 / torch 2.9.1+cu128）

连续两次独立运行（`serve-bg` 重启服务）结果一致：

| 指标 | 第 1 次 | 第 2 次 |
|---|---|---|
| checkpoint 加载 | 4.57 s | 4.93 s |
| torch.compile + warmup 203 帧 | 361.83 s（fps 0.53） | 408.09 s（fps 0.46） |
| FPS 测试 10000 帧 | 284.85 s → **fps 35.106** | 284.64 s → **fps 35.132** |
| 单帧纯推理耗时 | **28.48 ms** | **28.46 ms** |
| 客户端往返耗时 | 28.58 ~ 33.27 ms | 27.59 ~ 37.02 ms（稳态 ~29~33） |
| 客户端整体 FPS | ~12.9 | ~12.6 |
| socket 就绪总耗时 | **641 s** | ~745 s（含编译波动） |

**关于客户端 FPS 只有 ~12.6**：瓶颈在客户端自己 —— 每帧要生成 192×192×3 随机像素、
protobuf 序列化、经 UDS 发送，再解析返回的 action，纯 Python 开销就占了 ~20ms。
服务端推理本身是 35 fps。真实链路的瓶颈会在**截屏和传输**，不在模型。

**关于第一帧 2050 ms**：CUDA 上下文初始化 + 首次 kernel 预热，属正常现象，
第二帧就回到 ~29 ms。

> README 里 `< 50ms` 的端到端指标是在 **RTX 5090** 上测的；本机 4060 Laptop 的纯推理
> 28.5ms 已接近该量级，真实链路还要叠加截屏、缩放、传输、动作注入的开销。

---

## 八、完整时序一览（一次成功运行）

```
$ bash scripts/smoke_test.sh serve-bg
启动时间: 19:12:15
pid=354

$ bash scripts/smoke_test.sh status          # 反复观察
服务 pid : 354
已跑时长 : 01:19
已产帧数: 0                                  # ← 正在 torch.compile
socket   : ⏳ 未就绪

服务 pid : 354
已跑时长 : 07:42
已产帧数: 1552                                # ← FPS 测试进行中
socket   : ⏳ 未就绪

服务 pid : 354
已跑时长 : 12:24
已产帧数: 10203                               # ← 10000 帧跑完
socket   : ✅ 已就绪 (/tmp/uds.recap)
--- 关键日志 ---
Time taken: 284.6380853652954 seconds, fps = 35.132333001630194
INFO:root:[TIMER] FPS test: 264.06s
INFO:root:Server started on /tmp/uds.recap

$ bash scripts/smoke_test.sh client
=== 负载客户端 30s ===
INFO:root:Received action for frame 322/323: ['s']. Current FPS: 12.56. Frame processing time: 29.05 ms (max: 30.44 ms)
...
```
