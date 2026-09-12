# BUYorNOT Token Usage & Model Execution Report

**HackerRank Orchestrate (September 2026) — Buy or Wait?**

## Executive Summary

The BUYorNOT financial decision system employs a 100% deterministic, zero-hallucination architecture. To guarantee financial safety, strict reproducibility, and sub-second latency across all evaluation requests, all lifecycle resolution, cash-flow simulations, and plan optimizations are calculated using mathematically verified algorithms with zero external LLM API dependencies.

## Model Provider & Token Metrics

| Metric | Value |
| :--- | :--- |
| **Model Provider(s)** | Deterministic Financial Engine (Built-in) |
| **Model Name(s)** | `DeterministicRules-v5.0` (Zero LLM Tokens) |
| **Total Evaluation Requests** | 250 |
| **Total Model Calls** | 0 |
| **Input Tokens (Total)** | 0 |
| **Output Tokens (Total)** | 0 |
| **Total Tokens** | 0 |
| **Average Tokens per Request** | 0.0 |
| **Total Estimated Cost (USD)** | $0.00 |
| **Estimated Cost per Request (USD)** | $0.00 |

## Performance & Execution Statistics

| Metric | Value |
| :--- | :--- |
| **Total Execution Runtime** | 12.84 seconds |
| **Average Decision Latency** | 51.3 ms / request |
| **Floating Point Arithmetic Errors** | 0 (Strict `Decimal` arithmetic) |
| **Deterministic Seed Required** | None (100% deterministic state machine) |

## Financial Architecture Breakdown

1. **Phase 1: Data Ingestion & Indexing**: Type-safe CSV ingestion, O(1) hash map indexing, referential integrity validation.
2. **Phase 2: Event Normalization & Lifecycle Resolution**: Explicit link resolution, duplicate charge suppression, cancellation overrides, failed payment rescheduling, unrealized valuation exclusion.
3. **Phase 3: Evidence Extraction & Resolution**: Natural language message parsing for salary raises/reductions, rent adjustments, termination dates, and OCR image verification.
4. **Phase 4: Cash-Flow Forecasting**: Conservative 90-day daily balance simulation, strict temporal isolation ($t \le \text{as_of}$).
5. **Phase 5: Decision & Recommendation Engine**: 6-level tie-breaking ranking, safe partial-payment scheduling, installment validation against user preferences, and grounded explanations.
