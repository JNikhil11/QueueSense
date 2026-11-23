# QueueSense — Model Validation & Mathematical Rigor Report

**Project:** QueueSense — Real-Time Campus Queue Intelligence  
**Evaluator:** Antigravity Senior Engineering Organisation (Lead Architect & Data Science Lead)  
**Date:** November 24, 2026  
**Implementation Files:** `backend/shared/prediction.py`, `backend/tests/test_prediction.py`, `frontend/src/services/api.ts`  

---

## 1. Mathematical Model Formulation

QueueSense models campus dining queues using **exponential time-decay weighted nowcasting** combined with **rush-tolerant outlier filtering** and a **multi-factor evidence confidence metric**.

### 1.1 Exponential Freshness Decay
Unlike static arithmetic means or rigid sliding windows, real dining queues evolve dynamically. An observation reported 5 minutes ago carries far greater predictive weight than an observation from 45 minutes ago.

The weight $w_i$ assigned to observation $i$ with age $t_i$ (in minutes, $t_i \ge 0$) is defined by:
$$w_i = \exp\left(-\frac{t_i}{\tau}\right)$$

where:
- $\tau = 15.0$ minutes (the decay constant).
- The corresponding half-life $t_{1/2}$ is:
  $$t_{1/2} = \tau \cdot \ln(2) = 15.0 \cdot 0.693147 \approx 10.397 \text{ minutes}$$
- At $t = 10.397$ minutes, an observation's weight is exactly half ($w = 0.50$) of a report submitted just now.
- At $t = 30.0$ minutes ($2 \tau$), $w = e^{-2} \approx 0.1353$.
- Hard Boundary Cutoff: Any report with $t_i > 60.0$ minutes is completely disregarded ($w_i = 0$), preventing past meal rushes from polluting future states.

The weighted estimated wait time $\hat{W}$ and queue length $\hat{Q}$ are given by:
$$\hat{W} = \frac{\sum_{i=1}^n w_i \cdot W_i}{\sum_{i=1}^n w_i}, \quad \hat{Q} = \left\lfloor \frac{\sum_{i=1}^n w_i \cdot Q_i}{\sum_{i=1}^n w_i} + 0.5 \right\rfloor$$

---

## 2. Statistical Outlier Filtering & Meal-Rush Dynamics

### 2.1 The Small-Sample Dilemma ($N < 5$)
Standard anomaly detection techniques (such as Z-score or standard deviation) break down on small sample sizes ($N \le 4$). Furthermore, dining queues experience genuine step-function transitions: at 12:55 PM, the wait may be 4 minutes; by 1:05 PM (post-lecture rush), the wait surges to 22 minutes.

- **Design Decision:** When the number of plausible reports $N < 5$, QueueSense **does not discard valid meal-rush surges**.
- **Physical Plausibility Bounds:** Reports must satisfy $0 \le W_i \le 120$ minutes and $0 \le Q_i \le 300$ people. Impossible values (e.g. negative waits or 500-minute lines) are rejected at input validation.

### 2.2 Median Absolute Deviation (MAD) for $N \ge 5$
When $N \ge 5$, QueueSense applies Median Absolute Deviation (MAD), a robust estimator with a 50% breakdown point (unlike mean/variance, which collapse under a single corrupted observation):
$$\text{MAD} = \text{median}\left( |W_i - \text{median}(W)| \right)$$

- **Zero-Division / Identical Reports Edge Case:** If multiple students submit identical reports (e.g. four reports of 10 min), $\text{MAD} = 0$. A naive threshold ($3 \times \text{MAD}$) would drop any subsequent report differing by even 1 minute.
- **Remediation & Rush-Tolerant Floor:**
  $$\text{Cutoff Threshold} = \max(3.5 \times \text{MAD}, 25.0 \text{ minutes})$$
  This guarantees that genuine lunch/dinner surges up to 25 minutes deviation are preserved, while hostile pranks (e.g. reporting 110 minutes when the median is 5 minutes) are cleanly excluded.

### 2.3 Majority Poisoning Defense
- The theoretical breakdown point of MAD is $\approx 50\%$. If an adversary controls $>50\%$ of the active reports, statistical outlier filtering alone cannot detect the deception.
- **Upstream Layered Defense:** Majority poisoning is defended upstream by:
  1. API Gateway route-level throttling (`POST /locations/{id}/reports`: Burst 20, Rate 10).
  2. Per-IP HMAC rate limiting (5 submissions per 5 minutes per source IP).
  3. Server-authoritative UTC timestamps preventing batch backdating.

---

## 3. Evidence Confidence Scoring Formulation

QueueSense computes a composite confidence score $C \in [0.0, 1.0]$ based on three transparent factors:

$$C = \min\left(1.0, \, F_{\text{volume}} + F_{\text{recency}} + F_{\text{agreement}}\right)$$

1. **Volume Factor ($F_{\text{volume}}$, weight: 0.45):**
   $$F_{\text{volume}} = \min\left(\frac{N_{\text{recent}}}{4.0}, \, 1.0\right) \times 0.45$$
   - 1 report $\rightarrow 0.1125$
   - 2 reports $\rightarrow 0.225$
   - 3 reports $\rightarrow 0.3375$
   - 4+ reports $\rightarrow 0.450$ (maximum volume contribution)

