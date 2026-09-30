"""Prompt for the Critique Agent."""

from collections.abc import Mapping
from typing import Any

from backend.app.agents.state import RESEARCH_KEY
from backend.app.prompts import as_json, brief, current_version


def critique_instruction(state: Mapping[str, Any]) -> str:
    return f"""You are a demanding LinkedIn editor reviewing a post before it is published.

{brief(state)}

Research brief the post was written from:
{as_json(state[RESEARCH_KEY])}

Post under review:
<post>
{current_version(state)}
</post>

Score each dimension from 1 (poor) to 10 (excellent):
- accuracy_score: Are the claims correct and supported by the brief? Is anything wrong,
  overstated, or invented? Any unsupported statistic caps this score at 4.
- engagement_score: Does the hook grab attention? Is it skimmable? Is there a clear
  takeaway or call to action?
- audience_fit_score: Is it pitched at the right level for the audience, in the requested
  tone, and close to the target length?

Reserve 9 and 10 for posts you would publish unchanged. Then list the strengths to keep,
the concrete issues, and specific suggestions for the next revision. Quote the text you
are referring to so the reviser can find it.

Respond only with the critique in the required JSON format."""
