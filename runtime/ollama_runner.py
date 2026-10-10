#!/usr/bin/env python3
"""
ollama_runner.py — reproducible batch generation against a local Ollama server (HRgene v4).

Standard library only. Tested against Ollama 0.33 HTTP API (/api/chat, /api/tags, /api/version, /api/show).

USAGE
  python3 ollama_runner.py --model qwen3:8b --requests requests.jsonl --out ../experiments/20260901-qwen3-8b-c0c5-192 \
      [--schema ../schema/paired-review-bundle.schema.json | --schema json] \
      [--num-ctx 16384] [--num-predict 6000] [--temperature 0] [--seed 1] [--repeat 1] \
      [--limit N] [--no-resume] [--think] [--host http://127.0.0.1:11434] [--timeout 900] [--max-attempts 2]

INPUT  (--requests): JSONL, one request per line
  {"request_id": "case-0001.C2", "case_id": "case-0001", "condition": "C2",
   "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
   "format": <optional: JSON schema object or "json">, "meta": {...optional...}}
  A record may instead carry "system" and "user" strings; they are converted to messages.

OUTPUT (--out directory)
  config.json          model tag + digest + details + Ollama version + every option + input hashes + timestamps
  outputs/<request_id>.r<k>.json   one file per call: raw content, parsed JSON (if any), timings, token counts, attempts
  receipts.jsonl       one line per finished call (append-only; enables --resume)
  metrics.json         summary: counts, parse rate (overall and per condition), tokens/s, wall time, failures

DETERMINISM NOTES
  temperature 0 -> greedy decoding; repeats are (near-)identical, so use --repeat 1.
  For variance estimates use --temperature 0.2 --repeat 3; seed for repeat k is (--seed + k).
  Always set --num-ctx explicitly: Ollama's default context (4096) silently truncates long prompts.
  Thinking is OFF unless --think true|low|medium|high is passed (gpt-oss needs a level; thinking tokens count against num_predict).
"""
import argparse, hashlib, json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def http_json(url: str, payload=None, timeout: int = 60):
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_identity(host: str, model: str):
    version = http_json(f"{host}/api/version").get("version")
    tags = http_json(f"{host}/api/tags").get("models", [])
    entry = next((m for m in tags if m.get("name") == model or m.get("model") == model), None)
    if entry is None:
        names = [m.get("name") for m in tags]
        sys.exit(f"[runner] model '{model}' not found on {host}. Installed: {names}. Run: ollama pull {model}")
    show = {}
    try:
        show = http_json(f"{host}/api/show", {"model": model}, timeout=60)
    except Exception as e:  # noqa: BLE001
        show = {"error": str(e)}
    return {
        "ollama_version": version,
        "model": model,
        "digest": entry.get("digest"),
        "size_bytes": entry.get("size"),
        "modified_at": entry.get("modified_at"),
        "details": entry.get("details"),
        "capabilities": show.get("capabilities"),
        "parameters_from_modelfile": show.get("parameters"),
    }


def load_requests(path: str):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if "messages" not in r:
                msgs = []
                if r.get("system"):
                    msgs.append({"role": "system", "content": r["system"]})
                if r.get("user"):
                    msgs.append({"role": "user", "content": r["user"]})
                r["messages"] = msgs
            if not r["messages"]:
                sys.exit(f"[runner] request on line {i} has no messages")
            r.setdefault("request_id", f"req-{i:05d}")
            r.setdefault("case_id", None)
            r.setdefault("condition", None)
            out.append(r)
    ids = [r["request_id"] for r in out]
    if len(ids) != len(set(ids)):
        sys.exit("[runner] duplicate request_id values in requests file")
    return out


def try_parse_json(text: str):
    t = text.strip()
    if not t:
        return None
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        pass
    if t.startswith("```"):
        t2 = t.strip("`")
        if t2.lower().startswith("json"):
            t2 = t2[4:]
        try:
            return json.loads(t2.strip())
        except Exception:  # noqa: BLE001
            return None
    # last resort: first '{' .. last '}'
    a, b = t.find("{"), t.rfind("}")
    if a != -1 and b > a:
        try:
            return json.loads(t[a:b + 1])
        except Exception:  # noqa: BLE001
            return None
    return None


