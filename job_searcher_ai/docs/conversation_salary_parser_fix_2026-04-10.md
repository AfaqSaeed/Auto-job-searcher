# Salary Parser Fix

- Saved at: 2026-04-10T13:28:51.260210Z

Fixed a crash in parsing/normalization.py where malformed numeric text like Industry 4.0. could be mistaken for a salary token and raise ValueError. Tightened the salary regex, added guarded numeric coercion, and added a regression test to ensure invalid numeric tokens return no salary instead of crashing the pipeline.
