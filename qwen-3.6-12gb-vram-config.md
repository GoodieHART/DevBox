# Qwen 3.6 Fast TPS Config (12GB VRAM)

**Source:** [Michael Guo on X](https://x.com/Michaelzsguo/status/2050380832007721213?s=20)
**Type:** Visual Clip / Technical Config

## 🚀 The "Trick" for High TPS on 12GB VRAM
To fit a large model (35B total parameters) with a massive 128K context window into only 12GB of VRAM while maintaining speed, the following optimizations are used:

1.  **MoE Architecture (`A3B`):** Uses a Mixture of Experts model where only ~3B parameters are active per token, reducing compute load.
2.  **KV Cache Quantization (`-ctk q8_0`, `-ctv q8_0`):** Stores Key-Value caches in 8-bit instead of 16-bit. This halves the VRAM required for the context window, preventing OOM errors.
3.  **Flash Attention (`-fa on`):** Optimizes the attention mechanism for better memory efficiency and faster processing.

## 🛠️ Model Specifications
- **Model:** `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`
- **Total Params:** ~35B
- **Active Params:** ~3B
- **Quantization:** 4-bit (Q4_K_XL) via Unsloth Dynamic
- **Format:** GGUF

## 💻 Full Execution Command
```bash
llama-server \
--model ~/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf \
--port 8001 \
--alias qwen3.6-35b-a3b \
-c 131072 \
-n 32768 \
--no-context-shift \
--temp 0.6 \
--top-p 0.95 \
--top-k 20 \
--repeat-penalty 1.00 \
--presence-penalty 0.00 \
--fit on \
-fa on \
-ctk q8_0 \
-ctv q8_0 \
--chat-template-kwargs '{"preserve_thinking": true}'
```

## 📋 Parameter Breakdown
- `-c 131072`: Sets context window to 128K tokens.
- `-n 32768`: Sets max output to 32K tokens.
- `--fit on`: Maximizes hardware usage.
- `-fa on`: Enables Flash Attention.
- `-ctk q8_0 / -ctv q8_0`: 8-bit KV cache quantization (The VRAM saver).
- `--chat-template-kwargs '{"preserve_thinking": true}'`: Preserves the model's "thinking" process in output.