def main():
    ap = argparse.ArgumentParser(description="Reproducible batch runner for Ollama /api/chat")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--model", required=True)
    ap.add_argument("--requests", required=True, help="JSONL file of requests")
    ap.add_argument("--out", required=True, help="output run directory (created if missing)")
    ap.add_argument("--schema", default=None, help="path to a JSON schema file, or the literal 'json' for unconstrained JSON mode")
    ap.add_argument("--num-ctx", type=int, default=16384)
    ap.add_argument("--num-predict", type=int, default=6000)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None, help="only run the first N requests (smoke tests)")
    ap.add_argument("--no-resume", action="store_true", help="re-run even if an output file exists")
    ap.add_argument("--think", default="false", help="model thinking: false (default), true, or a level low|medium|high (gpt-oss)")
    ap.add_argument("--keep-alive", default="30m")
    ap.add_argument("--timeout", type=int, default=900, help="seconds per call")
    ap.add_argument("--max-attempts", type=int, default=2)
    ap.add_argument("--note", default="", help="free-text note stored in config.json")
    args = ap.parse_args()

    os.makedirs(os.path.join(args.out, "outputs"), exist_ok=True)
    fmt = None
    schema_sha = None
    if args.schema:
        if args.schema == "json":
            fmt = "json"
        else:
            with open(args.schema, "rb") as f:
                raw = f.read()
            schema_sha = sha256_bytes(raw)
            fmt = json.loads(raw.decode("utf-8"))

    ident = ollama_identity(args.host, args.model)
    requests = load_requests(args.requests)
    if args.limit:
        requests = requests[: args.limit]

    options = {
        "temperature": args.temperature,
        "num_ctx": args.num_ctx,
        "num_predict": args.num_predict,
    }
    think_value = {"false": False, "true": True}.get(str(args.think).lower(), str(args.think).lower())
    config = {
        "schema_version": "hrgene.v4.ollama_runner.config.v1",
        "started_at": now_iso(),
        "argv": sys.argv,
        "runner_sha256": sha256_file(os.path.abspath(__file__)),
        "host": args.host,
        "identity": ident,
        "options": options,
        "seed_base": args.seed,
        "repeat": args.repeat,
        "think": think_value,
        "keep_alive": args.keep_alive,
        "format": ("schema" if isinstance(fmt, dict) else fmt),
        "schema_path": args.schema,
        "schema_sha256": schema_sha,
        "requests_path": os.path.abspath(args.requests),
        "requests_sha256": sha256_file(args.requests),
        "n_requests": len(requests),
        "note": args.note,
    }
    cfg_path = os.path.join(args.out, "config.json")
    if os.path.exists(cfg_path) and not args.no_resume:
        prev = json.load(open(cfg_path, "r", encoding="utf-8"))
        for k in ("identity", "options", "seed_base", "format", "schema_sha256", "requests_sha256", "think"):
            if prev.get(k) != config.get(k):
                sys.exit(f"[runner] resume refused: '{k}' differs from the existing config.json in {args.out}. Use a new --out directory.")
        config["resumed_at"] = now_iso()
        config["started_at"] = prev.get("started_at")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    receipts_path = os.path.join(args.out, "receipts.jsonl")
    done_keys = set()
    if os.path.exists(receipts_path) and not args.no_resume:
        with open(receipts_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    done_keys.add((r["request_id"], r["repeat"]))

    t_start = time.time()
    total = len(requests) * args.repeat
    n_done = len(done_keys)
    print(f"[runner] model={args.model} digest={ident['digest'][:12]} ollama={ident['ollama_version']} requests={len(requests)} repeat={args.repeat} already_done={n_done}", flush=True)

    for r in requests:
        for k in range(args.repeat):
            key = (r["request_id"], k)
            if key in done_keys:
                continue
            out_path = os.path.join(args.out, "outputs", f"{r['request_id']}.r{k}.json")
            payload = {
                "model": args.model,
                "messages": r["messages"],
                "stream": False,
                "options": dict(options, seed=args.seed + k),
                "keep_alive": args.keep_alive,
                "think": think_value,
            }
            req_fmt = r.get("format", fmt)
            if req_fmt:
                payload["format"] = req_fmt
            attempts = []
            resp = None
            for attempt in range(1, args.max_attempts + 1):
                t0 = time.time()
                try:
                    resp = http_json(f"{args.host}/api/chat", payload, timeout=args.timeout)
                    attempts.append({"attempt": attempt, "ok": True, "seconds": round(time.time() - t0, 3)})
                    break
                except urllib.error.HTTPError as e:
                    body = e.read().decode("utf-8", "replace")[:500]
                    attempts.append({"attempt": attempt, "ok": False, "seconds": round(time.time() - t0, 3), "error": f"HTTP {e.code}: {body}"})
                except Exception as e:  # noqa: BLE001
                    attempts.append({"attempt": attempt, "ok": False, "seconds": round(time.time() - t0, 3), "error": repr(e)})
                time.sleep(min(30, 5 * attempt))
            content = (resp or {}).get("message", {}).get("content", "") if resp else ""
            parsed = try_parse_json(content) if content else None
            record = {
                "schema_version": "hrgene.v4.ollama_runner.output.v1",
                "request_id": r["request_id"],
                "case_id": r.get("case_id"),
                "condition": r.get("condition"),
                "meta": r.get("meta"),
                "repeat": k,
                "seed": args.seed + k,
                "model": args.model,
                "digest": ident["digest"],
                "format": ("schema" if isinstance(req_fmt, dict) else req_fmt),
                "ok": resp is not None,
                "attempts": attempts,
                "done_reason": (resp or {}).get("done_reason"),
                "prompt_eval_count": (resp or {}).get("prompt_eval_count"),
                "eval_count": (resp or {}).get("eval_count"),
                "prompt_eval_duration_ns": (resp or {}).get("prompt_eval_duration"),
                "eval_duration_ns": (resp or {}).get("eval_duration"),
                "total_duration_ns": (resp or {}).get("total_duration"),
                "thinking": (resp or {}).get("message", {}).get("thinking") if resp else None,
                "content": content,
                "content_sha256": sha256_bytes(content.encode("utf-8")) if content else None,
                "parse_ok": parsed is not None,
                "parsed": parsed,
                "finished_at": now_iso(),
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=1)
            receipt = {k2: record[k2] for k2 in ("request_id", "case_id", "condition", "repeat", "ok", "parse_ok", "done_reason", "prompt_eval_count", "eval_count", "eval_duration_ns", "content_sha256", "finished_at")}
            with open(receipts_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(receipt, ensure_ascii=False) + "\n")
            n_done += 1
            tps = (record["eval_count"] or 0) / (record["eval_duration_ns"] / 1e9) if record.get("eval_duration_ns") else 0.0
            elapsed = time.time() - t_start
            print(f"[runner] {n_done}/{total} {r['request_id']} r{k} ok={record['ok']} parse={record['parse_ok']} out_tok={record['eval_count']} {tps:.1f} tok/s elapsed={elapsed/60:.1f} min", flush=True)

    # metrics
    rows = []
    with open(receipts_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    by_cond = {}
    for row in rows:
        c = row.get("condition") or "_"
        d = by_cond.setdefault(c, {"n": 0, "ok": 0, "parse_ok": 0, "out_tokens": 0})
        d["n"] += 1
        d["ok"] += 1 if row.get("ok") else 0
        d["parse_ok"] += 1 if row.get("parse_ok") else 0
        d["out_tokens"] += row.get("eval_count") or 0
    gen_tok = sum((r.get("eval_count") or 0) for r in rows)
    gen_ns = sum((r.get("eval_duration_ns") or 0) for r in rows)
    metrics = {
        "schema_version": "hrgene.v4.ollama_runner.metrics.v1",
        "finished_at": now_iso(),
        "model": args.model,
        "digest": ident["digest"],
        "n_calls": len(rows),
        "n_ok": sum(1 for r in rows if r.get("ok")),
        "n_parse_ok": sum(1 for r in rows if r.get("parse_ok")),
        "parse_rate": (sum(1 for r in rows if r.get("parse_ok")) / len(rows)) if rows else None,
        "mean_gen_tokens_per_s": (gen_tok / (gen_ns / 1e9)) if gen_ns else None,
        "total_generated_tokens": gen_tok,
        "wall_seconds_this_session": round(time.time() - t_start, 1),
        "by_condition": by_cond,
    }
    with open(os.path.join(args.out, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"[runner] done. calls={metrics['n_calls']} parse_rate={metrics['parse_rate']} tok/s={metrics['mean_gen_tokens_per_s']}", flush=True)


if __name__ == "__main__":
    main()
