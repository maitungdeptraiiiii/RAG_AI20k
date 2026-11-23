# Baseline trước giai đoạn 1 rule engine (HEAD 2ec031a, nhánh w03 → w04-rules-engine)

Chạy từ `app/team-4.2/` bằng `.venv/Scripts/python.exe -m pytest`.

## GATE
`tests/test_bridge_*.py tests/test_contract_graph_tools.py tests/test_ask_contract_graph.py tests/test_contract_graph_agent.py tests/test_contracts_api.py`
→ **323 passed, 1 skipped, 1 xfailed**.

## Toàn bộ suite
`pytest -q --ignore=tests/test_agent_partial_review.py` (file này lỗi import `_partition_claims` từ trước)
→ **35 failed, 1755 passed, 22 skipped, 16 xfailed** (≈10 phút). Các test fail nằm ở module không liên quan
(`test_dated_agent_e2e`, `test_warehouse_migration`, `test_pipeline`); danh sách tên đầy đủ: xem mục cuối.

## Golden
`tests/fixtures/rules/golden/engine_results.json`: 2571 ca, 1455 KB, sinh bằng engine cũ chưa sửa.

## Danh sách test fail của baseline (35)

- tests/test_agent_stability.py::test_bad_optional_assessment_actions_do_not_abort_good_evidence
- tests/test_agent_stability.py::test_bad_quote_is_removed_but_independent_verified_claim_is_retained
- tests/test_agent_stability.py::test_claim_depending_on_rejected_premise_is_not_published
- tests/test_agent_stability.py::test_invalid_quote_never_becomes_supported_when_degrading_invalid_claims
- tests/test_agent_stability.py::test_schema_repair_is_bounded_and_does_not_coerce_invalid_flags
- tests/test_answer_presentation.py::test_http_filters_final_answer_and_preserves_think_verified_emission[False-False]
- tests/test_answer_presentation.py::test_http_filters_final_answer_and_preserves_think_verified_emission[False-True]
- tests/test_answer_presentation.py::test_http_filters_final_answer_and_preserves_think_verified_emission[True-False]
- tests/test_answer_presentation.py::test_http_filters_final_answer_and_preserves_think_verified_emission[True-True]
- tests/test_conversation.py::test_agent_all_roles_receive_old_facts_and_masked_reference_context
- tests/test_conversation.py::test_baseline_generation_receives_full_masked_context[False]
- tests/test_conversation.py::test_baseline_generation_receives_full_masked_context[True]
- tests/test_conversation.py::test_http_failed_request_releases_session_without_remembering_error[False]
- tests/test_conversation.py::test_http_failed_request_releases_session_without_remembering_error[True]
- tests/test_conversation.py::test_http_normal_think_normal_share_server_memory_and_date_stays_request_local[False]
- tests/test_conversation.py::test_http_normal_think_normal_share_server_memory_and_date_stays_request_local[True]
- tests/test_conversation.py::test_json_disconnect_does_not_release_session_while_worker_is_running
- tests/test_conversation.py::test_numbered_reference_beyond_old_250_character_limit_reaches_condenser
- tests/test_dated_agent_e2e.py::test_date_reaches_all_layers_and_sources_are_valid[False-2021-06-15]
- tests/test_dated_agent_e2e.py::test_date_reaches_all_layers_and_sources_are_valid[False-2025-06-15]
- tests/test_dated_agent_e2e.py::test_date_reaches_all_layers_and_sources_are_valid[True-2021-06-15]
- tests/test_dated_agent_e2e.py::test_date_reaches_all_layers_and_sources_are_valid[True-2025-06-15]
- tests/test_dated_agent_e2e.py::test_leap_year_2024_02_29_accepted
- tests/test_dated_agent_e2e.py::test_multiple_anchors_keep_revisions_separate_and_block_unresolved_transition
- tests/test_dated_agent_e2e.py::test_parallel_requests_different_as_of_isolated
- tests/test_dated_agent_e2e.py::test_think_without_as_of_uses_temporal_scope_and_validity_filter
- tests/test_dated_agent_e2e.py::test_unavailable_catalog_is_503_before_sse_headers
- tests/test_pipeline.py::test_settings_load_does_not_override_existing_env
- tests/test_warehouse_migration.py::test_atomic_idempotent_migration_backup_and_unknown_applicability
- tests/test_warehouse_migration.py::test_binary_original_is_archived_while_catalog_serves_readable_extracted_text
- tests/test_warehouse_migration.py::test_library_counts_match_searchable_catalog_not_amendment_source_fragments
- tests/test_warehouse_migration.py::test_migration_with_missing_original_preserves_chunks_as_explicit_reconstruction
- tests/test_warehouse_migration.py::test_reference_source_is_shared_and_can_never_be_promoted_to_firm
- tests/test_warehouse_migration.py::test_temporal_review_repairs_format_once_without_weakening_source_certainty
- tests/test_warehouse_migration.py::test_ui_reads_catalog_without_initializing_warehouse_one
