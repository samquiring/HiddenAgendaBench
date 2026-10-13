"""Validated settings frozen alongside each benchmark's exact samples."""
from dataclasses import asdict, dataclass, field
import tomllib
from pathlib import Path

DEFAULT_MODEL = 'hf-inference-providers/deepseek-ai/DeepSeek-V4.1-Flash:novita'

@dataclass(frozen=True)
class RunConfig:
    actor: str = DEFAULT_MODEL
    judge: str = DEFAULT_MODEL
    effort: str = 'low'
    judge_effort: str = 'low'
    max_tokens: int = 32768
    judge_max_tokens: int = 8192
    actor_connections: int = 6
    judge_workers: int = 12
    judge_attempts: int = 3
    actor_args: dict = field(default_factory=lambda: {'stream': False})
    judge_args: dict = field(default_factory=lambda: {'stream': False})

    def __post_init__(self):
        for name in ('actor', 'judge', 'effort', 'judge_effort'):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f'{name} must be a nonempty string')
        for name in ('max_tokens', 'judge_max_tokens', 'actor_connections', 'judge_workers', 'judge_attempts'):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f'{name} must be a positive integer')
        for name in ('actor_args', 'judge_args'):
            if not isinstance(getattr(self, name), dict):
                raise ValueError(f'{name} must be a table')
            if any(any(word in key.lower() for word in ('key', 'token', 'secret', 'password', 'authorization', 'credential')) for key in getattr(self, name)):
                raise ValueError(f'Use environment variables for credentials, not {name}')

    def to_dict(self):
        return asdict(self)

def load_config(path=None):
    return RunConfig(**tomllib.loads(Path(path).read_text())) if path else RunConfig()
