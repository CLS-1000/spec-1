SIGNAL RECORD:
Source: {signal_source} (credibility: {source_credibility})
Signal text: {signal_text}
Published: {published_at}
URL: {signal_url}
Gates fired: {gate_results}
Composite score: {opportunity_score}
Priority: {opportunity_priority}

INVESTIGATION:
Hypothesis: {hypothesis}
Research queries: {queries}
Analyst leads: {analyst_leads}

VERIFICATION:
Classification: {classification}
Confidence: {confidence}
Reasoning: {verification_reasoning}

PATTERN:
{pattern}
Domain: {domain}

Produce the Lead Intelligence Packet as a complete printed document.
Use this exact format:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

L E A D   I N T E L L I G E N C E   P A C K E T
SPEC-1 · {date} · LEAD-{lead_number}
SOURCE: {signal_source_upper} · CONF: {confidence} · CLASS: {classification}
MODULE: {recommended_module}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

S I G N A L

[One paragraph. What SPEC-1 detected. Specific. Named. The exact observation
from the scored signal — not paraphrased, not softened. Cite the source,
the date, and the confidence score inline. State which gate fired hardest
and why that matters.]

P A T T E R N   A N A L Y S I S

[What this signal means structurally. Name the mechanism.
Not "this may indicate" — state what it indicates and why.
Reference prior patterns from the same source or domain if relevant.
One paragraph per mechanism. Maximum three mechanisms.]

  M E C H A N I S M   O N E — [NAME IT]
  [How this channel works. What the leverage position is.
   What a test of this mechanism would look like.]

  M E C H A N I S M   T W O — [NAME IT]
  [Same structure. Testable claim.]

  M E C H A N I S M   T H R E E — [NAME IT — if applicable]
  [Same structure. Testable claim.]

A C T O R   M A P

[Named actors relevant to this signal. For each:]
▸ [Name / Entity]: [Role] · [Credibility or known track record] · [Current position]

[If actors are unnamed: state that explicitly and explain what the
anonymity itself signals about the sourcing or the story.]

W H A T   I S   A L R E A D Y   K N O W N

[Prior reporting, prior signals, established facts that give this signal
its context. This is not background — it is the foundation the analyst
needs to evaluate what is new vs what is noise.]

W H A T   I S   S T I L L   U N K N O W N

[The specific gaps. Not generic uncertainty. Named unknowns:
what document has not been released, what actor has not spoken,
what data point would resolve the ambiguity.]

E V I D E N C E   C H E C K L I S T

[Specific documents and data that exist and can be pulled:]
▪ [Document type] — [where it lives, how to request it]
▪ [Document type] — [where it lives, how to request it]
▪ [Document type] — [where it lives, how to request it]
▪ [Document type] — [where it lives, how to request it]
▪ [Document type] — [where it lives, how to request it]

T H R E E   Q U E S T I O N S

[Not rhetorical. Addressed to named institutions. Answerable with
specific documents or on-record statements. The Psyche-Ops standard.]

1. [Named institution]: [Specific factual question that demands a
   documentable answer — not an opinion, not a characterization.]

2. [Named institution]: [Specific factual question.]

3. [Named institution]: [Specific factual question.]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

F E E D   P R O M P T
// Run this after collecting source data. Paste into Claude with your material.
// This prompt loads context. Claude will produce original fact-based reporting.

"You are a senior intelligence analyst. Here is what you know before
reading the source data:

[2-3 sentences of the most critical context from the packet above —
the mechanism, the actors, the leverage position. Dense. Specific.]

Here is the source data I have collected: [ANALYST PASTES DATA HERE]

Produce a fact-based intelligence report on [specific named topic].
Treat [specific anomaly or pattern from the signal] as the central finding.
Name the mechanism. State the leverage position. Identify what the data
confirms, what it contradicts, and what it cannot yet resolve.
Surface any patterns in the data that were not anticipated by the hypothesis.
Do not summarize the source material — analyze it.
Take a position on what the data means. Earn it."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ROUTING
Module: {recommended_module}
Adapter: {recommended_adapter}
Lens: {investigative_lens}
Window: {freshness_window}
Confidence: {confidence_label}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPEC-1 // EVASTARARCANA · Portland OR
CLASSIFICATION: UNCLASSIFIED // LEAD-{lead_number} // {date}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
