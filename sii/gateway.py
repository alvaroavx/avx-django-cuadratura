from dataclasses import dataclass
from typing import Protocol

class SiiDisabledError(RuntimeError): pass

@dataclass(frozen=True)
class SubmissionResult:
    status: str
    track_id: str = ""
    error_code: str = ""

class SiiGateway(Protocol):
    def submit(self, *, receipt_id: str) -> SubmissionResult: ...
    def query(self, *, track_id: str) -> SubmissionResult: ...

class DisabledSiiGateway:
    def submit(self, *, receipt_id: str) -> SubmissionResult:
        raise SiiDisabledError("La emisión SII está deshabilitada en este ambiente.")
    def query(self, *, track_id: str) -> SubmissionResult:
        raise SiiDisabledError("La consulta SII está deshabilitada en este ambiente.")

class FakeSiiGateway:
    def __init__(self, result=None): self.result = result or SubmissionResult("ACCEPTED", "TEST-TRACK")
    def submit(self, *, receipt_id: str) -> SubmissionResult: return self.result
    def query(self, *, track_id: str) -> SubmissionResult: return self.result

