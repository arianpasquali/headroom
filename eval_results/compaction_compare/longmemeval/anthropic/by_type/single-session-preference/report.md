# Compaction Compare — LongMemEval_longmemeval_s_cleaned_single-session-preference

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-5-20250929
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, summary_prompt
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 latency | mean compactions | errors |
|---|---|---|---|---|---|---|---|
| baseline | 30 | 0.0% | +0.0% | 10.0% | 11926ms | 0.0 | 10 |
| headroom_default | 30 | 54.7% | +23.3% | 33.3% | 7561ms | 0.0 | 0 |
| summary_prompt | 30 | 39.4% | +13.3% | 23.3% | 11600ms | 1.0 | 0 |

## Per Question Type Breakdown

| arm | single-session-preference |
|---|---|
| baseline | 10.0% |
| headroom_default | 33.3% |
| summary_prompt | 23.3% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-5-20250929`
- Summary model: `claude-haiku-4-5`

### Errors

- `baseline/longmemeval_195a1a1b`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs48ZQvsTijjikP7Czvm'}
- `baseline/longmemeval_54026fce`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4CiTGJXzpEAHfwdCH5'}
- `baseline/longmemeval_d24813b1`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4GJcv4i9wvvpJfFgoi'}
- `baseline/longmemeval_57f827a0`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4Gqr7uhTDKURQrcvcv'}
- `baseline/longmemeval_75f70248`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4LR3ES5AhmFxBruArx'}
- `baseline/longmemeval_d6233ab6`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4MBq2D1h6LzHZP9VJg'}
- `baseline/longmemeval_1da05512`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4MqGnVt8xZpHfbfdGW'}
- `baseline/longmemeval_b6025781`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4PVPWUUPTpMQtf3ME6'}
- `baseline/longmemeval_a89d7624`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4QyAdHE6FPMuRdYHDX'}
- `baseline/longmemeval_1c0ddc50`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4UtZuyRgqJnH8UoEcg'}
