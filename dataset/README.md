---
size_categories:
- n<1K
task_categories:
- image-text-to-text
tags:
- gaming
- action policy
- world model
- vision action model
- vision action language model
---

![Open Pixel2Play Banner](banner.png)

# Dataset Card for p2p-toy-examples

This is a toy dataset for a conceptual understanding and test of the training code for the [Open Pixel2Play (P2P)](https://elefant-ai.github.io/open-p2p/) project. 

- **Paper:** [Scaling Behavior Cloning Improves Causal Reasoning: An Open Model for Real-Time Video Game Playing](https://huggingface.co/papers/2601.04575)
- **Repository:** [https://github.com/elefant-ai/open-p2p](https://github.com/elefant-ai/open-p2p)
- **Project Page:** [https://elefant-ai.github.io/open-p2p/](https://elefant-ai.github.io/open-p2p/)

The full dataset is available at [elefantai/p2p-full-data](https://huggingface.co/datasets/elefantai/p2p-full-data). 

**If you find this dataset useful in your research, please [cite our paper](#citation).**

## Sample Usage

To download this toy dataset using the official repository script:
```bash
uv run python scripts/download_data.py --toy
```

## Dataset Details

The dataset is structured in this way:

```text
|-- dataset
|   |-- uuid1
|   |   |-- 192x192.mp4
|   |   |-- video.mp4
|   |   |-- annotation.proto
|   |-- uuid2
|   |   |-- 192x192.mp4
|   |   |-- video.mp4
|   |   |-- annotation.proto
...
```

where we have
- `video.mp4` is the raw video
- `192x192.mp4` is the resized video that used for model training
- `annotation.proto` contains the user actions and text annotations per frame. 

Moreover, `annotation.proto` contains the following information
```text
{
  "metadata": {
    "timestamp": Time of recording
    "env": name of the game environment
    "...": Additional metadata fields
  },
  "frame_annotations":[
    { # List of annotations available for each frame
      "user_action": {
        # Present if the action is performed by the user
        "keyboard": [
          List of keys currently being pressed (e.g., ['w', 'space'])
        ],
        "mouse": {
          "mouse_absolute_px": Mouse movement/position on X-axis (pixels)
          "mouse_absolute_py": Mouse movement/position on Y-axis (pixels)
          "scroll_delta_px": Pixels moved by the middle mouse scroll
          "buttons_down": [
            List of 0 or 1 (e.g., [0] for Left Click, [1] for Right Click)
          ]
        }
      },
      "system_action": {
        # Present if action is from inference server (correction data only)
        # Same as the user_action
      },
      "frame_text_annotation": {
        "instruction": The natural language text instruction
        "frame_text_annotator": The VLM model used for the annotation
        "duration": Duration of the instruction in seconds
        "text_embedding_dict": {
          tokenizer_name: The tokenized text embedding vector
        }
      }
    }
  ]
}
```

## Licensing & Usage

This dataset is released by **Elefant AI** under a **Modified MIT License**. 

### Modified MIT License
**Copyright (c) 2026 Elefant AI**

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software" and "Dataset"), to deal in the Software and Dataset without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software and Dataset, subject to the following conditions:
1. **Attribution:** The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software and Dataset.
2. **Third-Party Rights & Fair Use:** This Dataset contains audiovisual recordings of third-party video games. Elefant AI does not claim ownership of the underlying game assets, characters, or engines. 
    * The user of this Dataset acknowledges that their use, redistribution, or commercialization of the game recording portions of the Dataset may be subject to the End User License Agreements (EULA) and Intellectual Property guidelines of the respective game publishers.
    * **User Responsibility:** It is the sole responsibility of the user to ensure that their specific use case—including AI training, research, or commercial applications—falls within "Fair Use" or the "Fair Dealing" provisions of their jurisdiction, or complies with the explicit media usage policies of the game publishers.
3. **No Endorsement:** Use of this Dataset does not imply endorsement by the game publishers or any affiliated entities.

**THE SOFTWARE AND DATASET ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE/DATASET OR THE USE OR OTHER DEALINGS IN THE SOFTWARE/DATASET.**

### Important Disclaimer for Users
While Elefant AI provides the **human annotations and curation** under an open license, the raw video content remains the intellectual property of the original game developers. 

---

## Citation

```bibtex
@misc{yue2026scaling,
      title={Scaling Behavior Cloning Improves Causal Reasoning: An Open Model for Real-Time Video Game Playing}, 
      author={Yuguang Yue and Irakli Salia and Samuel Hunt and Chris Green and Wenzhe Shi and Jonathan J. Hunt},
      year={2026},
      eprint={2601.04575},
      archivePrefix={arXiv},
      primaryClass={cs.LG},
      url={https://arxiv.org/abs/2601.04575}
}
```