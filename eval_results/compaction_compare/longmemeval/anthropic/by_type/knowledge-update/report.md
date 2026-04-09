# Compaction Compare — LongMemEval_longmemeval_s_cleaned_knowledge-update

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-5-20250929
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, summary_prompt
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 latency | mean compactions | errors |
|---|---|---|---|---|---|---|---|
| baseline | 30 | 0.0% | +0.0% | 46.7% | 9696ms | 0.0 | 3 |
| headroom_default | 30 | 55.3% | +23.3% | 70.0% | 4131ms | 0.0 | 0 |
| summary_prompt | 30 | 39.5% | +3.3% | 50.0% | 8477ms | 1.0 | 0 |

## Per Question Type Breakdown

| arm | knowledge-update |
|---|---|
| baseline | 46.7% |
| headroom_default | 70.0% |
| summary_prompt | 50.0% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-5-20250929`
- Summary model: `claude-haiku-4-5`

### Errors

- `baseline/longmemeval_41698283`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4GaHEyaTuGiFEt1oc9'}
- `baseline/longmemeval_2698e78f`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4H96SzVCX7cuz5oxCF'}
- `baseline/longmemeval_618f13b2`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4NYLLQ5MKGhxrN3VKF'}
