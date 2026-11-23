# QueueSense --- Queue Intelligence & Mathematical Estimation Model

**Project:** QueueSense  
**Author:** J Nikhil (`JNikhil11`)  
**Architecture:** Pure Python / TypeScript Deterministic Algorithm (No black-box hallucinations)  

---

## 1. Core Mathematical Philosophy

QueueSense rejects marketing buzzwords such as "predictive AI" when applied to simple heuristics. Instead, it employs a **rigorous, deterministic statistical time-decay model** designed specifically for real-world campus food queues. Campus queues are characterized by:
- **Rapid fluctuations:** A queue can surge by 30 people in 5 minutes at the ringing of a class bell, and clear out 10 minutes later.
- **Sparse data:** In the early morning or mid-afternoon, only 1 or 2 observations may exist.
- **Disagreement & noise:** Human perception of time varies widely (one student may report 5 minutes while another reports 12 minutes for the same line).

---

## 2. Mathematical Formulation

### 2.1 Exponential Freshness Decay
Given a report $i$ submitted at timestamp $T_i$, its age in minutes relative to the current time $T_{\text{now}}$ is:
$$t_i = \max\left(0, \frac{T_{\text{now}} - T_i}{60}\right)$$

The time-decay weight $w_i$ decays exponentially according to:
$$w_i(t_i) = \begin{cases} \exp\left(-\frac{t_i}{\tau}\right) & \text{if } 0 \le t_i \le t_{\max} \\ 0 & \text{if } t_i > t_{\max} \end{cases}$$

- **Decay Constant ($\tau$):** Configured to **15.0 minutes**. At $t = 15$m, a report retains $e^{-1} \approx 36.8\%$ of its initial weight. At $t = 30$m, it retains $e^{-2} \approx 13.5\%$.
- **Hard Horizon ($t_{\max}$):** Configured to **60.0 minutes**. Observations older than 1 hour are strictly disregarded.

### 2.2 Statistical Outlier Filtering: Median Absolute Deviation (MAD)
Before calculating the weighted mean, incoming reports are screened to prevent accidental or malicious distortion.
1. **Plausibility Hard Bounds:**
   - Wait time $q_i \in [0, 120]$ minutes.
   - Queue length $L_i \in [0, 300]$ people.
2. **Median Absolute Deviation (for $N \ge 3$ reports):**
   $$\tilde{q} = \text{median}(\{q_i\})$$
   $$\text{MAD} = \text{median}\left(\{|q_i - \tilde{q}|\}\right)$$
   $$\text{Threshold} = 3.0 \times \max(\text{MAD}, 4.0\text{ min})$$
   Any report satisfying $|q_i - \tilde{q}| > \text{Threshold}$ is classified as an outlier, logged for administrator audit, and excluded from the public estimate.

### 2.3 Time-Weighted Estimators
The predicted wait time $\hat{Q}$ and predicted queue length $\hat{L}$ are computed as:
$$\hat{Q} = \frac{\sum_{i=1}^N w_i \cdot q_i}{\sum_{i=1}^N w_i}, \quad \hat{L} = \text{round}\left(\frac{\sum_{i=1}^N w_i \cdot L_i}{\sum_{i=1}^N w_i}\right)$$

### 2.4 Congestion Classification
Wait times map to human-friendly operational categories:
- **LOW:** $\hat{Q} < 3.5\text{ min}$
- **MODERATE:** $3.5\text{ min} \le \hat{Q} < 8.5\text{ min}$
- **HIGH:** $8.5\text{ min} \le \hat{Q} < 15.5\text{ min}$
- **VERY HIGH:** $\hat{Q} \ge 15.5\text{ min}$

---

## 3. Evidence & Confidence Scoring

Rather than asserting false claims (such as "99% accuracy"), QueueSense computes an **Evidence Quality Index ($C \in [0.0, 1.0]$)** derived from three physical factors:

$$C = \min\left(1.0, S_{\text{vol}} + S_{\text{rec}} + S_{\text{agr}}\right)$$

1. **Volume Score ($S_{\text{vol}} \le 0.45$):**
   $$S_{\text{vol}} = \min\left(\frac{N_{\text{recent}}}{4}, 1.0\right) \times 0.45$$
2. **Recency Score ($S_{\text{rec}} \le 0.35$):**
   $$S_{\text{rec}} = \max\left(0, 1.0 - \frac{t_{\min}}{25.0}\right) \times 0.35$$
3. **Agreement Score ($S_{\text{agr}} \le 0.20$):**
   $$\Delta_{\text{spread}} = \max(q_i) - \min(q_i)$$
   $$S_{\text{agr}} = \begin{cases} \max\left(0, 1.0 - \frac{\Delta_{\text{spread}}}{15.0}\right) \times 0.20 & \text{if } N \ge 2 \\ 0.08 & \text{if } N = 1 \end{cases}$$

### Confidence Tiers
- **HIGH:** $C \ge 0.70$ (Multiple concurring reports within last 5 minutes)
- **MODERATE:** $0.40 \le C < 0.70$ (Recent observations with reasonable agreement)
- **LIMITED:** $0.20 \le C < 0.40$ (Single report or aging observation)
- **VERY LOW / NO DATA:** $C < 0.20$ (Data sparse or obsolete)

---

## 4. Defensible Recommendation Engine

The recommendation system follows an explicit safety protocol:
1. **Filter Active Outlets:** Must be marked `active: true`.
2. **Freshness Filter:** Must have `LIVE` or `RECENT` status (latest report $\le 20$m old). Outlets with `STALE` or `NO RECENT DATA` are disqualified.
3. **Confidence Threshold:** Must have $C \ge 0.25$.
4. **Ranking:** Sort remaining candidates by lowest $\hat{Q}$, breaking ties by highest confidence $C$.
5. **Honest Fallback:** If zero outlets qualify, the engine returns `isEligible: false` with the user-facing explanation:
   > *"Not enough recent queue reports across campus to make a reliable recommendation yet."*
