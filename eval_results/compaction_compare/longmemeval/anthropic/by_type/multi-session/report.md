# Compaction Compare — LongMemEval_longmemeval_s_cleaned_multi-session

## Configuration

- **Provider**: anthropic
- **Model**: claude-sonnet-4-5-20250929
- **Threshold**: 50,000 tokens
- **Arms**: baseline, headroom_default, summary_prompt
- **Baseline arm**: baseline

## Results

| arm | n | compression | delta quality vs baseline | quality correct | p50 latency | mean compactions | errors |
|---|---|---|---|---|---|---|---|
| baseline | 30 | 0.0% | +0.0% | 16.7% | 9680ms | 0.0 | 12 |
| headroom_default | 30 | 55.8% | +13.3% | 30.0% | 5927ms | 0.0 | 0 |
| summary_prompt | 30 | 39.6% | +3.3% | 20.0% | 9631ms | 1.0 | 0 |

## Per Question Type Breakdown

| arm | multi-session |
|---|---|
| baseline | 16.7% |
| headroom_default | 30.0% |
| summary_prompt | 20.0% |

## Threshold Sweep

Single threshold run at 50,000 tokens. Multi-threshold sweeps can be merged here by a future caller.

## Notes

- Answer model: `claude-sonnet-4-5-20250929`
- Summary model: `claude-haiku-4-5`

### Errors

- `baseline/longmemeval_gpt4_f2262a51`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs47m8brGi2kXs9eCiHT'}
- `baseline/longmemeval_dd2973ad`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs48G6PE7PHNU87Rc6Xb'}
- `baseline/longmemeval_c4a1ceb8`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs48q7FFxrkQPhU4zvWs'}
- `baseline/longmemeval_36b9f61e`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4CSuscV2JFBsrotoDC'}
- `baseline/longmemeval_28dc39ac`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4D1tFd8YGAfoWmmjCb'}
- `baseline/longmemeval_gpt4_15e38248`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4HeuLHVywe77T1zGdj'}
- `baseline/longmemeval_88432d0a`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4JECowpXoaPMPF81to'}
- `baseline/longmemeval_gpt4_7fce9456`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4MDh8k7mge8f4hzV8J'}
- `baseline/longmemeval_d682f1a2`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4MrfsFmR7F1PHTKW7u'}
- `baseline/longmemeval_7024f17c`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4NT4aWEpBpiSXSmAuB'}
- `baseline/longmemeval_gpt4_5501fe77`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4P6GCzB63puxhMXgpE'}
- `baseline/longmemeval_gpt4_d12ceb0e`: Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "This request would exceed your organization's rate limit of 2,000,000 input tokens per minute (org: 1f04809c-ca50-404b-bc39-093c4ae7cc67, model: claude-sonnet-4-5-20250929). For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later. You may also contact sales at https://claude.com/contact-sales to discuss your options for a rate limit increase."}, 'request_id': 'req_011CZs4RxcfYaawiA6ZnHd6M'}