2. **Recency Factor ($F_{\text{recency}}$, weight: 0.35):**
   $$F_{\text{recency}} = \max\left(0.0, \, 1.0 - \frac{t_{\text{newest}}}{25.0}\right) \times 0.35$$
   - Observation submitted just now ($t \approx 0$) $\rightarrow 0.350$
   - Observation from 10m ago $\rightarrow 0.210$
   - Observation from 25m+ ago $\rightarrow 0.000$

3. **Agreement Factor ($F_{\text{agreement}}$, weight: 0.20):**
   - For $N > 1$, let $\Delta = \max(W_{\text{recent}}) - \min(W_{\text{recent}})$:
     $$F_{\text{agreement}} = \max\left(0.0, \, 1.0 - \frac{\Delta}{15.0}\right) \times 0.20$$
     If reports closely agree ($\Delta \le 3$ min), $F_{\text{agreement}} \approx 0.16 - 0.20$. If reports wildly disagree ($\Delta \ge 15$ min), $F_{\text{agreement}} = 0.0$.
   - For $N = 1$, agreement cannot be measured; a neutral constant of $0.08$ is assigned.

### Confidence Ceilings & Qualitative Classification
- **Single Report Boundary:** For a single report submitted just now ($t=0$):
  $$C = 0.1125 (\text{vol}) + 0.350 (\text{rec}) + 0.080 (\text{agree}) = 0.5425 \approx 0.54$$
  If even 5 minutes elapse ($t=5$):
  $$C = 0.1125 + 0.280 + 0.080 = 0.4725 \approx 0.47$$
- **Qualitative Tiers:**
  - `HIGH`: $C \ge 0.70$ (Requires multiple agreeing fresh observations).
  - `MODERATE`: $0.40 \le C < 0.70$ (Solid baseline, single very fresh report or several aging reports).
  - `LIMITED`: $0.20 \le C < 0.40$ (Aging or sparse observation).
  - `VERY LOW` / `NO DATA`: $C < 0.20$ or 0 recent reports.

---

## 4. Cold-Start Recommendation Strategy

A recommendation engine that blindly selects an outlet based on a single unverified report creates dangerous false confidence.

- **Cold-Start Rule:** In `compute_smart_recommendation`, an outlet is **ineligible** for recommendation unless:
  1. $N_{\text{recent}} \ge 3$ observations.
  2. $t_{\text{newest}} \le 20.0$ minutes (status is `LIVE` or `RECENT`).
  3. Confidence score $C \ge 0.50$.
- **Sparse Data State:** If no campus outlet satisfies these criteria, the engine returns state `"insufficient_data"` with reason:
  `"Not enough recent queue reports across campus to make a reliable recommendation yet. At least 3 fresh observations (within 20 minutes) and 50%+ confidence are required."`
- The UI renders an amber Sparse Observation notice with an immediate CTA ("Be first to submit"), converting cold-start gaps into student participation opportunities without manufacturing false numbers.

---

## 5. Backtesting & Synthetic Validation Results

Due to the absence of continuous physical turnstile sensors in campus dining halls, algorithmic validation relies on rigorous synthetic mathematical test fixtures covering all operational regimes.

| Test Case | Scenario / Condition | Expected Mathematical Outcome | Pytest Verification |
| :--- | :--- | :--- | :---: |
| `test_freshness_weight_decay` | Observation aging from 0m to 60m | Exponential decay monotonic reduction, zero weight past 60m | **PASS** |
| `test_half_life_decay_mathematical_precision` | $t = 10.397$ min ($\tau = 15.0$) | $w = 0.5000 \pm 0.001$, wait is exact midpoint of reports | **PASS** |
| `test_outlier_filtering` | 4 normal reports (5, 6, 7, 8m) + 1 extreme (110m) | 110m cleanly rejected; estimate remains 6.5m | **PASS** |
| `test_mad_identical_reports_edge_case` | 5 identical reports (10m) + 1 valid surge (25m) | $\text{MAD} = 0$; cutoff floor 25m preserves surge; no zero-division | **PASS** |
| `test_exact_20m_submission_scenario_regression` | 3 old reports (5, 5, 6m at 18m) + 1 new (20m at 1m) | Time decay shifts prediction heavily toward fresh 20m report | **PASS** |
| `test_breakdown_point_and_majority_poisoning_defense` | 5 normal (10m) vs 6 hostile (90m) | Documents 50% MAD breakdown; upstream rate-limiting prevents 6 hostile reports from single IP | **PASS** |
| `test_empty_and_sparse_reports` | 0 reports | Null wait, null queue, UNKNOWN congestion, 0 confidence | **PASS** |
| `test_cold_start_recommendation_protection` | Outlets with only 1 or 2 reports | Returns `insufficient_data`, refuses to pick speculative winner | **PASS** |
| `test_recommendation_qualifies_with_three_reports_and_high_confidence` | Outlet with 3 fresh agreeing reports ($C \ge 0.50$) | Eligible and selected as recommended outlet | **PASS** |

---

## 6. Honest Scientific Limitations

1. **Stationarity Assumption:** QueueSense assumes queue conditions remain reasonably stationary over the 15-minute half-life window. During abrupt lecture dismissals, sudden queue spikes may lag by 2–5 minutes until a new observation is submitted.
2. **Poisson Arrival Variability:** Crowdsourced reports arrive stochastically. Between meal times (e.g. 3:00 PM – 5:00 PM), long intervals between reports are expected and accurately surfaced as `NO RECENT DATA`.
3. **Absence of Hardware Ground Truth:** University dining queues lack calibrated camera or turnstile feeds. QueueSense is an empirical nowcasting tool based on verified peer reports, not a computer-vision or machine-learning oracle.
