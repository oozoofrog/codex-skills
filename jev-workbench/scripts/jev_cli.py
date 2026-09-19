#!/usr/bin/env python3
"""Jev Skills Kit 0.1.1: explicit, auditable, cooperative API runner.

Not the official Jev CLI and not the full jev-decide authority controller.
Python 3.10+, standard library only. No shell execution or automatic file upload.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any
import urllib.error
import urllib.request
from datetime import datetime, timezone

VERSION = "0.1.1"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL_ALIASES = {"jev-latest", "jev-preview"}
MODEL_VERSION_PATTERN = r"jev-\d+\.\d+\.\d+"
MAX_BYTES = 262144  # Local safety budget; NOT the provider's token limit.
MAX_RESPONSE_BYTES = 2097152
BASE = Path(__file__).resolve().parent.parent
RESERVED = {"NEEDS_EVIDENCE", "REJECT_ALL", "NEEDS_REVIEW"}


class KitError(Exception):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def require(condition: bool, message: str) -> None:
    if not condition:
        raise KitError(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def request_bytes(request: Any) -> bytes:
    """Preserve candidate and criteria order in the actual HTTP body."""
    return json.dumps(request, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def request_digest(request: Any) -> str:
    return hashlib.sha256(request_bytes(request)).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reject_symlinks(path: Path) -> None:
    path = path.absolute()
    for part in [*path.parents, path]:
        # macOS temp roots use these system aliases; user-created links stay forbidden.
        if (sys.platform == "darwin" and part in (Path("/tmp"), Path("/var"))
                and part.resolve() == Path("/private") / part.name):
            continue
        require(not part.is_symlink(), f"Symlink paths are not supported: {part}")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in obj, f"Duplicate JSON key: {key}")
        obj[key] = value
    return obj


def loads(data: bytes | str) -> Any:
    def reject_constant(value: str) -> None:
        raise KitError(f"Non-finite JSON constant: {value}")
    try:
        return json.loads(data, object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    except (ValueError, UnicodeError) as exc:
        raise KitError(f"Invalid UTF-8 JSON: {exc}") from exc


def read_json(path: Path, limit: int = MAX_RESPONSE_BYTES) -> Any:
    reject_symlinks(path)
    require(path.is_file(), f"File not found: {path}")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    require(len(raw) <= limit, f"File exceeds local byte budget: {path}")
    return loads(raw)


def write_new(path: Path, obj: Any) -> None:
    """Exclusive creation: never silently replace evidence or receipts."""
    reject_symlinks(path)
    raw = json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def number(value: Any, low: float, high: float, name: str) -> None:
    require(type(value) in (float, int), f"{name} must be a number, not boolean")
    require(math.isfinite(value) and low <= value <= high,
            f"{name} must be finite and within [{low}, {high}]")


def present(value: Any, name: str) -> None:
    require(isinstance(value, (str, dict, list)) and bool(value), f"{name} is empty")


def secret_scan(value: Any) -> None:
    """Best-effort detector, NOT a guarantee that all secrets were removed."""
    text = canonical(value).decode("utf-8")
    patterns = [r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b",
                r'(?i)"(?:api[_-]?key|access[_-]?token|password|authorization|client_secret)"\s*:\s*"[^"\s]{4,}"']
    require(not any(re.search(p, text) for p in patterns),
            "Possible secret detected. Remove it from the input; there is no force-upload flag.")


def validate_request(request: Any) -> None:
    require(isinstance(request, dict), "request must be an object")
    require(set(request) == {"state", "model", "questions"},
            "request requires exactly state, model, questions")
    model = request["model"]
    require(isinstance(model, str) and (model in MODEL_ALIASES or
            re.fullmatch(MODEL_VERSION_PATTERN, model) is not None),
            "Use a versioned Jev model ID, jev-latest, or jev-preview")
    present(request["state"], "state")
    questions = request["questions"]
    require(isinstance(questions, dict) and 1 <= len(questions) <= 64,
            "Use 1..64 questions per request (local kit limit)")
    for qid, q in questions.items():
        require(isinstance(qid, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", qid) is not None,
                "Question IDs must be simple stable identifiers")
        require(isinstance(q, dict), f"Question {qid} must be an object")
        require(set(q) <= {"type", "instructions", "criteria"}, f"Unexpected fields in {qid}")
        require(q.get("type") in ("choice", "score", "noul"), f"Invalid type in {qid}")
        present(q.get("instructions"), f"{qid}.instructions")
        if q["type"] == "choice":
            require(isinstance(q.get("criteria"), dict) and len(q["criteria"]) >= 2,
                    f"{qid} Choice requires at least two options")
            for key, val in q["criteria"].items():
                require(isinstance(key, str) and bool(key), "Empty choice option")
                if val is not None:
                    present(val, f"{qid}.criteria.{key}")
        elif q["type"] == "score":
            require(isinstance(q.get("criteria"), list) and len(q["criteria"]) >= 2,
                    f"{qid} Score requires at least two ordered levels")
            for val in q["criteria"]:
                present(val, f"{qid}.criteria")
        elif "criteria" in q:
            require(isinstance(q["criteria"], dict) and set(q["criteria"]) == {"true", "false"},
                    "Noul criteria, when supplied, must define true and false")
    require(len(canonical(request)) <= MAX_BYTES,
            f"Payload exceeds {MAX_BYTES} bytes (local budget, not model token limit)")
    secret_scan(request)


def validate_packet(packet: Any) -> None:
    require(isinstance(packet, dict), "Input must be a packet object")
    required = {"schema_version", "task_id", "workflow", "authority", "is_example", "policy", "request"}
    require(required <= set(packet) <= required | {"lineage"}, "Unexpected or missing packet fields")
    require(type(packet["schema_version"]) is int and packet["schema_version"] == 1, "schema_version must be 1")
    for name in ("task_id", "workflow"):
        require(isinstance(packet[name], str) and bool(packet[name].strip()), f"{name} required")
    require(type(packet["is_example"]) is bool, "is_example must be boolean")
    require(packet["authority"] in {"delegated", "advisory", "evaluation"}, "Invalid authority mode")
    policy = packet["policy"]
    require(isinstance(policy, dict) and set(policy) == {"revision", "decision_question", "min_confidence"},
            "policy requires revision, decision_question, min_confidence")
    require(isinstance(policy["revision"], str) and bool(policy["revision"]), "Policy revision required")
    if policy["min_confidence"] is not None:
        number(policy["min_confidence"], 0, 1, "min_confidence")
    validate_request(packet["request"])
    decision = policy["decision_question"]
    if packet["authority"] == "delegated":
        require(isinstance(decision, str) and decision in packet["request"]["questions"], "Delegation requires a decision question")
        q = packet["request"]["questions"][decision]
        require(q["type"] == "choice", "Delegation requires Choice, not an agent-computed score")
        require({"NEEDS_EVIDENCE", "REJECT_ALL"} <= set(q["criteria"]), "Delegated Choice must allow NEEDS_EVIDENCE and REJECT_ALL")
    elif decision is not None:
        require(decision in packet["request"]["questions"] and packet["request"]["questions"][decision]["type"] == "choice",
                "decision_question must point to Choice or be null")
    if "lineage" in packet:
        lin = packet["lineage"]
        require(isinstance(lin, dict) and set(lin) == {"parent_packet_sha256", "change_reason"}, "Invalid lineage")
        require(re.fullmatch(r"[a-f0-9]{64}", lin["parent_packet_sha256"] or "") is not None, "Invalid parent hash")
        require(isinstance(lin["change_reason"], str) and bool(lin["change_reason"].strip()), "A new-evidence/change reason is required")
    secret_scan(packet)


def validate_response(request: dict[str, Any], response: Any) -> None:
    require(isinstance(response, dict), "Response must be an object")
    require(isinstance(response.get("model"), str) and bool(response["model"]), "Response model missing")
    if request["model"] in MODEL_ALIASES:
        require(response["model"] == request["model"] or
                re.fullmatch(MODEL_VERSION_PATTERN, response["model"]) is not None,
                "Returned model is not a Jev version or the requested alias")
    else:
        require(response["model"] == request["model"], "Returned model does not match pinned model")
    answers = response.get("answers")
    require(isinstance(answers, dict) and set(answers) == set(request["questions"]), "Response question IDs do not match request")
    usage = response.get("usage")
    require(isinstance(usage, dict), "Response usage missing")
    for key in ("input_tokens", "output_tokens"):
        require(type(usage.get(key)) is int and usage[key] >= 0, "Invalid usage token count")
    for qid, q in request["questions"].items():
        answer = answers[qid]
        require(isinstance(answer, dict) and answer.get("type") == q["type"], f"Wrong answer type for {qid}")
        if q["type"] == "noul":
            number(answer.get("noul"), 0, 1, f"{qid}.noul")
            continue
        probs = answer.get("probabilities")
        expected = set(q["criteria"]) if q["type"] == "choice" else {str(i) for i in range(len(q["criteria"]))}
        require(isinstance(probs, dict) and set(probs) == expected, f"Wrong probability keys for {qid}")
        for val in probs.values():
            number(val, 0, 1, f"{qid}.probability")
        require(abs(sum(probs.values()) - 1) <= 0.005, f"Probabilities do not sum to one for {qid}")
        number(answer.get("confidence"), 0, 1, f"{qid}.confidence")
        if q["type"] == "choice":
            require(answer.get("choice") in expected, f"Out-of-set choice in {qid}")
            require(probs[answer["choice"]] + 0.005 >= max(probs.values()), f"Choice is not a maximum-probability option in {qid}")
        else:
            n = len(q["criteria"])
            number(answer.get("score"), 0, n - 1, f"{qid}.score")
            expected_legend = {str(i): v for i, v in enumerate(q["criteria"])}
            require(answer.get("legend") == expected_legend, f"Score legend mismatch for {qid}")
            average = sum(int(k) * v for k, v in probs.items())
            require(abs(answer["score"] - average) <= 0.01 * n, f"Score/probability mismatch for {qid}")


def hash_watched(root: Path, names: list[str]) -> list[dict[str, str]]:
    reject_symlinks(root)
    root = root.resolve(strict=True)
    output = []
    for name in sorted(set(names)):
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "Watched paths must be relative and inside root")
        path = root / relative
        reject_symlinks(path)
        require(path.is_file() and path.resolve().is_relative_to(root), f"Invalid watched file: {name}")
        require(path.stat().st_size <= 16777216, "Watched files have a 16 MiB local limit")
        output.append({"path": str(relative), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return output


def inspect_run(directory: Path, require_fresh: bool = True) -> dict[str, Any]:
    reject_symlinks(directory)
    require(directory.is_dir(), "Prepared run directory missing")
    manifest = read_json(directory / "manifest.json")
    packet = read_json(directory / "packet.json")
    payload = read_json(directory / "payload.json")
    validate_packet(packet)
    legacy = manifest.get("kit_version") == "0.1.0"
    require(legacy or manifest.get("kit_version") == VERSION, "Unsupported prepared-run version")
    matches = payload == packet["request"] if legacy else request_bytes(payload) == request_bytes(packet["request"])
    require(matches, "payload.json does not match packet.json (including request order)")
    require(digest(packet) == manifest["packet_sha256"], "Packet hash mismatch")
    payload_hash = digest(payload) if legacy else request_digest(payload)
    require(payload_hash == manifest["payload_sha256"], "Payload hash mismatch")
    binding = {"packet_sha256": manifest["packet_sha256"], "root": manifest["root"], "watched": manifest["watched"]}
    if not legacy:
        binding["payload_sha256"] = manifest["payload_sha256"]
    require(digest(binding) == manifest["approval_sha256"], "Approval binding mismatch")
    fresh = True
    try:
        current = hash_watched(Path(manifest["root"]), [w["path"] for w in manifest["watched"]])
        fresh = current == manifest["watched"]
    except (KitError, OSError):
        fresh = False
    if require_fresh and not fresh:
        raise KitError("STALE: watched files changed or disappeared. Reprepare with new evidence.", 3)
    return {"manifest": manifest, "packet": packet, "fresh": fresh, "legacy_read_only": legacy}


def prepare(input_path: Path, out: Path, root: Path, watch: list[str]) -> dict[str, Any]:
    packet = read_json(input_path)
    validate_packet(packet)
    reject_symlinks(out)
    require(not out.exists(), "Output already exists; use status/check rather than overwriting a run")
    watched = hash_watched(root, watch)
    manifest = {"kit_version": VERSION, "created_at": now(), "packet_sha256": digest(packet),
                "payload_sha256": request_digest(packet["request"]), "root": str(root.resolve()), "watched": watched,
                "watched_contents_uploaded": False, "endpoint": ENDPOINT}
    binding = {"packet_sha256": manifest["packet_sha256"], "payload_sha256": manifest["payload_sha256"],
               "root": manifest["root"], "watched": watched}
    manifest["approval_sha256"] = digest(binding)
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".jev-prepare-", dir=out.parent))
    try:
        for name, value in (("packet.json", packet), ("payload.json", packet["request"]), ("manifest.json", manifest)):
            write_new(temporary / name, value)
        require(not out.exists(), "Output appeared during preparation")
        # Local cooperative operation, not a cross-process authorization boundary.
        os.rename(temporary, out)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {"status": "PREPARED", "directory": str(out.resolve()), **manifest,
            "preview": str((out / "payload.json").resolve()),
            "warning": "Only payload.json is sent. Hash approval is not proof of human authorization."}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise KitError("Redirect refused; API credentials will not be forwarded", 4)


def live_request(request: dict[str, Any], timeout: float) -> dict[str, Any]:
    key = os.environ.get("TYPESAFE_API_KEY", "")
    require(bool(key.strip()) and "\n" not in key and "\r" not in key, "TYPESAFE_API_KEY is missing or malformed")
    call = urllib.request.Request(ENDPOINT, data=request_bytes(request), method="POST",
                                  headers={"Authorization": "Bearer " + key,
                                           "Content-Type": "application/json",
                                           "User-Agent": "jev-skills-kit/" + VERSION})
    # ProxyHandler({}) deliberately disables ambient proxy configuration.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(call, timeout=timeout) as result:
            raw = result.read(MAX_RESPONSE_BYTES + 1)
            require(len(raw) <= MAX_RESPONSE_BYTES, "Response exceeds local byte budget")
            return loads(raw)
    except urllib.error.HTTPError as exc:
        # Do not echo response bodies: upstream errors can repeat private input.
        raise KitError(f"HTTP_{exc.code}: no automatic retry; inspect provider status and prior attempt.", 4) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise KitError("DELIVERY_UNKNOWN: transport failed; request may have reached provider. No automatic retry.", 4) from exc


def build_receipt(packet: dict[str, Any], response: dict[str, Any], origin: str,
                  kit_version: str = VERSION) -> dict[str, Any]:
    selected = None
    status = "EVALUATED"
    question = packet["policy"]["decision_question"]
    if question is not None:
        answer = response["answers"][question]
        selected = answer["choice"]
        status = selected if selected in RESERVED else "SELECTED"
        minimum = packet["policy"]["min_confidence"]
        if minimum is not None and answer["confidence"] < minimum and status == "SELECTED":
            status = "NEEDS_REVIEW"
    eligible = (origin == "live" and packet["authority"] == "delegated" and
                status == "SELECTED" and not packet["is_example"])
    receipt = {"schema_version": 1, "kit_version": kit_version, "task_id": packet["task_id"],
            "workflow": packet["workflow"], "authority": packet["authority"], "origin": origin,
            "decision_status": status, "selected": selected,
            "eligible_for_delegated_followup": eligible,
            "execution_authorized": False, "model": response["model"],
            "packet_sha256": digest(packet), "response_sha256": digest(response),
            "policy_revision": packet["policy"]["revision"],
            "note": "Selection is not factual proof or user execution permission. Cooperative record only."}
    if kit_version != "0.1.0":
        receipt["payload_sha256"] = request_digest(packet["request"])
    return receipt


def verified_receipt(directory: Path, packet: dict[str, Any], kit_version: str) -> dict[str, Any]:
    receipt = read_json(directory / "receipt.json")
    raw = read_json(directory / "response.json")
    validate_response(packet["request"], raw)
    require(receipt.get("origin") in {"live", "fixture", "external"}, "Invalid receipt origin")
    expected = build_receipt(packet, raw, receipt["origin"], kit_version)
    require(receipt == expected, "Receipt content mismatch")
    return receipt


def run(directory: Path, live: bool, fixture: Path | None, approved_sha: str | None,
        timeout: float, external: Path | None = None) -> dict[str, Any]:
    data = inspect_run(directory)
    packet, manifest = data["packet"], data["manifest"]
    require(sum((live, fixture is not None, external is not None)) == 1, "Choose exactly one provider mode")
    origin = "live" if live else "fixture" if fixture else "external"
    if (directory / "receipt.json").exists():
        saved = verified_receipt(directory, packet, manifest["kit_version"])
        require(saved["origin"] == origin, "Provider-mode mismatch; fixture/import cannot become live in the same run")
        return {"status": "CACHED", "receipt": saved}
    require(not (directory / "attempt.json").exists(),
            "An attempt already exists without a valid receipt. Inspect status; do not blindly replay.")
    require(not data["legacy_read_only"],
            "Legacy run is read-only. Preserve prior attempts; prepare and review new input before any new request.")
    if live:
        require(not packet["is_example"], "Example packets cannot be sent live. Replace all sample data and set is_example=false.")
        require(approved_sha == manifest["approval_sha256"], "Exact approval_sha256 required after reviewing payload.json")
        require(bool(os.environ.get("TYPESAFE_API_KEY", "").strip()), "TYPESAFE_API_KEY is required")
    else:
        raw = read_json(fixture or external)
        validate_response(packet["request"], raw)
    lock = directory / ".run-lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise KitError("Run is locked; inspect prior attempt before recovery", 3) from exc
    try:
        require(not (directory / "attempt.json").exists(), "Concurrent/prior attempt detected")
        write_new(directory / "attempt.json", {"origin": origin, "started_at": now(),
                                               "packet_sha256": digest(packet)})
        try:
            if live:
                raw = live_request(packet["request"], timeout)
                # Preserve raw provider data even if contract validation fails.
                write_new(directory / "response.json", raw)
                validate_response(packet["request"], raw)
            else:
                write_new(directory / "response.json", raw)
            receipt = build_receipt(packet, raw, origin)
            write_new(directory / "receipt.json", receipt)
            return {"status": "COMPLETED", "receipt": receipt}
        except KitError as exc:
            write_new(directory / "failure.json", {"status": "UNAVAILABLE" if exc.code == 4 else "INVALID_RESPONSE",
                                                   "message": str(exc), "recorded_at": now()})
            raise
    finally:
        with contextlib.suppress(OSError):
            lock.rmdir()


def status(directory: Path, actionable: bool = False) -> dict[str, Any]:
    data = inspect_run(directory, require_fresh=False)
    result: dict[str, Any] = {"status": "READY" if data["fresh"] else "STALE", "fresh": data["fresh"],
                              "legacy_read_only": data["legacy_read_only"],
                              "watched_files": len(data["manifest"]["watched"]),
                              "task_id": data["packet"]["task_id"], "workflow": data["packet"]["workflow"]}
    if (directory / "receipt.json").exists():
        result["receipt"] = verified_receipt(directory, data["packet"], data["manifest"]["kit_version"])
    elif (directory / "failure.json").exists():
        result["failure"] = read_json(directory / "failure.json")
    elif (directory / "attempt.json").exists():
        result["status"] = "DELIVERY_UNKNOWN" if data["fresh"] else "STALE"
    if actionable:
        require(not data["legacy_read_only"], "Legacy run is read-only; it cannot authorize new delegated followup")
        require(data["fresh"], "STALE: cannot use a stale decision")
        require(result.get("receipt", {}).get("eligible_for_delegated_followup") is True,
                "Not eligible: require a live, delegated, selected, non-example result")
    return result


def evaluate(cases_path: Path) -> dict[str, Any]:
    """Offline evaluation of already-saved responses; never issues receipts."""
    cases = read_json(cases_path)
    require(isinstance(cases, list) and bool(cases), "Evaluation cases must be a nonempty list")
    results = []
    seen = set()
    for case in cases:
        require(isinstance(case, dict) and set(case) == {"case_id", "packet", "response", "question_id", "acceptable"}, "Invalid evaluation case")
        require(case["case_id"] not in seen, "Duplicate case_id")
        seen.add(case["case_id"])
        packet = read_json(cases_path.parent / case["packet"])
        raw = read_json(cases_path.parent / case["response"])
        validate_packet(packet)
        validate_response(packet["request"], raw)
        qid = case["question_id"]
        require(qid in raw["answers"] and raw["answers"][qid]["type"] == "choice", "Evaluation currently supports Choice labels only")
        acceptable = case["acceptable"]
        require(isinstance(acceptable, list) and bool(acceptable) and all(v in packet["request"]["questions"][qid]["criteria"] for v in acceptable), "Invalid acceptable option set")
        answer = raw["answers"][qid]
        results.append({"case_id": case["case_id"], "choice": answer["choice"], "accepted": answer["choice"] in acceptable,
                        "confidence": answer["confidence"], "model": raw["model"]})
    accepted = sum(r["accepted"] for r in results)
    return {"evaluation_only": True, "execution_authorized": False, "total": len(results), "accepted": accepted,
            "acceptance_rate": accepted / len(results), "cases": results,
            "warning": "A synthetic fixture score measures harness behavior, not live model accuracy."}


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Local-only runtime/key checks; never prints keys")
    sub.add_parser("templates", help="List packaged workflow templates")
    pre = sub.add_parser("prepare", help="Freeze explicit input and show exact outbound preview")
    pre.add_argument("--input", type=Path, required=True)
    pre.add_argument("--out", type=Path, required=True)
    pre.add_argument("--root", type=Path, default=Path.cwd())
    pre.add_argument("--watch", action="append", default=[], help="Hash a relative file locally; does not upload its contents")
    runp = sub.add_parser("run", help="Run once or return a saved response")
    runp.add_argument("directory", type=Path)
    providers = runp.add_mutually_exclusive_group(required=True)
    providers.add_argument("--live", action="store_true")
    providers.add_argument("--fixture", type=Path)
    providers.add_argument("--external-response", type=Path)
    runp.add_argument("--approved-sha")
    runp.add_argument("--timeout", type=float, default=30)
    for name in ("status", "check"):
        p = sub.add_parser(name)
        p.add_argument("directory", type=Path)
        p.add_argument("--require-actionable", action="store_true")
    ev = sub.add_parser("evaluate", help="Offline comparison of saved Choice answers with acceptable sets")
    ev.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            emit({"kit_version": VERSION, "python": sys.version.split()[0],
                  "typesafe_key_present": bool(os.getenv("TYPESAFE_API_KEY")),
                  "endpoint": ENDPOINT, "network_called": False,
                  "official_cli": False, "authority_enforcement": "cooperative",
                  "templates": len(list((BASE / "templates").glob("*.json")))})
        elif args.command == "templates":
            emit([p.stem for p in sorted((BASE / "templates").glob("*.json"))])
        elif args.command == "prepare":
            emit(prepare(args.input, args.out, args.root, args.watch))
        elif args.command == "run":
            number(args.timeout, 1, 120, "timeout")
            emit(run(args.directory, args.live, args.fixture, args.approved_sha, args.timeout, args.external_response))
        elif args.command in ("status", "check"):
            result = status(args.directory, args.require_actionable)
            emit(result)
            if args.command == "check" and not result["fresh"]:
                return 3
        elif args.command == "evaluate":
            emit(evaluate(args.cases))
        return 0
    except KitError as exc:
        emit({"status": "ERROR", "message": str(exc), "exit_code": exc.code})
        return exc.code
    except (OSError, KeyError, TypeError, ValueError) as exc:
        emit({"status": "ERROR", "message": f"{type(exc).__name__}: {exc}", "exit_code": 2})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
