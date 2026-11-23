# QueueSense --- Design System & Visual Specification

**Project:** QueueSense  
**Art Direction:** Restrained Technical Editorial  
**Dominant Palette:** Deep Obsidian, Neon Green (`#39F58A`), Neon Blue (`#20C8FF`), Editorial Maroon (`#761D43`)  

---

## 1. Visual Philosophy & Identity

QueueSense rejects generic, low-contrast AI SaaS dashboard tropes (such as random purple gradients, gratuitous glassmorphism, floating orbs, and fabricated KPI cards). Instead, it adopts a **high-precision, student-utility design language**:
- **Clarity of Information:** High contrast between deep slate/obsidian canvases and luminescent data accents.
- **Immediate Answers:** Students walking between hostels and academic blocks must grasp the estimated wait within 500 milliseconds.
- **Evidence-First Visual Hierarchy:** Wait figures take typographic priority; supporting evidence (confidence bars, report counts, freshness pills) follows immediately beneath.
- **Iconography:** Lucide React icons exclusively. No emoji iconography.

---

## 2. Color Palette & Tokens

### 2.1 Accent Colors
- **Neon Green (`#39F58A`):** Indicates low congestion, fresh/live data status, and primary positive actions ("Report Queue", "View Outlet").
- **Neon Blue (`#20C8FF`):** Indicates moderate queue states, secondary interactive controls, and statistical evidence indicators.
- **Restrained Maroon / Rose (`#761D43` / `#F43F5E`):** Reserved strictly for critical bottlenecks, heavy congestion (>15m wait), and validation warnings.

### 2.2 Surface Architecture
```css
--surface-base:     #0B0F17; /* Deepest background obsidian canvas */
--surface-card:     #121824; /* Primary outlet and recommendation cards */
--surface-elevated: #1A2234; /* Interactive buttons, input fields, modals */
--surface-border:   #232E44; /* Crisp architectural divider borders */
--surface-subtle:   #2E3D5B; /* Hover highlight borders */
```

### 2.3 Status Color Matrix
| Status | Background | Border | Text | Icon State |
| :--- | :--- | :--- | :--- | :--- |
| **LIVE (<7m)** | `rgba(57, 245, 138, 0.10)` | `#39F58A` (30%) | `#39F58A` | Green pulsing dot |
| **RECENT (<20m)** | `rgba(32, 200, 255, 0.10)` | `#20C8FF` (30%) | `#20C8FF` | Solid cyan badge |
| **STALE (<60m)** | `rgba(245, 158, 11, 0.10)` | `#F59E0B` (30%) | `#F59E0B` | Amber warning pill |
| **NO RECENT DATA** | `#1E293B` | `#334155` | `#94A3B8` | Muted slate border |

---

## 3. Typography System

### 3.1 Headline / Display Typography: **Space Grotesk**
- Geometric, modern sans-serif with subtle technological quirks.
- Used for page titles, hero headings, and modal titles.
- Weights: 600 (Semi-bold), 700 (Bold).

### 3.2 UI & Body Typography: **Inter**
- High-legibility humanist sans-serif optimized for mobile screens and dense UI controls.
- Weights: 400 (Regular), 500 (Medium), 600 (Semi-bold).

### 3.3 Data & Figures Typography: **IBM Plex Mono**
- Tabular figures (`tnum` font feature enabled) ensure numbers align vertically.
- Used for wait-time values, queue counts, timestamps, and report IDs.
- Weights: 500 (Medium), 700 (Bold).

---

## 4. Responsive Breakpoints & Mobile Optimization

- **Small Mobile (360px – 480px):** Single-column vertical stream, sticky header, full-width touch-friendly report sliders.
- **Tablet (768px – 1024px):** Two-column card grid, expanded recommendation card with side-by-side evidence metrics.
- **Desktop (1024px – 1440px):** Three-column card grid, comprehensive hero metrics ribbon, modal audit trays.

