"""
Null UI for non-interactive usage (server/electron).
All methods are no-ops to avoid terminal output.
"""


class NullUI:
    """No-op UI implementation."""

    def show_banner(self):
        pass

    def print_agent(self, message: str, end: str = "\n"):
        pass

    def print_agent_prefix(self):
        pass

    def print_stream(self, chunk: str):
        pass

    def print_newline(self):
        pass

    def print_error(self, message: str):
        pass

    def print_warning(self, message: str):
        pass

    def print_info(self, message: str):
        pass

    def get_user_input(self) -> str:
        raise RuntimeError("NullUI does not support interactive input.")

    def print_goodbye(self):
        pass
