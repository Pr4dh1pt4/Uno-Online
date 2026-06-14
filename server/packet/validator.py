from shared.packet_types import C2S

_PUBLIC_TYPES = {
    C2S.REGISTER_REQ,
    C2S.LOGIN_REQ,
    C2S.SESSION_LOGIN_REQ,
    C2S.PING,
    C2S.RECONNECT_REQ,
}

_KNOWN_TYPES = {v for k, v in vars(C2S).items() if not k.startswith("_") and isinstance(v, str)}

class ValidationResult:
    def __init__(self, ok: bool, reason: str = ""):
        self.ok = ok
        self.reason = reason

class ConnSeqTracker:

    def __init__(self):
        self.last_seq = -1

    def check_and_update(self, seq: int) -> bool:
        if not isinstance(seq, int) or seq <= self.last_seq:
            return False
        self.last_seq = seq
        return True

def validate_structure(pkt) -> ValidationResult:
    if not isinstance(pkt, dict):
        return ValidationResult(False, "not_object")
    ptype = pkt.get("type")
    if not isinstance(ptype, str) or ptype not in _KNOWN_TYPES:
        return ValidationResult(False, "unknown_type")
    if "seq" not in pkt or not isinstance(pkt.get("seq"), int):
        return ValidationResult(False, "missing_seq")
    if "payload" not in pkt or not isinstance(pkt.get("payload"), dict):
        return ValidationResult(False, "bad_payload")
    return ValidationResult(True)

def validate_auth(pkt, authenticated: bool) -> ValidationResult:
    ptype = pkt["type"]
    if ptype in _PUBLIC_TYPES:
        return ValidationResult(True)
    if not authenticated:
        return ValidationResult(False, "not_authenticated")
    return ValidationResult(True)

def validate_sequence(pkt, tracker: ConnSeqTracker) -> ValidationResult:
    if pkt["type"] == C2S.PING:
        return ValidationResult(True)
    if not tracker.check_and_update(pkt["seq"]):
        return ValidationResult(False, "bad_sequence")
    return ValidationResult(True)

def run_pipeline(pkt, authenticated: bool, tracker: ConnSeqTracker) -> ValidationResult:
    for step in (
        validate_structure(pkt),
        validate_auth(pkt, authenticated) if isinstance(pkt, dict) and "type" in pkt else ValidationResult(False, "not_object"),
    ):
        if not step.ok:
            return step
    return validate_sequence(pkt, tracker)
