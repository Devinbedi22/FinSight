# Optional LLM for the Research Assistant

FinSight's research assistant continues to work without a language-model provider. In that mode, `/api/v1/research/ask` returns the existing deterministic findings and retrieved evidence.

## Provider contract

Phase 6E supports an OpenAI-compatible **chat completions** endpoint. The backend sends one bounded request containing the current question, up to six prior user questions, deterministic findings, structured evidence, and limitations. It has no tools, database access, or ability to retrieve more data. Provider output is an explanation plus evidence IDs; the backend checks every ID against the evidence retrieved for the current request. Invalid citations, unsupported numeric values, timeouts, rate limits, or other provider errors retain the deterministic findings.

Conversation context is held only in the `/research` page's React state and sent with the next request. It is not saved to local storage or the database. Context can help resolve a follow-up, but the backend uses it only to identify a ticker or topic; it fetches the evidence again. Prior conversation text is treated as untrusted input.

## Configuration

Set these variables in `backend/.env` (never in `frontend/.env` or a `NEXT_PUBLIC_*` variable):

```dotenv
RESEARCH_LLM_PROVIDER=openai_compatible
RESEARCH_LLM_BASE_URL=https://api.openai.com/v1
RESEARCH_LLM_MODEL=<model name enabled for your provider account>
RESEARCH_LLM_API_KEY=<your provider API key>
RESEARCH_LLM_TIMEOUT_SECONDS=25
```

The provider is disabled by default with `RESEARCH_LLM_PROVIDER=none`. A configured provider must be compatible with `POST {base_url}/chat/completions` and accept `model`, `messages`, `temperature`, and `max_tokens`. HTTPS is required except for a loopback development endpoint. FinSight does not require or ship a provider key, and a provider may charge according to its own account terms.

Restart the backend after changing the variables. `GET /api/v1/research/status` reports only a safe provider name and readiness state; it never returns the key or configured URL.

## Limits and behavior

- At most six prior questions and 24,000 characters of evidence context are sent.
- The provider call has bounded connect/read timeouts, no automatic retry, and a 700-token response cap.
- The model must cite IDs from the current evidence. Unknown or missing citation IDs cause deterministic fallback.
- Numeric claims in the model narrative must already appear in a deterministic finding. The verified findings remain separately visible in the UI.
- Missing evidence remains missing; the assistant does not fabricate a value or substitute an external source.
- Explanations are descriptive, not financial advice, causal proof, or validated forecasts.
