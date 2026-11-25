"""Reserve PyPI names: one 0.0.1 release per name whose page is the name, the architecture image and the
repository link -- nothing else. Standard library only (no build, no twine).

    python3 scripts/reserve_pypi.py ztna bao1 bao2                   #  check each name
    python3 scripts/reserve_pypi.py healthchecks vaultwarden --upload          #  the same, then publish to PyPI

The token is the [pypi] password in ~/.pypirc, or PYPI_TOKEN.

Every upload is kept in scripts/reserved.yaml: `registered` (PyPI accepted it) and `failed` (PyPI refused it,
with its reason). A name that later registers moves from failed to registered. Checks are not recorded.

A name already on PyPI is skipped. PyPI may still refuse a free-looking name (too similar to another,
prohibited): the upload then fails with PyPI's message and nothing else happens. A reserved name needs a
real repository and release later (PEP 541); the page links the repository it will live in.
"""
import base64
import configparser
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile

UPLOAD = "https://upload.pypi.org/legacy/"
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reserved.yaml")
DEFAULTS = {
    "owner": "cloudformer",
    "author": "Frank Zhang",
    "version": "0.0.1",
}


def names_from(argv):
    """The names, separated by spaces: ztna bao1 bao2."""
    names = [a for a in argv if not a.startswith("--")]
    bad = [n for n in names if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]|[A-Za-z0-9]", n)]
    if not names or bad:
        sys.exit(f"names: give them separated by spaces, e.g. ztna bao1 bao2 (invalid: {bad})")
    return names


def on_pypi(name):
    """None when free; else the project's homepage / repository URLs (to tell ours from someone else's)."""
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=20) as r:
            info = json.load(r)["info"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return " ".join([info.get("home_page") or ""] + list((info.get("project_urls") or {}).values()))


def page(name, c):
    repo = f"https://github.com/{c['owner']}/{name}"
    image = f"https://raw.githubusercontent.com/{c['owner']}/{name}/main/docs/architecture.svg"
    return f"# {name}\n\n![{name} architecture]({image})\n\n{repo}\n"


def metadata(name, c):
    version = c["version"]
    fields = {
        "metadata_version": "2.1", "name": name, "version": version,
        "summary": f"Reserved for https://github.com/{c['owner']}/{name}",
        "author": c["author"], "license": "MIT", "requires_python": ">=3.9",
        "description_content_type": "text/markdown", "description": page(name, c),
        "classifiers": ["Development Status :: 1 - Planning", "License :: OSI Approved :: MIT License",
                        "Programming Language :: Python :: 3"],
        "project_urls": [f"Homepage, https://github.com/{c['owner']}/{name}"],
    }
    text = "".join([
        "Metadata-Version: 2.1\n", f"Name: {name}\n", f"Version: {version}\n", f"Summary: {fields['summary']}\n",
        f"Author: {c['author']}\n", "License: MIT\n",
        *[f"Project-URL: {u}\n" for u in fields["project_urls"]],
        *[f"Classifier: {k}\n" for k in fields["classifiers"]],
        f"Requires-Python: {fields['requires_python']}\n", "Description-Content-Type: text/markdown\n",
        "\n", fields["description"]])
    return fields, text


def wheel(name, fields, meta_text, out_dir):
    """A py3-none-any wheel with one module that says what the project is."""
    module, version = re.sub(r"[-.]+", "_", name).lower(), fields["version"]
    dist = f"{module}-{version}.dist-info"
    files = {
        f"{module}/__init__.py": f'"""{name}: reserved name, planned project. {fields["project_urls"][0].split(", ")[1]}"""\n'
                                 f'__version__ = "{version}"\n',
        f"{dist}/METADATA": meta_text,
        f"{dist}/WHEEL": "Wheel-Version: 1.0\nGenerator: reserve_pypi\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{dist}/top_level.txt": module + "\n",
    }
    record = []
    for path, text in files.items():
        data = text.encode()
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        record.append(f"{path},sha256={digest},{len(data)}")
    files[f"{dist}/RECORD"] = "\n".join(record + [f"{dist}/RECORD,,"]) + "\n"
    path = os.path.join(out_dir, f"{module}-{version}-py3-none-any.whl")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for p, text in files.items():
            z.writestr(p, text)
    return path


def token():
    if os.environ.get("PYPI_TOKEN"):
        return os.environ["PYPI_TOKEN"]
    rc = configparser.ConfigParser()
    rc.read(os.path.expanduser("~/.pypirc"))
    if rc.has_option("pypi", "password"):
        return rc.get("pypi", "password")
    sys.exit("no token: set PYPI_TOKEN or the [pypi] password in ~/.pypirc")


def upload(path, fields, tok):
    with open(path, "rb") as f:
        content = f.read()
    form = dict(fields, **{":action": "file_upload", "protocol_version": "1", "filetype": "bdist_wheel",
                           "pyversion": "py3", "sha256_digest": hashlib.sha256(content).hexdigest()})
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    for key, value in form.items():
        for v in (value if isinstance(value, list) else [value]):
            body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{v}\r\n'.encode())
    body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="content"; filename="{os.path.basename(path)}"\r\n'
               "Content-Type: application/octet-stream\r\n\r\n".encode() + content + f"\r\n--{boundary}--\r\n".encode())
    auth = base64.b64encode(f"__token__:{tok}".encode()).decode()
    req = urllib.request.Request(UPLOAD, data=body.getvalue(), method="POST", headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}", "Authorization": f"Basic {auth}"})
    try:
        urllib.request.urlopen(req, timeout=60)
        return None
    except urllib.error.HTTPError as e:
        # PyPI puts its message in the status line ("400 The name 'x' isn't allowed. See ..."); the body repeats it
        reason = str(e.reason)
        if reason in ("Bad Request", "Forbidden", ""):
            lines = [ln.strip() for ln in e.read().decode(errors="replace").splitlines() if ln.strip()]
            reason = lines[-1] if lines else reason
        return e.code, reason.split(" See ")[0].strip()


