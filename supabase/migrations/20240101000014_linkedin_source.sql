-- Add source column to pipeline_entries for tracking entry origin (gmail vs linkedin)
ALTER TABLE public.pipeline_entries
  ADD COLUMN IF NOT EXISTS source TEXT;
