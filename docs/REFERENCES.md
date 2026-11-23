# QueueSense --- Technical References & Design Inspirations

**Project:** QueueSense  
**Challenge:** Techfest, IIT Bombay × AWS ShipIt Challenge  
**Author:** J Nikhil (`JNikhil11`)  

---

## 1. Challenge & Domain Context

- **Event:** Techfest, IIT Bombay × AWS ShipIt Challenge 2026.
- **Problem Statement:** Solve a tangible, real-world campus operational challenge using AWS serverless cloud infrastructure and Free Tier services.
- **Campus Target:** IIT Bombay student messes and canteens.

---

## 2. Technical Documentation & AWS Resources

- **AWS SAM (Serverless Application Model):**
  - Specification & Resource Types: [AWS SAM Template Specification](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-specification.html)
  - HTTP API Gateway v2 integration: [AWS::Serverless::HttpApi](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-httpapi.html)
- **Amazon DynamoDB Single-Table Design:**
  - Alex DeBrie, *The DynamoDB Book* access pattern modeling.
  - AWS Documentation: [Single-Table Design with DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-modeling-nosql-B.html)
- **Time-Series Weighting & Median Absolute Deviation:**
  - Rousseeuw, P. J., & Croux, C. (1993). *Alternatives to the Median Absolute Deviation*. Journal of the American Statistical Association.
  - Exponential decay weighting in time-series estimation ($w = e^{-t/\tau}$).

---

## 3. Open Source Packages & Libraries

| Package | Version | Purpose | License |
| :--- | :--- | :--- | :--- |
| **React** | 18.3.1 | Core UI component framework | MIT |
| **Vite** | 5.4.11 | Fast frontend tooling & bundler | MIT |
| **Tailwind CSS** | 3.4.17 | Utility-first CSS styling engine | MIT |
| **Lucide React** | 0.474.0 | Clean, accessible vector icons | ISC |
| **Vitest** | 2.1.8 | Fast unit test runner | MIT |
| **Boto3** | 1.34+ | Official AWS SDK for Python | Apache 2.0 |
| **Pytest** | 9.2.0 | Python test framework | MIT |
| **Python** | 3.12 | Serverless backend runtime | PSF License |

---

## 4. Design & Interaction Inspirations

- **Linear & Raycast:** Restrained technical palettes, monospace metrics, micro-interaction feedback.
- **FlightAware & Citymapper:** Real-time freshness indicators (`LIVE` vs `RECENT`), explicit data staleness disclaimers.
- **Google Maps Popular Times:** Transparent congestion bands (`LOW`, `MODERATE`, `HIGH`, `VERY HIGH`) without false precision.

