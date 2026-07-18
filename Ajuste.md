# Task: Evidence-Based Adjustment of Existing Nutrition Plan

## Context
I have a diet plan prescribed by a nutritionist (./Dietas/20260604_ATM.pdf). 
I have followed it strictly for 4 weeks with no visible weight loss. 
I need to loose 14kg of body fat as quickly as possible.
I got a *modified* version adjusted using only well-established, mainstream clinical nutrition science, but still are ot seeing any change. I need a seccond modification to ensure I lose fat.


## Body Composition Data (from smart scale, 4-week tracking)
| date       | weight | bmi  | body fat percentage | body water mass | fat mass | muscle mass | muscle percentage | body water | protein percentage | bone mineral percentage | skeletal muscle mass | visceral fat rating | basal metabolic rate | estimated waist to hip ratio | fat free body weight | heart rate | height |
|------------|--------|------|---------------------|-----------------|----------|-------------|-------------------|------------|--------------------|-------------------------|----------------------|---------------------|----------------------|------------------------------|----------------------|------------|--------|
| 2026-06-27 | 94.7   | 27.1 | 26.4%               | 48.4kg          | 25kg     | 65.9kg       | 69.6%             | 51.1%      | 17.7%              | 4%                      | 35.2kg               | 14                  | 1876kcal             | 1.2                          | 69.7kg               | 91bpm      | 187cms |
| 2026-07-04 | 94.4   | 27   | 26.3%               | 48.6kg          | 24.8kg   | 65.8kg       | 69.7%             | 51.5%      | 17.5%              | 4%                      | 35.4kg               | 14                  | 1873kcal             | 1                            | 69.6kg               | 99bpm      | 187cms |
| 2026-07-10 | 94.5   | 27   | 26.3%               | 49.2kg          | 24.9kg   | 65.8kg       | 69.6%             | 52.1%      | 16.7%              | 4%                      | 36kg                 | 13                  | 1873kcal             | 0.9                          | 69.6kg                | 95bpm      | 187cms |
| 2026-07-17 | 94.6   | 27.1   | 26.3%               | 49.3kg          | 24.9kg   | 65.8kg       | 69.7%             | 52.1%      | 16.7%              | 4%                      | 36.1kg                 | 13                  | 1876kcal             | 0.9                          | 69.6kg                | 99bpm      | 187cms |

## Strict Rules
1. **Interpret the body composition trend before recommending changes.**
   - Look for reputable current medical and scientific sources to shed light into the data.
2. **No hallucination**: Every macro, calorie, or food change must be 
   traceable to (a) content already in the original PDF, (b) the body 
   composition data provided, or (c) a cited, reputable source (e.g., 
   peer-reviewed journals, ADA/Academy of Nutrition and Dietetics, WHO, 
   NIH/NIDDK, Mayo Clinic, UpToDate). If uncertain a recommendation is 
   well-supported, say so explicitly instead of guessing.
3. **No invented foods, supplements, or macro targets** not derived from 
   the original plan's structure, my body composition data, or a cited 
   source.
4. **Cite everything**: Include a source list at the end with a one-line 
   justification for each change.
5. **Flag non-macro explanations**: If the data or general evidence 
   suggests the real issue may be adherence, sleep, stress, or measurement 
   noise rather than the macros themselves, say so instead of just 
   cutting calories further.
6. **Explicit disclaimer**: End the output with a note that this is not 
   medical advice and should be reviewed/approved by my nutritionist 
   before I follow it.

## Output
Produce a new PDF with:
- Easy to read and brief structure/format (meals, macros, portions)
- A very short interpretation of the body composition trend (recomposition vs. 
  true plateau vs. inconclusive)
- A "Changes Made" summary table (old value → new value → reason → source)
- Source list
- Disclaimer per Rule 8
- Use a new file in the same folder called 20260710_ATM.

## Input
./Dietas/20260604_ATM.pdf
./Dietas/20260710_ATM.pdf