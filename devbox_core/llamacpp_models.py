"""Curated GGUF model catalog for the llama.cpp Research Center."""

LLAMACPP_MODELS = {
    "1": {
        "name": "Qwen3.5-9B-Instruct",
        "repo_id": "unsloth/Qwen3.5-9B-GGUF",
        "filename": "Qwen3.5-9B-Q4_K_M.gguf",
        "size": "5.68GB",
        "type": "text",
        "description": "Best overall - thinking mode, 256K context",
        "function_calling": True,
        "settings": {"temp": 0.7, "top_p": 0.8, "top_k": 20}
    },
    "2": {
        "name": "Bonsai-8B",
        "repo_id": "prism-ml/Bonsai-8B-gguf",
        "filename": "Bonsai-8B-Q1_0.gguf",
        "size": "1.15GB",
        "type": "text",
        "description": "1-bit ultra-lightweight - 14x smaller, 6x faster on GPU",
        "function_calling": True,
        "settings": {"temp": 0.5, "top_p": 0.85, "top_k": 20}
    },
    "3": {
        "name": "SmolVLM-500M",
        "repo_id": "ggml-org/SmolVLM-500M-Instruct-GGUF",
        "filename": "ggml-model-mmproj-f16.gguf",
        "size": "~1.5GB",
        "type": "vision",
        "description": "Fast image captioning",
        "function_calling": False,
        "settings": {"temp": 0.7, "top_p": 0.9, "top_k": 40}
    },
    "4": {
        "name": "Gemma4-26B-A4B",
        "repo_id": "unsloth/gemma-4-26b-a4b-it-GGUF",
        "filename": "gemma-4-26b-a4b-it-Q4_K_M.gguf",
        "size": "~17GB",
        "type": "vision",
        "description": "Google's latest - MoE (4B active), 256K context, multimodal",
        "function_calling": True,
        "settings": {"temp": 0.7, "top_p": 0.8, "top_k": 20}
    },
    "5": {
        "name": "Custom Model",
        "repo_id": None,
        "filename": None,
        "size": "User-defined",
        "type": "text",
        "description": "Any GGUF model from HuggingFace",
        "function_calling": True,
        "settings": {"temp": 0.7, "top_p": 0.9, "top_k": 40}
    },
}