def load_log():
    """{"registered": {name: note}, "failed": {name: note}} from reserved.yaml (written only by save_log)."""
    log, section = {"registered": {}, "failed": {}}, None
    if os.path.isfile(LOG):
        for line in open(LOG, encoding="utf-8"):
            if line.rstrip().endswith(":") and not line.startswith(" "):
                section = line.rstrip()[:-1]
            elif line.startswith("  - ") and section in log:
                name, _, note = line[4:].rstrip("\n").partition("  # ")
                log[section][name.strip()] = note.strip()
    return log


def save_log(log):
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("# written by scripts/reserve_pypi.py\n")
        for section in ("registered", "failed"):
            f.write(f"{section}:\n")
            for name in sorted(log[section]):
                note = log[section][name]
                f.write(f"  - {name}" + (f"  # {note}" if note else "") + "\n")


def record(log, name, ok, note=""):
    log["registered" if ok else "failed"][name] = note
    log["failed" if ok else "registered"].pop(name, None)


COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
GREEN = "\033[32m{}\033[0m" if COLOR else "{}"
RED = "\033[31m{}\033[0m" if COLOR else "{}"


def report(name, status, lines=(), next_step="", good=False, bad=False):
    """One block per name: a blank line, `name: status` (green when good), the details and `next:` under it."""
    width = max(len(name) + 2, len("next: "))
    print(f"\n{(name + ':').ljust(width)}{GREEN.format(status) if good else RED.format(status) if bad else status}")
    for line in lines:
        print(" " * width + line)
    if next_step:
        print("next:".ljust(width) + next_step)


def main():
    send = "--upload" in sys.argv[1:]
    c, names = DEFAULTS, names_from(sys.argv[1:])
    out = tempfile.mkdtemp(prefix="reserve-pypi-")
    tok = token() if send else None
    me = f"python3 {os.path.abspath(__file__).replace(os.path.expanduser('~'), '~')}"
    log = load_log()
    for name in names:
        link = f"https://pypi.org/project/{name}/"
        urls = on_pypi(name)
        if urls is not None:
            if f"github.com/{c['owner']}/" in urls:
                report(name, "already registered by you", [link])
            else:
                report(name, "taken by someone else", [link], "pick another name")
            continue
        if re.sub(r"[-.]+", "_", name).lower() in getattr(sys, "stdlib_module_names", ()):
            report(name, "not allowed", ["a Python standard library module"], "pick another name")
            continue
        fields, meta_text = metadata(name, c)
        path = wheel(name, fields, meta_text, out)
        if not send:
            report(name, "Available, no release on PyPI", [], f"{me} {name} --upload", good=True)
            continue
        err = upload(path, fields, tok)
        code, reason = err or (200, "")
        if code == 429:   # PyPI's limit on new projects per account: not an answer about the name
            report(name, "not tried: PyPI rate limit (too many new projects for now)", [],
                   f"wait about an hour, then: {me} {name} --upload")
            continue
        if code == 403 and "upload to project" not in reason:   # the token, not the name
            report(name, "registration failed!", [reason], bad=True, next_step="check the token in ~/.pypirc (or PYPI_TOKEN), then run again")
            continue
        if code == 403:   # "The user ... isn't allowed to upload to project 'x'": registered by someone, no release
            reason = "registered by someone else (no release yet, so it does not show on PyPI)"
        record(log, name, not err, reason)
        if not err:
            report(name, "registered successfully!", [link], good=True, next_step=
                   f"run the SERIES.md block with NAME={name} -> github.com/{c['owner']}/{name} and ~/repo-private/{name}")
        else:
            report(name, "registration failed!", [reason, "why: https://docs.pypi.org/project-management/choosing-a-name/"], bad=True, next_step=
                   "pick another name")
    if send:
        save_log(log)
        print(f"\nall results: {LOG.replace(os.path.expanduser('~'), '~')}\n")
    else:
        print()


if __name__ == "__main__":
    main()
