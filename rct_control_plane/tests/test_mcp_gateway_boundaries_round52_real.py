"""
Round 52: the MCP gateway's three powerful tools now have real boundaries. Before, the shell,
filesystem and fetch tools were limited by a pattern denylist only (CodeQL: path injection, command
line injection, server-side request forgery). Real files, real subprocesses, a real local HTTP server.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rct_control_plane import mcp_gateway as gw


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv(gw.GATEWAY_ROOT_ENV, str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()
    monkeypatch.delenv(gw.GATEWAY_SHELL_ALLOW_ENV, raising=False)
    monkeypatch.delenv(gw.GATEWAY_FETCH_PRIVATE_ENV, raising=False)
    return tmp_path


def fs(action, path, content=None):
    args = {"action": action, "path": path}
    if content is not None:
        args["content"] = content
    return gw.execute_delentia_tool("delentia_workspace_fs", args)


# ------------------------------------------------------------------ filesystem

def test_files_inside_the_workspace_work(root):
    assert fs("write", "notes/a.txt", "hello")["status"] == "SUCCESS"
    assert fs("read", "notes/a.txt")["content"] == "hello"
    assert "a.txt" in fs("list", "notes")["entries"]


_DRIVE_PATH = "C:\\Windows\\win.ini" if os.name == "nt" else "/root/.ssh/config"      # a drive path is only a file name on POSIX


@pytest.mark.parametrize("path", ["../outside.txt", "notes/../../outside.txt", "..", "/etc/passwd", _DRIVE_PATH])
def test_paths_outside_the_workspace_are_vetoed_for_every_action(root, path):
    for action in ("read", "write", "list"):
        result = fs(action, path, "x" if action == "write" else None)
        assert result["status"] == "VETOED_BY_WORKSPACE_BOUNDARY", (action, path, result)
    assert not (root / "outside.txt").exists()


@pytest.mark.parametrize("name", [".env", "config/.env.local", "deploy_secret.txt", "credentials.json", "vault_master.key", "keys/id_rsa", "a.pem"])
def test_secret_looking_names_are_vetoed_even_inside_the_workspace(root, name):
    (root / "ws" / "config").mkdir(exist_ok=True)
    assert fs("write", name, "x")["status"] == "VETOED_BY_WORKSPACE_BOUNDARY"
    assert fs("read", name)["status"] == "VETOED_BY_WORKSPACE_BOUNDARY"


def test_a_symlink_that_leaves_the_workspace_is_refused(root):
    outside = root / "outside"
    outside.mkdir()
    (outside / "x.txt").write_text("secret", encoding="utf-8")
    try:
        os.symlink(outside, root / "ws" / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks cannot be created here")
    assert fs("read", "link/x.txt")["status"] == "VETOED_BY_WORKSPACE_BOUNDARY"


def test_delete_is_still_vetoed_and_errors_do_not_leak_details(root):
    assert fs("delete", "a.txt")["status"] == "VETOED_BY_FDIA_GATE"
    (root / "ws" / "dir").mkdir()
    failed = fs("read", "dir")          # a directory cannot be read as a file
    assert failed["status"] in ("ERROR", "SUCCESS")
    if failed["status"] == "ERROR":
        assert str(root) not in json.dumps(failed) and "Traceback" not in json.dumps(failed)


# ------------------------------------------------------------------ shell

def shell(command, cwd="."):
    return gw.execute_delentia_tool("delentia_execute_safe_shell", {"command": command, "cwd": cwd})


def test_destructive_commands_are_still_vetoed_first(root):
    assert shell("rm -rf /production/database")["status"] == "VETOED_BY_FDIA_GATE"


def test_only_allowlisted_programs_start_and_no_shell_interprets_the_line(root):
    ok = shell('python -c "print(6*7)"')
    assert ok["status"] == "SUCCESS" and ok["stdout"].strip() == "42", ok
    for command in ("powershell -c 1", "bash -c id", "curl http://example.com", "calc.exe", "echo hi"):
        # CORD may refuse a suspicious line before the allowlist is consulted; either way it does not run
        assert shell(command)["status"] in ("VETOED_BY_SHELL_ALLOWLIST", "VETOED_BY_CORD"), command
    piped = shell('python -c "print(1)" | python -c "print(2)"')       # `|` is an argument to the first program, not a pipe
    assert piped["status"] == "SUCCESS" and piped["stdout"].split() == ["1"], piped
    chained = shell('python -c "print(1)" && python -c "print(2)"')
    assert "2" not in chained.get("stdout", "")


def test_the_working_directory_must_be_inside_the_workspace(root):
    assert shell('python -c "print(1)"', cwd="..")["status"] == "VETOED_BY_WORKSPACE_BOUNDARY"
    assert shell('python -c "print(1)"', cwd=str(root))["status"] == "VETOED_BY_WORKSPACE_BOUNDARY"
    (root / "ws" / "sub").mkdir()
    assert shell('python -c "print(1)"', cwd="sub")["status"] == "SUCCESS"


def test_the_operator_can_widen_the_allowlist_a_caller_cannot(root, monkeypatch):
    assert shell("hostname")["status"] == "VETOED_BY_SHELL_ALLOWLIST"
    monkeypatch.setenv(gw.GATEWAY_SHELL_ALLOW_ENV, "hostname")
    assert shell("hostname")["status"] == "SUCCESS"


def test_an_unbalanced_quote_is_an_error_not_a_crash(root):
    assert shell('python -c "print(1)')["status"] == "ERROR"


# ------------------------------------------------------------------ fetch

class _Page(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        raw = b"hello from the page"
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


@pytest.fixture
def page():
    server = HTTPServer(("127.0.0.1", 0), _Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def fetch(url):
    return gw.execute_delentia_tool("delentia_web_fetch", {"url": url})


@pytest.mark.parametrize("url", ["http://127.0.0.1:1/", "http://localhost/", "http://169.254.169.254/latest/meta-data", "http://[::1]/",
                                 "http://10.0.0.5/", "http://192.168.1.1/", "http://0.0.0.0/"])
def test_private_loopback_and_link_local_addresses_are_not_fetched(root, url):
    assert fetch(url)["status"] == "VETOED_BY_NETWORK_BOUNDARY"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/", "gopher://x/", "example.com", ""])
def test_only_http_and_https_are_accepted(root, url):
    assert fetch(url)["status"] == "ERROR"


def test_the_operator_can_allow_private_hosts_and_a_redirect_is_still_not_followed(root, page, monkeypatch):
    assert fetch(page + "/")["status"] == "VETOED_BY_NETWORK_BOUNDARY"
    monkeypatch.setenv(gw.GATEWAY_FETCH_PRIVATE_ENV, "1")
    ok = fetch(page + "/")
    assert ok["status"] == "SUCCESS" and "hello from the page" in ok["preview"]
    redirected = fetch(page + "/redirect")
    assert redirected["status"] == "ERROR" and "meta-data" not in json.dumps(redirected)


def test_helpers_agree_with_the_tools(root):
    assert gw._in_workspace("a/b") == os.path.normpath(os.path.join(gw._workspace_root(), "a", "b"))
    assert gw._in_workspace("../x") is None
    assert gw._blocked_name("x/.ENV") and not gw._blocked_name("readme.md")
    assert gw._resolve_public_target("http://127.0.0.1/") is None


def test_https_fetch_connects_to_the_validated_address_and_checks_the_host_name(root, tmp_path, monkeypatch):
    """A real TLS server with a self-signed certificate for 'localhost': the request goes to the address
    that was validated, the certificate is checked against the host name, and a wrong name is refused."""
    import datetime
    import ipaddress
    import ssl

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "c.pem", tmp_path / "k.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

    server = HTTPServer(("127.0.0.1", 0), _Page)
    server_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    server_context.minimum_version = ssl.TLSVersion.TLSv1_2
    server_context.load_cert_chain(str(cert_path), str(key_path))
    server.socket = server_context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    real_create = ssl.create_default_context
    monkeypatch.setattr(ssl, "create_default_context", lambda *a, **k: real_create(cafile=str(cert_path)))
    monkeypatch.setenv(gw.GATEWAY_FETCH_PRIVATE_ENV, "1")
    try:
        target = gw._resolve_public_target(f"https://localhost:{server.server_port}/")
        assert target is not None and target.ip in ("127.0.0.1", "::1")
        assert "hello from the page" in gw._fetch_pinned(target)
        wrong = gw._FetchTarget("https", "not-localhost.invalid", target.ip, target.port, "/")
        with pytest.raises(ssl.SSLError):
            gw._fetch_pinned(wrong)
    finally:
        server.shutdown()
        server.server_close()


def test_the_workspace_root_can_be_listed_but_not_read_or_written(root):
    (root / "ws" / "a.txt").write_text("x", encoding="utf-8")
    for path in (".", "", "notes/.."):
        assert "a.txt" in fs("list", path)["entries"], path
        assert fs("read", path)["status"] == "VETOED_BY_WORKSPACE_BOUNDARY"
        assert fs("write", path, "x")["status"] == "VETOED_BY_WORKSPACE_BOUNDARY"


def test_a_failing_scheduled_task_does_not_leak_its_exception_text(root):
    secret = "internal path C:/private/db.sqlite is locked"

    def boom():
        raise RuntimeError(secret)

    gw.scheduler.register_task(name="boom_task", description="fails", interval_seconds=3600, handler=boom)
    task_id = next(t["task_id"] for t in gw.scheduler.list_tasks() if t["name"] == "boom_task")
    result = gw.execute_delentia_tool("delentia_cron_scheduler", {"action": "trigger", "task_id": task_id})
    assert result["status"] == "ERROR" and secret not in json.dumps(result) and "private" not in json.dumps(result)
