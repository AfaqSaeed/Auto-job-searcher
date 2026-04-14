# Fix LLMAssessment List Coercion

- Saved at: 2026-04-14T17:23:10.747679Z

## Request
Fix the crash during run-all where LLMAssessment validation fails because the LLM sometimes returns lists for fields that are expected to be strings.

## Cause
The ranking path passed the raw Ollama JSON directly into LLMAssessment.model_validate(). Some models return list values for recommended_resume_emphasis and recommended_cover_letter_angle, which violates the schema and caused a ValidationError.

## Change
Updated src\\job_searcher\\ranking\\llm_reasoning.py to normalize LLM payloads before validation. String fields are now coerced from list or scalar values into strings, and list fields are normalized consistently.

## Result
The ranking step no longer crashes when Ollama returns list-valued fields for LLMAssessment. Those values are converted into schema-compatible strings or string lists before validation.

## Validation
Ran C:\\Users\\afaqs\\anaconda3\\python.exe -m py_compile on src\\job_searcher\\ranking\\llm_reasoning.py and executed a small runtime check showing list-to-string and string-to-list coercion works as expected.
