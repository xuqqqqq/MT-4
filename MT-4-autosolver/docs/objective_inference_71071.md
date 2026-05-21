# Objective Inference Report

Records: `10`

## Raw Proxy Error

| proxy | MAE | RMSE | bias local-online | Pearson |
|---|---:|---:|---:|---:|
| seq_penalty | 91.276 | 136.252 | -27.951 | 0.978 |
| prop_penalty | 91.305 | 131.410 | 20.211 | 0.974 |
| subset_mean_penalty | 91.573 | 131.449 | 20.683 | 0.975 |
| uniform_penalty | 91.787 | 131.197 | 18.650 | 0.973 |
| best_score_penalty | 127.846 | 192.619 | -86.441 | 0.966 |

## Affine Calibration

| proxy | formula | train MAE | LOO MAE |
|---|---|---:|---:|
| seq_penalty | online ~= 1.1954 * proxy + -105.43 | 87.821 | 123.566 |
| subset_mean_penalty | online ~= 1.1428 * proxy + -125.11 | 92.112 | 130.621 |
| prop_penalty | online ~= 1.1395 * proxy + -122.21 | 92.945 | 131.889 |
| uniform_penalty | online ~= 1.1268 * proxy + -111.17 | 94.835 | 135.403 |
| best_score_penalty | online ~= 1.2895 * proxy + -94.31 | 105.405 | 151.711 |

## Linear Blends

| model | columns | train MAE | LOO MAE |
|---|---|---:|---:|
| prop_seq_uniform | prop_penalty, seq_penalty, uniform_penalty | 55.185 | 118.377 |
| seq_penalty_affine | seq_penalty | 87.821 | 123.566 |
| subset_mean_penalty_affine | subset_mean_penalty | 92.112 | 130.621 |
| prop_penalty_affine | prop_penalty | 92.945 | 131.889 |
| uniform_penalty_affine | uniform_penalty | 94.835 | 135.403 |
| prop_uniform | prop_penalty, uniform_penalty | 92.100 | 150.474 |
| prop_subset_mean | prop_penalty, subset_mean_penalty | 93.627 | 151.295 |
| best_score_penalty_affine | best_score_penalty | 105.405 | 151.711 |
| all_expected_proxies | prop_penalty, seq_penalty, uniform_penalty, subset_mean_penalty, best_score_penalty | 44.489 | 239.131 |

