from abc import ABC, abstractmethod


class FunctionReader(ABC):
    @abstractmethod
    def load_functions(self, source: str): ...

    @abstractmethod
    def read_function(self) -> str: ...

    @abstractmethod
    def read_scenario(self) -> str: ...
