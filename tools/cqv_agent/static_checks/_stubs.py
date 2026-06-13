"""
Stubs for static checks that genuinely require a language parser or CFG.

All previous stubs have been implemented:
- patch 0071: check_set_seed_scope, check_imports_complete,
  check_function_docs_present, check_no_unbounded_loops,
  check_global_state_mutation -> r_heuristics.py
- patch 0092: check_parse_success, check_duplicate_code_blocks,
  check_growing_vectors, check_error_handling_coverage
  -> heuristics_cross_lang.py
- patches 0096-0098: check_undefined_references, check_function_signatures,
  check_dead_code, check_loop_invariants -> check_r_ast.py
  (tree-sitter-languages, optional dep, graceful fallback)

No stubs remain. This module is kept as a placeholder.
"""
