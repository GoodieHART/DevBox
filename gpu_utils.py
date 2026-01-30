"""
GPU utilities for DevBox applications.

Provides parameterized GPU launcher functions to eliminate code duplication.
"""

# GPU configurations for different DevBox types
GPU_CONFIGS = {
    "t4": {"gpu": "t4", "description": "NVIDIA T4"},
    "l4": {"gpu": "l4", "description": "NVIDIA L4"},
    "a10g": {"gpu": "a10g", "description": "NVIDIA A10G"}
}

# Base arguments for GPU-powered DevBoxes
BASE_GPU_ARGS = {
    "secrets": ["modal.Secret.from_name(\"ssh-public-key\")"],
    "volumes": {"/data": None},  # Will be filled with actual volume
    "timeout": 3600
}

# GPU-specific arguments
GPU_ARGS = {
    "t4": {"cpu": 0.5, "memory": 1024},
    "l4": {"cpu": 0.5, "memory": 1024}, 
    "a10g": {"cpu": 0.5, "memory": 1024}
}

# RDP-specific arguments (higher resources)
RDP_GPU_ARGS = {
    "t4": {"cpu": 1.5, "memory": 4096},
    "l4": {"cpu": 1.5, "memory": 4096},
    "a10g": {"cpu": 1.5, "memory": 4096}
}


def get_gpu_config(gpu_type: str, is_rdp: bool = False):
    """
    Get GPU configuration for specified GPU type and connection type.
    
    Args:
        gpu_type (str): GPU type ('t4', 'l4', 'a10g')
        is_rdp (bool): Whether this is for RDP (higher resources)
    
    Returns:
        dict: Complete GPU configuration
    """
    if gpu_type not in GPU_CONFIGS:
        raise ValueError(f"Unsupported GPU type: {gpu_type}")
    
    config = BASE_GPU_ARGS.copy()
    config.update(GPU_CONFIGS[gpu_type])
    
    # Add GPU-specific resource arguments
    resource_args = RDP_GPU_ARGS[gpu_type] if is_rdp else GPU_ARGS[gpu_type]
    config.update(resource_args)
    
    return config


def get_gpu_decorator_args(gpu_type: str, is_rdp: bool = False):
    """
    Get decorator arguments for Modal @app.function with GPU configuration.
    
    Args:
        gpu_type (str): GPU type ('t4', 'l4', 'a10g')
        is_rdp (bool): Whether this is for RDP
    
    Returns:
        dict: Arguments for @app.function decorator
    """
    config = get_gpu_config(gpu_type, is_rdp)
    
    # Convert to decorator format
    decorator_args = {
        "image": None,  # Will be filled with actual image
        "gpu": config["gpu"],
        "secrets": config["secrets"],
        "volumes": config["volumes"],
        "cpu": config["cpu"],
        "memory": config["memory"],
        "timeout": config["timeout"]
    }
    
    return decorator_args


def get_available_gpus():
    """
    Get list of available GPU types.
    
    Returns:
        list: Available GPU types
    """
    return list(GPU_CONFIGS.keys())


def get_gpu_description(gpu_type: str):
    """
    Get human-readable description of GPU type.
    
    Args:
        gpu_type (str): GPU type
    
    Returns:
        str: Description of GPU
    """
    if gpu_type not in GPU_CONFIGS:
        return f"Unknown GPU: {gpu_type}"
    
    return GPU_CONFIGS[gpu_type]["description"]