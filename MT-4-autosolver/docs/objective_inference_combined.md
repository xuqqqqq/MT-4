# Objective Inference Report

Records: `30`

## Raw Proxy Error

| proxy | MAE | RMSE | bias local-online | Pearson |
|---|---:|---:|---:|---:|
| uniform_penalty | 85.517 | 124.338 | -22.876 | 0.979 |
| prop_penalty | 85.792 | 126.070 | -22.013 | 0.978 |
| subset_mean_penalty | 91.573 | 131.449 | 20.683 | 0.975 |
| seq_penalty | 96.106 | 142.307 | -58.373 | 0.977 |
| best_score_penalty | 130.325 | 196.980 | -104.985 | 0.961 |

## Affine Calibration

| proxy | formula | train MAE | LOO MAE |
|---|---|---:|---:|
| uniform_penalty | online ~= 1.1490 * proxy + -80.02 | 79.777 | 87.387 |
| prop_penalty | online ~= 1.1534 * proxy + -84.07 | 80.119 | 87.665 |
| seq_penalty | online ~= 1.1725 * proxy + -54.61 | 81.202 | 89.017 |
| best_score_penalty | online ~= 1.2246 * proxy + -31.68 | 104.251 | 115.131 |
| subset_mean_penalty | online ~= 1.1428 * proxy + -125.11 | 92.112 | 130.621 |

## Linear Blends

| model | columns | train MAE | LOO MAE |
|---|---|---:|---:|
| uniform_penalty_affine | uniform_penalty | 79.777 | 87.387 |
| prop_penalty_affine | prop_penalty | 80.119 | 87.665 |
| seq_penalty_affine | seq_penalty | 81.202 | 89.017 |
| prop_uniform | prop_penalty, uniform_penalty | 79.385 | 92.878 |
| prop_seq_uniform | prop_penalty, seq_penalty, uniform_penalty | 80.074 | 98.291 |
| best_score_penalty_affine | best_score_penalty | 104.251 | 115.131 |
| subset_mean_penalty_affine | subset_mean_penalty | 92.112 | 130.621 |
| prop_subset_mean | prop_penalty, subset_mean_penalty | 93.627 | 151.295 |
| all_expected_proxies | prop_penalty, seq_penalty, uniform_penalty, subset_mean_penalty, best_score_penalty | 44.489 | 239.131 |

