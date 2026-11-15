import os, sys, traceback
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

print("=== 1) gemma gated repo 可访问性 ===")
try:
    from huggingface_hub import HfApi
    api = HfApi()
    info = api.model_info("google/embeddinggemma-300M")
    print("gated:", info.gated, "| files:", len(info.siblings or []))
except Exception as e:
    print("model_info failed:", type(e).__name__, str(e)[:200])

print()
print("=== 2) toy dataset 里的 instruction 文本 ===")
try:
    from datasets import load_dataset
    ds = load_dataset("elefantai/p2p-toy-examples", split="train")
    print("rows:", len(ds))
    print("columns:", ds.column_names)
    row = ds[0]
    for k, v in row.items():
        s = str(v)
        print(f"--- {k} ({type(v).__name__}) ---")
        print(s[:800])
except Exception as e:
    print("dataset failed:", type(e).__name__, str(e)[:300])
    traceback.print_exc()
