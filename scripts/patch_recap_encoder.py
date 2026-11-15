#!/usr/bin/env python3
"""
为 recap-main 打补丁：GStreamer 官方 Windows 安装包不含 x264enc（属 gst-plugins-ugly，
专利原因官方改用 openh264），导致 recap_gst::record_window 里硬编码的 Encoder::RngX264
构建失败 -> pipeline 构建失败 -> 无帧 -> 推理链路断开。

改动：
  1. Encoder 枚举新增 OpenH264 变体
  2. Encoder::instance() 增加 openh264enc 分支（属性按 openh264enc 的实际语义映射）
  3. 运行时探测 x264enc 是否存在，缺失时回退到 openh264enc
  4. openh264 只支持 4:2:0，caps 里不能再协商 high-4:4:4 profile

用法: python patch_recap_encoder.py <recap-main 目录>
"""

import sys
from pathlib import Path

TARGET = Path(sys.argv[1]) / "crates" / "recap_gst" / "src" / "record_window.rs"

OLD_ENUM = """enum Encoder {
    AmfH264,
    X264,
    RngX264,
}
"""

NEW_ENUM = """enum Encoder {
    AmfH264,
    X264,
    RngX264,
    /// `x264enc` lives in gst-plugins-ugly, which the official GStreamer Windows
    /// installers no longer ship. `openh264enc` ships with the runtime package, so
    /// use it as a fallback when x264 is unavailable.
    OpenH264,
}
"""

OLD_INSTANCE = """            Encoder::RngX264 => {
                let rng = rand::rng().random_range(14u32..=18);
                gst::ElementFactory::make("x264enc")
                    .property("quantizer", rng)
                    .property_from_str("pass", "qual")
                    .property("bitrate", 4096_u32)
                    .property_from_str("psy-tune", "film")
            }
        }
    }
"""

NEW_INSTANCE = """            Encoder::RngX264 => {
                let rng = rand::rng().random_range(14u32..=18);
                gst::ElementFactory::make("x264enc")
                    .property("quantizer", rng)
                    .property_from_str("pass", "qual")
                    .property("bitrate", 4096_u32)
                    .property_from_str("psy-tune", "film")
            }
            // openh264enc takes its quality bounds as qp-min/qp-max and expects the
            // bitrate in bits per second (x264enc uses kbit/s).
            Encoder::OpenH264 => {
                let rng = rand::rng().random_range(14u32..=18);
                gst::ElementFactory::make("openh264enc")
                    .property("qp-min", rng)
                    .property("qp-max", rng + 4)
                    .property("bitrate", 4096_u32 * 1000)
                    .property_from_str("rate-control", "quality")
            }
        }
    }

    /// openh264 only encodes 4:2:0, so it cannot negotiate a high-4:4:4 profile.
    fn supports_444_profile(self) -> bool {
        !matches!(self, Encoder::OpenH264)
    }
"""

OLD_SELECT = """        let encoder = Encoder::RngX264;
        tracing::info!(module = "capture::encoder", "Encoder: {:?}", encoder);

        let encoder = encoder.build()?;

        let encoder_caps = gst_video::VideoCapsBuilder::for_encoding("video/x-h264")
            // 10% chance of high-4:4:4 profile this will mean almost 100% color fidelity
            .field_if("profile", "high-4:4:4", rand::rng().random_bool(0.1))
            .build();
"""

NEW_SELECT = """        // x264enc is only available when gst-plugins-ugly is installed, which the
        // official GStreamer Windows installers skip. Fall back to openh264enc so
        // the capture pipeline can still be built.
        let encoder_kind = if gst::ElementFactory::find("x264enc").is_some() {
            Encoder::RngX264
        } else {
            tracing::warn!(
                module = "capture::encoder",
                "x264enc is not available, falling back to openh264enc"
            );
            Encoder::OpenH264
        };
        tracing::info!(module = "capture::encoder", "Encoder: {:?}", encoder_kind);

        let encoder = encoder_kind.build()?;

        let encoder_caps = gst_video::VideoCapsBuilder::for_encoding("video/x-h264")
            // 10% chance of high-4:4:4 profile this will mean almost 100% color fidelity
            .field_if(
                "profile",
                "high-4:4:4",
                encoder_kind.supports_444_profile() && rand::rng().random_bool(0.1),
            )
            .build();
"""

REPLACEMENTS = [
    ("enum Encoder {\n    AmfH264,\n    X264,\n    RngX264,\n}\n", NEW_ENUM),
    (
        """            Encoder::RngX264 => {
                let rng = rand::rng().random_range(14u32..=18);
                gst::ElementFactory::make("x264enc")
                    .property("quantizer", rng)
                    .property_from_str("pass", "qual")
                    .property("bitrate", 4096_u32)
                    .property_from_str("psy-tune", "film")
            }
        }
    }
""",
        NEW_INSTANCE,
    ),
    (OLD_SELECT, NEW_SELECT),
]


def main() -> int:
    if not TARGET.exists():
        print(f"[FAIL] 找不到 {TARGET}")
        return 1

    text = TARGET.read_text(encoding="utf-8")
    original = text

    for old, new in REPLACEMENTS:
        if new in text and old not in text:
            print(f"[skip] 该段已打过补丁: {old.strip().splitlines()[0][:50]}")
            continue
        if old not in text:
            print(f"[FAIL] 未找到待替换片段:\n{old[:200]}")
            return 1
        text = text.replace(old, new, 1)
        print(f"[ok] 替换: {old.strip().splitlines()[0][:60]}")

    if text != original:
        TARGET.write_text(text, encoding="utf-8")
        print(f"\n已写入 {TARGET}")
    else:
        print("\n无需改动")
    return 0


if __name__ == "__main__":
    sys.exit(main())