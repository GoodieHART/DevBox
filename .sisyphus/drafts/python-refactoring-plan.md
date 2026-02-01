# Draft: Python Code Deduplication Refactoring Plan

## Requirements (confirmed)
- Extract all duplicated functions into reusable modules to eliminate code deduplication while maintaining backward compatibility
- Follow existing import + fallback pattern established in devbox.py
- Maintain backward compatibility 
- Run syntax validation after each change
- Place new modules in root directory alongside existing ones
- Break changes into atomic, verifiable steps
- Create step-by-step execution plan ordered by dependency
- Each step must be independently verifiable
- Include test creation strategy for each extracted function
- Define verification checkpoints for each step
- Include rollback strategy for each step
- Specify commit checkpoints after logical groups of changes

## Technical Decisions
- Use pytest-based testing framework (recommended for Python refactoring)
- Follow Test-Driven Refactoring approach: write tests first, then refactor
- Maintain current import + fallback pattern for backward compatibility
- Create new utility modules: backup_utils.py, persistence_utils.py, gpu_utils.py
- Follow atomic Git workflow with clear commit messages
- Use semantic versioning approach for compatibility

## Research Findings
- **Codebase Analysis**: devbox.py (1430+ lines) contains 5 major duplication patterns
- **Test Infrastructure**: None exists - need to create pytest framework
- **Current Pattern**: Import + fallback already established for ui_utils.py and quotes_loader.py
- **Duplicated Code**: ~200+ lines across UI functions, backup functions, GPU wrappers, persistence setup
- **Dependencies**: Modal framework, standard library, existing ui_utils.py and quotes_loader.py modules

## Open Questions
- Should we remove the fallback implementations from devbox.py entirely, or keep them as ultimate safety net?
- What specific test coverage percentage should we target?
- Should we implement deprecation warnings for the fallback functions?
- Any preference for commit message format or branching strategy?

## Scope Boundaries
- INCLUDE: Extracting duplicate functions, creating utility modules, setting up test infrastructure, maintaining backward compatibility
- EXCLUDE: Changing Modal framework usage, modifying core business logic, changing public API interfaces, altering file structure beyond new utility modules
- GUARDRAILS: Must not break existing functionality, must maintain import + fallback pattern, must keep devbox.py as main entry point