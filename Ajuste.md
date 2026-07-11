# Task: Evidence-Based Adjustment of Existing Nutrition Plan

## Context
I have a diet plan prescribed by a nutritionist (./Dietas/20260604_ATM.pdf). 
I have followed it strictly for 4 weeks with no visible weight loss. 
I need to loose 14kg of body fat as quickly as possible.
I want a *modified* version adjusted using only well-established, mainstream clinical nutrition science. 

## Body Composition Data (from smart scale, 4-week tracking)
| date       | weight | bmi  | body fat percentage | body water mass | fat mass | muscle mass | muscle percentage | body water | protein percentage | bone mineral percentage | skeletal muscle mass | visceral fat rating | basal metabolic rate | estimated waist to hip ratio | fat free body weight | heart rate | height |
|------------|--------|------|---------------------|-----------------|----------|-------------|-------------------|------------|--------------------|-------------------------|----------------------|---------------------|----------------------|------------------------------|----------------------|------------|--------|
| 2026-06-27 | 94.7   | 27.1 | 26.4%               | 48.4kg          | 25kg     | 65.9%       | 69.6%             | 51.1%      | 17.7%              | 4%                      | 35.2kg               | 14                  | 1876kcal             | 1.2                          | 69.7kg               | 91bpm      | 187cms |
| 2026-07-04 | 94.4   | 27   | 26.3%               | 48.6kg          | 24.8kg   | 65.8%       | 69.7%             | 51.5%      | 17.5%              | 4%                      | 35.4kg               | 14                  | 1873kcal             | 1                            | 69.6kg               | 99bpm      | 187cms |
| 2026-07-10 | 94.5   | 27   | 26.3%               | 49.2kg          | 24.9kg   | 65.8%       | 69.6%             | 52.1%      | 16.7%              | 4%                      | 36kg                 | 13                  | 1873kcal             | 0.9                          | 69.6%                | 95bpm      | 187cms |

## Strict Rules
1. **Interpret the body composition trend before recommending changes.**
   - If fat mass is down but weight/lean mass is flat or up, state clearly 
     that this is likely body recomposition, not a stall — and that 
     cutting calories further would be the wrong move.
   - If water % has shifted significantly, note that this alone can 
     explain weight-scale stagnation and is not a fat-loss issue.
   - Only treat this as a genuine plateau requiring adjustment if fat 
     mass has been flat or increased across the full 4 weeks.
   - Note explicitly that consumer bioimpedance scales have known margins 
     of error (hydration, time of day, etc.) and trends matter more than 
     single readings — do not overreact to single data points.
2. **No hallucination**: Every macro, calorie, or food change must be 
   traceable to (a) content already in the original PDF, (b) the body 
   composition data provided, or (c) a cited, reputable source (e.g., 
   peer-reviewed journals, ADA/Academy of Nutrition and Dietetics, WHO, 
   NIH/NIDDK, Mayo Clinic, UpToDate). If uncertain a recommendation is 
   well-supported, say so explicitly instead of guessing.
3. **No invented foods, supplements, or macro targets** not derived from 
   the original plan's structure, my body composition data, or a cited 
   source.
4. **Conservative adjustment only**: Any calorie deficit increase must 
   stay within generally accepted safe ranges (commonly cited as ~1% 
   of body weight per week fat loss). Do not propose aggressive or 
   rapid-loss modifications, even if the data shows a genuine plateau.
5. **Cite everything**: Include a source list at the end with a one-line 
   justification for each change.
6. **Flag non-macro explanations**: If the data or general evidence 
   suggests the real issue may be adherence, sleep, stress, or measurement 
   noise rather than the macros themselves, say so instead of just 
   cutting calories further.
7. **Explicit disclaimer**: End the output with a note that this is not 
   medical advice and should be reviewed/approved by my nutritionist 
   before I follow it.

## Output
Produce a new PDF with:
- Easy to read structure/format (meals, macros, portions)
- A short interpretation of the body composition trend (recomposition vs. 
  true plateau vs. inconclusive)
- A "Changes Made" summary table (old value → new value → reason → source)
- Source list
- Disclaimer per Rule 8
- Use a new file in the same folder called 20260710_ATM.

## Input
./Dietas/20260604_ATM.pdf