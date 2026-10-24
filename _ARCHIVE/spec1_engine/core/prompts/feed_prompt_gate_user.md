Evaluate this feed prompt against the five quality criteria:

FEED PROMPT TO EVALUATE:
{feed_prompt}

SIGNAL CONTEXT:
Source: {signal_source}
Pattern: {pattern}
Classification: {classification}
Confidence: {confidence}
Hypothesis: {hypothesis}

FIVE QUALITY CRITERIA — all must pass:

1. NAMES A SPECIFIC ANOMALY OR PATTERN
   The prompt must reference the specific finding from this signal —
   not a generic topic. "Analyze this document" fails.
   "Treat the 3x committee acceleration velocity as the central finding" passes.

2. SPECIFIES A MODULE OR INVESTIGATIVE LENS
   The prompt must name what kind of analysis to produce:
   donor network, legislative trajectory, conflict pattern,
   supply chain disruption, influence operation, etc.

3. DIRECTS ANALYSIS NOT SUMMARY
   The prompt must explicitly instruct Claude to analyze and take a position —
   not summarize, not rewrite, not describe.

4. INCLUDES COMPRESSED CONTEXT LOAD
   The prompt must contain 1-2 sentences of expert context so Claude
   is not starting cold. The analyst's source data alone is not enough.

5. PRODUCES ORIGINAL REPORTING
   The prompt must be specific enough that two analysts with different
   source data would get meaningfully different outputs.
   Generic prompts that produce the same output regardless of input fail.

Return JSON: {"pass": bool, "failures": [str], "rewrite": str | null}
