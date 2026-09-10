-- Migration 002 — record committee integrity and evidence-gate outcomes.
--
-- Phase 1 hardening (ADR-020, ADR-021). Two facts were previously derivable
-- only from run artifacts, or not recorded at all:
--   1. whether a run really was a dual-agent committee or a degraded one;
--   2. whether a proposed action was restricted by the deterministic evidence
--      gate, and what it was originally proposed as.
-- Both are now first-class columns so history and audit do not depend on files.
--
-- Additive only: every column is nullable or has a default, so existing personal
-- data is preserved untouched. Runs recorded before this migration are labelled
-- 'UNKNOWN' rather than being retroactively claimed to have been full committees.
-- Rollback: these columns can be dropped; no existing column is altered.

ALTER TABLE research_runs ADD COLUMN committee_mode TEXT NOT NULL DEFAULT 'UNKNOWN';
ALTER TABLE research_runs ADD COLUMN committee_integrity_json TEXT;
ALTER TABLE research_runs ADD COLUMN analyst_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE research_runs ADD COLUMN critique_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE research_runs ADD COLUMN data_quality_score INTEGER;
ALTER TABLE research_runs ADD COLUMN agreement_score INTEGER;
ALTER TABLE research_runs ADD COLUMN evidence_gate_json TEXT;

ALTER TABLE recommendations ADD COLUMN proposed_action TEXT;
ALTER TABLE recommendations ADD COLUMN proposed_confidence INTEGER;
ALTER TABLE recommendations ADD COLUMN restricted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE recommendations ADD COLUMN restriction_reasons_json TEXT;

CREATE INDEX idx_runs_committee_mode ON research_runs(committee_mode);
