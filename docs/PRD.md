# QueueSense --- Product Requirements Document (PRD)

**Project:** QueueSense --- Real-Time Campus Food Queue Intelligence  
**Owner:** J Nikhil (`JNikhil11`)  
**Challenge:** Techfest, IIT Bombay × AWS ShipIt Challenge  
**Target AWS Region:** `ap-southeast-2` (Sydney)  
**Version:** 1.0.0 (Production Release)  

---

## 1. Executive Summary & Problem Statement

### 1.1 The Campus Problem
At university campuses (such as VIT-AP University), thousands of students congregate around dining halls (messes) and food courts (canteens) during short meal intervals (12:00 PM – 2:00 PM and 7:00 PM – 9:00 PM). Students walk across campus without knowing whether an outlet has a 2-minute line or a 25-minute bottleneck. This leads to wasted time, overcrowding, dining hall congestion, and mealtime frustration.

### 1.2 The Solution
**QueueSense** is a lightweight, mobile-first campus food-queue intelligence system powered by AWS serverless technologies. It collects crowdsourced queue observations from students, applies mathematical time-decay weighting and outlier rejection, provides transparent confidence scores, and computes real-time recommendations to redirect foot traffic to less crowded outlets.

**Tagline:** *Know the queue before you join it.*

---

## 2. Product Principles & Non-Negotiables

1. **Evidence Before Confidence:** Every estimate explicitly displays its age and the volume of supporting reports. A guess is never dressed as a live fact.
2. **Honest States:** The UI strictly differentiates between `LIVE` (<7m), `RECENT` (<20m), `STALE` (<60m), `NO RECENT DATA` (>60m or 0 reports), and `DEMO` data.
3. **Useful Under Sparse Data:** When observations are sparse or stale, the recommendation engine refuses to manufacture a false winner, explaining clearly that data is insufficient.
4. **Zero Personal Data (Privacy by Design):** No student names, registration IDs, phone numbers, or exact geolocation coordinates are required or stored.
5. **Low Friction Reporting:** Submitting an observation takes less than 5 seconds using intuitive presets.
6. **Mobile-First Experience:** Built for students checking status while walking between hostels and lecture blocks.

---

## 3. User Personas & Core Journeys

### 3.1 Student User
- **View Congestion:** Inspect estimated wait times and queue lengths across all campus dining halls and canteens.
- **Inspect Evidence:** See when the estimate was last updated and how many peer reports support it.
- **Receive Recommendation:** Discover the lowest-wait active outlet that meets confidence thresholds.
- **Submit Observation:** Report wait time in minutes and queue size with optional counter notes.
- **Filter & Search:** Filter by Messes vs Canteens and search specific outlets.

### 3.2 Operations / Admin User
- **Campus Activity Feed:** Inspect chronological feed of all incoming reports across campus.
- **Outlier Visibility:** Audit reports flagged by the statistical outlier rejection engine.
- **Outlet Status:** Verify reporting volume and operational status.

---

## 4. Feature Specifications

### 4.1 Campus Food Outlets
The release covers 5 core dining locations at VIT-AP University:
1. `Central Mess A (North Dining)`: 450 capacity multi-counter dining hall.
2. `South Mess B (Annex Dining)`: 350 capacity dining hall with dedicated veg counters.
3. `Rock Plaza Food Court`: 180 capacity open-air plaza.
4. `CB Academic Bistro`: 120 capacity fast-counter canteen.
5. `Midnight Fuel Canteen`: 150 capacity evening cafeteria.

### 4.2 Recommendation Algorithm
- Evaluates active outlets.
- Disqualifies outlets with `STALE` or `NO RECENT DATA` status, or confidence < 0.25.
- Selects the outlet with the minimum predicted wait time.
- Emits plain-language explanation: *"Shortest estimated wait (~4.5 min) with high evidence; verified by 3 reports updated 2m ago."*

### 4.3 Data Quality & Bounds
- Reported wait time: integer/float [0, 120] minutes.
- Queue length: integer [0, 300] people.
- Note: string [0, 140] chars, stripped of control characters and HTML tags.
- Report ID and timestamp: generated exclusively server-side.

