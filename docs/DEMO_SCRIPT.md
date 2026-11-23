# QueueSense --- 90-Second Demonstration Script

**Event:** Techfest, IIT Bombay × AWS ShipIt Challenge  
**Project:** QueueSense --- Real-Time Campus Food Queue Intelligence  
**Presenter:** J Nikhil (`JNikhil11`)  

---

## 1. Demo Narrative Breakdown (0:00 – 1:30)

| Timestamp | Screen / Visual Focus | Spoken Script | Key Action |
| :--- | :--- | :--- | :--- |
| **0:00 – 0:15** | Dashboard Hero & Tagline | *"Every day at university dining halls, thousands of students walk across campus completely blind to queue lengths. They get stuck in unexpected 25-minute bottlenecks. This is QueueSense: real-time campus queue intelligence powered by AWS serverless architecture."* | Show Hero title *"Skip the wait. Find your next meal."* and live campus metrics strip. |
| **0:15 – 0:30** | Smart Recommendation Banner & Evidence | *"Right here on the first screen, QueueSense answers the student's core question: Where should I eat right now? South Mess B is recommended with a 5-minute wait based on 2 concurring reports updated 2 minutes ago. Notice how our algorithm explicitly displays evidence quality instead of pretending to have 100% predictive certainty."* | Point out the Evidence Quality bar (High), recency indicator (2m ago), and plain-language explanation. |
| **0:30 – 0:45** | Outlet Card Congestion & Filtering | *"Students can filter between central messes and quick canteens. For each dining outlet, we display the calculated wait time, queue length, and freshness status: LIVE, RECENT, or aging data. If an outlet hasn't received a report in over 60 minutes, QueueSense honestly marks it as 'No Recent Data' rather than making up a number."* | Click 'Messes' tab, filter by 'Shortest Wait', highlight freshness pill with green pulse. |
| **0:45 – 1:05** | Reporting Flow & Instant Recalculation | *"Contributing is frictionless. While standing in line, a student clicks 'Report Queue', taps '12 minutes' with 15 people ahead, adds a quick note like 'Counters 1 & 2 open', and submits. On the backend, AWS Lambda receives the report, generates a server-side timestamp, writes to DynamoDB, recalculates the exponential decay weight and outlier filters, and updates the estimate immediately."* | Open Report Modal, tap 12m preset, submit, and show instant toast + updated estimate. |
| **1:05 – 1:20** | Outlet Detail & Admin Audit Log | *"Clicking any outlet reveals the full observation history and statistical spread. We also built a read-only campus audit feed for dining administrators to monitor traffic flows and review statistical outliers without collecting any student personal data."* | Open Outlet Detail view showing timeline; open Admin Audit Feed showing raw records. |
| **1:20 – 1:30** | AWS Architecture & Closing | *"Under the hood, QueueSense runs on API Gateway HTTP API, Python Lambda functions, and DynamoDB single-table storage—built 100% within the AWS Free Tier using AWS SAM. QueueSense: Know the queue before you join it."* | Briefly show Architecture diagram and conclusion. |

---

## 2. Judge Q&A Talking Points

- **Q: How do you prevent students from submitting fake queue times?**  
  *A:* "QueueSense implements Median Absolute Deviation (MAD) outlier rejection. If a user submits an extreme 90-minute wait while the median is 8 minutes, the algorithm flags it as a statistical outlier, logs it in the audit feed, and excludes it from the public estimate."

- **Q: What happens during slow hours when no one has reported?**  
  *A:* "QueueSense has an honest staleness policy. Reports older than 60 minutes decay to zero weight. The UI transitions to 'No Recent Data' and clearly explains that new observations are needed rather than hallucinating an estimate."

- **Q: Why AWS Serverless?**  
  *A:* "Campus food queues have extreme burst patterns—zero traffic during lecture hours, and massive spikes at 12:30 PM. Serverless Lambda and DynamoDB on-demand billing scale up instantaneously during rush hours and cost zero dollars when students are in class."

