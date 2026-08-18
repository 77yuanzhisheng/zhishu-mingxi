"""Domain exceptions exposed by the chat service."""


class ChatUserNotFoundError(LookupError):
    pass


class ChatSessionNotFoundError(LookupError):
    pass


class ChatSessionAccessError(PermissionError):
    pass


class LLMUnavailableError(RuntimeError):
    pass
