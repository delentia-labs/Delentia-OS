"""Repair this task's proxy hostname mapping without copying VFS containers.

No model download, image commit, container recreation/removal or TLS override.
Use --check for a read-only check; default repairs only a dedicated proxy entry.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request

NAME = 'codex-delentia-ollama-20261022'
CACHE = '/workspace/.cache/ollama-models'
MIN_FREE = 2 * 4683086845 + 2 * 1024**3

def docker(*args, data=None):
    result = subprocess.run(['docker', *args], input=data, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('task Docker operation failed; no credentials emitted')
    return result.stdout

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    info = json.loads(docker('inspect', NAME))[0]
    if not any(m.get('Source') == CACHE and m.get('Destination') == '/root/.ollama/models' for m in info['Mounts']):
        raise RuntimeError('refuse a service with a different model cache')
    ports = info['HostConfig']['PortBindings']['11434/tcp']
    if not ports or any(p['HostIp'] != '127.0.0.1' or p['HostPort'] != '11434' for p in ports):
        raise RuntimeError('refuse non-loopback or unexpected bindings')
    env = dict(x.split('=', 1) for x in info['Config']['Env'] if '=' in x)
    current = urllib.parse.urlsplit(os.environ.get('HTTPS_PROXY', ''))
    configured = urllib.parse.urlsplit(env.get('HTTPS_PROXY', ''))
    if not current.hostname or current.hostname != configured.hostname or current.port != configured.port:
        raise RuntimeError('proxy configuration differs; automatic container recreation is disabled')
    try:
        socket.inet_aton(current.hostname)
    except OSError:
        pass
    else:
        raise RuntimeError('an explicit IP proxy needs separate configuration refresh')
    address = socket.gethostbyname(current.hostname)
    if not info['State']['Running']:
        if args.check:
            print(json.dumps({'running': False, 'changed': False}));return 1
        docker('start', NAME)
    old = docker('exec', NAME, 'cat', '/etc/hosts')
    lines = []; matches = 0
    for line in old.splitlines():
        fields = line.split('#', 1)[0].split()
        if current.hostname in fields[1:]:
            if len(fields) != 2:
                raise RuntimeError('refuse ambiguous proxy aliases')
            line = address + '\t' + current.hostname;matches += 1
        lines.append(line)
    if matches != 1:
        raise RuntimeError('require one existing dedicated proxy hostname entry')
    new = '\n'.join(lines) + '\n';changed = old != new
    if changed and not args.check:
        backup = Path('/workspace/.delentia-cloud/ollama-hosts-before-refresh.txt')
        if not backup.exists():
            backup.write_text(old, encoding='utf-8');backup.chmod(0o600)
        docker('exec', '-i', NAME, 'sh', '-c', 'cat > /etc/hosts', data=new)
        if docker('exec', NAME, 'cat', '/etc/hosts') != new:
            raise RuntimeError('proxy hostname mapping readback differs')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    ready = False
    for _ in range(10):
        try:
            with opener.open('http://127.0.0.1:11434/api/tags', timeout=2) as response:
                ready = response.status == 200 and isinstance(json.load(response).get('models'), list)
            if ready:break
        except OSError:
            pass
        time.sleep(0.25)
    free = shutil.disk_usage('/workspace').free
    print(json.dumps({'running': True, 'proxy_mapping_stale': changed if args.check else False,
                      'changed': changed and not args.check, 'tags_api_ready': ready,
                      'free_bytes_after_service_start': free, 'minimum_model_free_bytes': MIN_FREE,
                      'model_download_headroom_ready': free >= MIN_FREE,
                      'container_recreated': False, 'tls_verification_disabled': False}))
    return 0 if ready and not (args.check and changed) else 1

if __name__ == '__main__':
    raise SystemExit(main())
