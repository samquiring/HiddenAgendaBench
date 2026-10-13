# Framework decision

Use Inspect AI directly, with its OpenRouter adapter (or LiteLLM proxy adapter). Python task definitions reuse datasets, generate solvers, provider adapters, retries, epochs, logs, token accounting and the log viewer. Custom code implements only our experimental protocol, fixture generation, deterministic grading, redaction and offline monitoring/analysis.

Sources reviewed:

- [Inspect task structure](https://inspect.aisi.org.uk/tasks.html)
- [Inspect providers: OpenRouter and LiteLLM Proxy](https://inspect.aisi.org.uk/providers.html)
- [Inspect reasoning channels and budgets](https://inspect.aisi.org.uk/reasoning.html)
- [ControlArena](https://github.com/UKGovernmentBEIS/control-arena): an Inspect-based foundation for control protocols/settings. Appropriate if we add tool environments or intervention policies; unnecessary abstraction for one actor response and offline monitors.
- [SHADE-Arena public split](https://github.com/jkutaso/SHADE-Arena): relevant precedent for primary/side-task evaluation and monitoring, but its AgentDojo tool environments are not our tool-free computation setup. No task data or code copied.

This choice preserves a migration route to ControlArena while avoiding a new model client, scheduler or evaluation-log format. Judge requests also use Inspect's model abstraction. Python is the only implementation language.
