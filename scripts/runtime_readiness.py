"""Fail-fast preflight for real local integration prerequisites; never skips tests.

No paid provider, model download, SSH connection, or sandbox disabling occurs.
Exit 1 means the full integration environment is not ready, even if unit tests pass.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def check(model: str, inference: bool = False) -> dict:
    import httpx
    results = {}
    try:
        with httpx.Client(trust_env=False, timeout=15) as client:
            response = client.get('http://127.0.0.1:11434/api/tags')
            response.raise_for_status()
            names = [item['name'] for item in response.json().get('models', [])]
            present = model in names
            results['ollama_model'] = {'ready': present, 'requested': model, 'installed': names,
                'action': None if present else 'Install the real required model via the official registry; check blob/CDN access, disk and manifest checksums.'}
            if present and inference:
                answer = client.post('http://127.0.0.1:11434/api/generate', json={
                    'model': model, 'prompt': 'Reply PONG', 'stream': False, 'options': {'num_predict': 8}}, timeout=180)
                answer.raise_for_status()
                results['ollama_inference'] = {'ready': bool(answer.json().get('response')), 'model': model}
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        results['ollama_model'] = {'ready': False, 'error': type(exc).__name__, 'action': 'Start the local Ollama service and verify the model separately.'}
    try:
        addresses = sorted({r[4][0] for r in socket.getaddrinfo('example.com', 443, type=socket.SOCK_STREAM)})
        results['public_dns'] = {'ready': bool(addresses), 'host': 'example.com'}
    except OSError as exc:
        results['public_dns'] = {'ready': False, 'error': type(exc).__name__,
            'action': 'Provide working host DNS and allowed public egress for the DNS-pinned crawler. Proxy-only HTTP does not establish this capability.'}
    with tempfile.TemporaryDirectory(prefix='delentia-readiness-') as temp:
        from rct_control_plane.browser_tool import find_browser
        browser = find_browser()
        if not browser:
            results['browser_sandbox'] = {'ready': False, 'error': 'no browser executable'}
        else:
            env = {**os.environ, 'XDG_CONFIG_HOME': temp + '/config', 'XDG_CACHE_HOME': temp + '/cache'}
            try:
                run = subprocess.run([browser, '--headless', '--disable-gpu', '--no-first-run',
                    '--user-data-dir=' + temp + '/profile', '--dump-dom', 'about:blank'],
                    capture_output=True, text=True, timeout=20, env=env)
                results['browser_sandbox'] = {'ready': run.returncode == 0 and '<html' in run.stdout,
                    'exit_code': run.returncode, 'stderr_excerpt': run.stderr[-1500:],
                    'action': 'Use a host with usable Chromium sandbox: root-owned 4755 helper or permitted user namespaces. Never use --no-sandbox.'}
            except (OSError, subprocess.TimeoutExpired) as exc:
                results['browser_sandbox'] = {'ready': False, 'error': type(exc).__name__}
        ssh = shutil.which('ssh')
        if not ssh:
            results['ssh_config'] = {'ready': False, 'error': 'OpenSSH not installed'}
        else:
            from rct_control_plane.sandbox import ssh_command_line
            key, known = Path(temp)/'key', Path(temp)/'known_hosts'
            key.write_text('synthetic preflight placeholder');known.write_text('')
            argv = ssh_command_line({'bin': ssh, 'target': 'agent@example.invalid', 'port': '22',
                'key': str(key), 'known_hosts': str(known), 'workdir': 'work'}, 'true', 10)
            run = subprocess.run([argv[0], '-G'] + argv[1:-1], capture_output=True, text=True, timeout=10)
            results['ssh_config'] = {'ready': run.returncode == 0 and 'stricthostkeychecking true' in run.stdout,
                                    'exit_code': run.returncode, 'action': 'Explicit isolated config; no connection attempted.'}
    return {'format': 'delentia-runtime-readiness-1', 'ready': all(r['ready'] for r in results.values()),
            'checks': results, 'note': 'This is preflight, not a replacement for the integration tests or model capability evaluation.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='qwen2.5:7b')
    parser.add_argument('--inference', action='store_true', help='Try one actual local inference only when the model is installed.')
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    result = check(args.model, args.inference)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.json:
        args.json.write_text(text + '\n', encoding='utf-8')
    return 0 if result['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
