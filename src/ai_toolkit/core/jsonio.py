"""JSON and JSONL files: tolerant reads, atomic writes, advisory locks."""
import contextlib
import fcntl
import json
import os


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


@contextlib.contextmanager
def locked(path):
    """Exclusive advisory lock on <path>.lock."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "a") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def read_jsonl(path):
    """Every parseable line of a JSONL file; missing file or bad lines are skipped."""
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def append_jsonl(path, record):
    with locked(path):
        with open(path, "a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
