# ABSOLUTE DRAIN DUMP - MODAL REFACTORING CORRECTION PLAN

## CRITICAL REALIZATION
Modal is NOT a library - it's a deployment platform. The file with @app.function decorators
MUST be the entry point. Separate main.py and launchers.py CANNOT work.

## ARCHITECTURAL CONSTRAINTS (Non-negotiable)
1. @app.function decorators MUST be at module level in the file being run
2. CLI calling .remote() MUST be in the SAME FILE as the decorators
3. Usage: `modal run devbox.py` - this is the ONLY valid entry point
4. Can import shared logic from other modules, but decorators stay in main file

## CURRENT BROKEN STATE
- ❌ main.py - Creates Modal functions dynamically (impossible)
- ❌ launchers.py - Decorators inside functions (invisible to Modal parser)
- ✅ config.py, images.py, utils.py, gpu_utils.py, shared_runtime.py - Work as imports
- ✅ devbox.py (original) - Works but not refactored

## CORRECTED APPROACH

### PHASE 1: CLEANUP (Delete Broken Files)
- DELETE main.py
- DELETE launchers.py
- These files implement patterns that Modal cannot execute

### PHASE 2: REFACTOR devbox.py (Keep as Single Modal File)
Keep devbox.py as THE file, but refactor internals:

#### Step 2.1: Update Imports Section
Replace all image definitions with imports from images.py:
```python
# OLD (in devbox.py):
standard_devbox_image = modal.Image.debian_slim(...)  # ~30 lines

# NEW (in devbox.py):
from images import (  # ~1 line
    standard_devbox_image, cuda_devbox_image, doc_processing_image,
    gemini_cli_image, llm_playroom_image, llamacpp_cpu_image, rdp_devbox_image
)
```

#### Step 2.2: Update Constants Section
Replace scattered constants with imports from config.py:
```python
# OLD (in devbox.py):
IDLE_TIMEOUT_SECONDS = 300  # Line 84
cpu_devbox_args = dict(...)  # Lines 868-874
gpu_devbox_args = dict(...)  # Lines 876-882

# NEW (in devbox.py):
from config import IDLE_TIMEOUT_SECONDS, get_resource_config
# Use get_resource_config("cpu") / get_resource_config("gpu", "t4")
```

#### Step 2.3: Update GPU Section
Replace hardcoded GPU configs with imports from gpu_utils.py:
```python
# OLD (in devbox.py):
gpu_devbox_args = dict(secrets=..., volumes=..., cpu=1.0, memory=2048)

# NEW (in devbox.py):
from gpu_utils import get_gpu_config, GPU_ARGS
# Use get_gpu_config("t4", is_rdp=False) for proper GPU configuration
```

#### Step 2.4: Update Utility Functions
Replace inline functions with imports from utils.py:
```python
# OLD (in devbox.py):
def inject_ssh_key():  # Lines 342-471 (~130 lines)
    # ... massive inline implementation ...

# NEW (in devbox.py):
from utils import inject_ssh_key  # 1 line import
# Function now imported from centralized module
```

#### Step 2.5: Update Runtime Logic
Replace run_devbox_shared with imports from shared_runtime.py:
```python
# OLD (in devbox.py):
def run_devbox_shared(extra_packages):  # Lines 474-680 (~210 lines)
    # ... persistence, backup, SSH setup logic ...

# NEW (in devbox.py):
from shared_runtime import handle_devbox_startup
# Call handle_devbox_startup(extra_packages, "ssh")
```

#### Step 2.6: Keep @app.function Decorators (CRITICAL)
These MUST stay at module level in devbox.py:
```python
# In devbox.py - Module level, Modal will see these:

@app.function(image=standard_devbox_image, **get_resource_config("cpu"))
def launch_devbox(extra_packages):
    return handle_devbox_startup(extra_packages, "ssh")

@app.function(image=cuda_devbox_image, gpu="t4", **get_resource_config("gpu", "t4"))
def launch_devbox_t4(extra_packages):
    return handle_devbox_startup(extra_packages, "ssh")

# ... all 12 @app.function definitions stay here ...
```

#### Step 2.7: Keep main() Function (CLI)
The CLI stays in devbox.py and calls .remote() on the deployed functions:
```python
def main():
    # Display menu
    choice = display_main_menu()
    
    # Call deployed functions via .remote()
    if choice == "1":
        launch_devbox.remote(extra_packages)
    elif choice == "2":
        launch_devbox_t4.remote(extra_packages)
    # ... etc ...

if __name__ == "__main__":
    main()
```

### PHASE 3: VERIFICATION STEPS
1. Syntax check: python3 -m py_compile devbox.py
2. Import check: python3 -c "import devbox"
3. Modal dry-run: modal run devbox.py --help (if available)
4. Manual test: Run through menu with choice "13" (exit)

### PHASE 4: EXPECTED OUTCOME
- devbox.py imports from 5 shared modules (config, images, utils, gpu_utils, shared_runtime)
- devbox.py contains all @app.function decorators at module level
- devbox.py contains the main() CLI
- Usage: `modal run devbox.py` works exactly as before
- ~400 lines of duplication eliminated through imports
- All functionality preserved

## QUANTIFIED IMPROVEMENTS
BEFORE: devbox.py = 1,816 lines (all in one file)
AFTER:  
  - devbox.py = ~1,200 lines (refactored, imports shared logic)
  - config.py = 85 lines (extracted constants)
  - images.py = 75 lines (extracted image definitions)
  - utils.py = 68 lines (extracted utilities)
  - gpu_utils.py = 110 lines (extracted GPU config, ENHANCED with L40S)
  - shared_runtime.py = 78 lines (extracted runtime logic)
  - TOTAL = ~1,616 lines (200 lines saved through deduplication)

## FILES TO DELETE
- main.py (broken separate entry point)
- launchers.py (broken dynamic function creation)

## FILES TO KEEP/MODIFY
- devbox.py (refactor to use imports, keep decorators and CLI)
- config.py (keep as shared module)
- images.py (keep as shared module)
- utils.py (keep as shared module)
- gpu_utils.py (keep as shared module, already enhanced)
- shared_runtime.py (keep as shared module)

## CRITICAL SUCCESS CRITERIA
1. `modal run devbox.py` executes without errors
2. Menu displays correctly
3. Can select option and reach function call
4. Functions are properly decorated and deployable
5. All imports resolve correctly
6. No syntax errors
7. Backward compatible with original behavior

## RISK MITIGATION
- Original devbox.py is preserved in git history
- If refactoring fails, can `git checkout devbox.py` to restore
- Each change is atomic and reversible
- Testing after each major step

## TESTING PROTOCOL
1. After each file deletion - verify git status
2. After each import addition - test syntax
3. After devbox.py refactor - test imports
4. Final test - run menu and exit (choice 13)
5. If any test fails - stop and fix before continuing

---
END OF DRAIN DUMP
Execute this plan exactly as specified.
