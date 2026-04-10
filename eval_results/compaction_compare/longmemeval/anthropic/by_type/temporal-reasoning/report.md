# Compaction Compare — LongMemEval_longmemeval_s_cleaned_temporal-reasoning

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-5-20250929
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, summary_prompt
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 latency | mean compactions | errors |
|---|---|---|---|---|---|---|---|
| baseline | 30 | 0.0% | +0.0% | 0.0% | 9428ms | 0.0 | 4 |
| headroom_default | 30 | 55.0% | +0.0% | 0.0% | 5670ms | 0.0 | 0 |
| summary_prompt | 30 | 39.5% | +6.7% | 6.7% | 9207ms | 1.0 | 0 |

## Per Question Type Breakdown

| arm | temporal-reasoning |
|---|---|
| baseline | 0.0% |
| headroom_default | 0.0% |
| summary_prompt | 6.7% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-5-20250929`
- Summary model: `claude-haiku-4-5`

### Errors

- `baseline/longmemeval_gpt4_4929293a`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs47CSqbyG6v8wXCke1E'}
- `baseline/longmemeval_gpt4_1d4ab0c9`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs49AEC9dfiTCGvj5FVz'}
- `baseline/longmemeval_gpt4_1d80365e`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4D2P22d6C31ozm6HfR'}
- `baseline/longmemeval_gpt4_1e4a8aeb`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4PLJZZKo9EBKCtNBD9'}
