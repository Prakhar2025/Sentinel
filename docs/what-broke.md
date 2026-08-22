# What Broke (living log)

Every entry is a genuine failure hit during the build, appended in real time with its fix. Entries are never rewritten, polished, or invented after the fact. This file is the source for the "what broke at 2 AM" pitch segment and is freshness-enforced by a pre-commit hook.

| Date (IST) | Phase | What broke | Root cause | Fix |
|------------|-------|------------|------------|-----|
| 2026-08-22 | 0 | System `python` was 3.9.10; venv created from it cannot run the py3.12 stack | PATH points at an old Python install while 3.12.10 exists via the `py` launcher | Pin all tooling to `py -3.12` (Makefile, docs); venv recreated from 3.12.10 |
| 2026-08-22 | 0 | `pip install` hung and failed with DNS errors on `pypi.ngc.nvidia.com` | Machine-wide pip config adds the NVIDIA NGC index as an extra index and that host no longer resolves | Set `PIP_CONFIG_FILE` to a nonexistent path for all install commands (bypasses global config); documented in Makefile workflow |
| 2026-08-22 | 0 | `OperationNotPageableError` calling Bedrock `list_foundation_models` | boto3 1.4x: the operation is not paginated; script used `get_paginator` | Single direct call; discovered in the boto3 docs shape |
| 2026-08-22 | 0 | `ParamValidationError: Invalid type for parameter byInferenceType, value: ['ON_DEMAND']` | The API takes a scalar string, not a list | `byInferenceType="ON_DEMAND"` |
| 2026-08-22 | 0 | `AttributeError: 'VerifyResult' object has no attribute '__dict__'` on output | dataclass declared with `slots=True` (no instance dict) | `dataclasses.asdict()` for serialization |
| 2026-08-22 | 0 | gpt-oss 120B/20B returned empty text (non-JSON parse failure) | They are reasoning models: a 128-token cap is consumed entirely by thinking before any output token | Raise maxTokens to 512 for verification calls; Phase 5 must check stopReason before treating empty output as non-compliance |
| 2026-08-22 | 0 | Nova Lite and GLM-5 responses failed `json.loads` despite being valid JSON | Both wrap JSON in markdown code fences; none of the five candidates support native `responseFormat` on Bedrock | Fence-stripping parser in the verification script; Phase 5 design updated to require fence-stripping + jsonschema gate |
| 2026-08-22 | 0 | Llama 3.3 70B Converse call rejected with ValidationException | Model is listed in-region but its base ID is not invocable (needs a cross-region inference profile) | Dropped from the fallback chain; `zai.glm-5` keeps the final slot (measured 703 ms, valid JSON) |
