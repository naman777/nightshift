#### Held-out scenarios (final numbers)

Split: `heldout` · 15 scenarios x 3 repeat(s) · prompts `v1` · offline reference policy (mock provider); not LLM results

| Configuration | Root-cause acc. | Top-3 | Judge | Remediation | Unsafe-action rate | Grounding | Red-herring acc. | Cost / incident | Time to dx (modelled p50 / p95) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Naive: blame last change | 20% ± 0 | 20% | 20% | 93% | 0% | 0% | 33% | $0.000 | 0.8s / 0.8s |
| Naive: blame noisiest service | 7% ± 0 | 7% | 0% | 27% | 0% | 0% | 0% | $0.000 | 0.8s / 0.8s |
| Single agent (all tools) | 100% ± 0 | 100% | 100% | 100% | 0% | 100% | 100% | $0.051 | 18.1s / 20.3s |
| Multi-agent | 100% ± 0 | 100% | 100% | 100% | 0% | 100% | 100% | $0.081 | 16.4s / 18.1s |
| Multi-agent + model routing | 100% ± 0 | 100% | 100% | 100% | 0% | 100% | 100% | $0.036 | 16.4s / 18.1s |
| Multi-agent, no citation rule (ablation) | 100% ± 0 | 100% | 100% | 100% | 0% | 100% | 100% | $0.081 | 16.4s / 18.1s |
| Multi-agent + incident memory | 100% ± 0 | 100% | 100% | 100% | 0% | 100% | 100% | $0.082 | 17.0s / 18.9s |

Invalid scenarios (expected alert never fired): 0.

#### Development scenarios

Split: `dev` · 25 scenarios x 3 repeat(s) · prompts `v1` · offline reference policy (mock provider); not LLM results

| Configuration | Root-cause acc. | Top-3 | Judge | Remediation | Unsafe-action rate | Grounding | Red-herring acc. | Cost / incident | Time to dx (modelled p50 / p95) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Naive: blame last change | 20% ± 0 | 20% | 16% | 80% | 0% | 0% | 30% | $0.000 | 0.8s / 0.8s |
| Naive: blame noisiest service | 12% ± 0 | 12% | 0% | 32% | 0% | 0% | 20% | $0.000 | 0.8s / 0.8s |
| Single agent (all tools) | 100% ± 0 | 100% | 100% | 96% | 0% | 100% | 100% | $0.052 | 18.7s / 21.9s |
| Multi-agent | 100% ± 0 | 100% | 100% | 96% | 0% | 100% | 100% | $0.082 | 16.7s / 18.5s |
| Multi-agent + model routing | 100% ± 0 | 100% | 100% | 96% | 0% | 100% | 100% | $0.036 | 16.7s / 18.5s |
| Multi-agent, no citation rule (ablation) | 100% ± 0 | 100% | 100% | 96% | 0% | 100% | 100% | $0.082 | 16.7s / 18.5s |
| Multi-agent + incident memory | 100% ± 0 | 100% | 100% | 96% | 0% | 100% | 100% | $0.084 | 17.2s / 19.3s |

Invalid scenarios (expected alert never fired): 0.

#### Hard stress set (not part of the headline 40): decoys, concurrent faults, telemetry outages

Split: `hard` · 10 scenarios x 3 repeat(s) · prompts `v1` · offline reference policy (mock provider); not LLM results

| Configuration | Root-cause acc. | Top-3 | Judge | Remediation | Unsafe-action rate | Grounding | Red-herring acc. | Cost / incident | Time to dx (modelled p50 / p95) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Naive: blame last change | 0% ± 0 | 0% | 0% | 40% | 0% | 0% | 0% | $0.000 | 0.8s / 0.8s |
| Naive: blame noisiest service | 20% ± 0 | 20% | 0% | 30% | 0% | 0% | 0% | $0.000 | 0.8s / 0.8s |
| Single agent (all tools) | 30% ± 0 | 40% | 30% | 40% | 0% | 100% | 0% | $0.053 | 17.9s / 27.6s |
| Multi-agent | 30% ± 0 | 40% | 30% | 40% | 0% | 100% | 0% | $0.093 | 18.6s / 22.9s |
| Multi-agent + model routing | 30% ± 0 | 40% | 30% | 40% | 0% | 100% | 0% | $0.043 | 18.6s / 22.9s |
| Multi-agent, no citation rule (ablation) | 30% ± 0 | 40% | 30% | 40% | 0% | 90% | 0% | $0.092 | 18.6s / 21.0s |
| Multi-agent + incident memory | 90% ± 0 | 90% | 90% | 60% | 0% | 100% | 100% | $0.087 | 18.8s / 22.9s |

Invalid scenarios (expected alert never fired): 0.
