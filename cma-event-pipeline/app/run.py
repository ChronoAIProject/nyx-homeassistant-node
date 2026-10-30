"""Initialize a private durable directory, optionally restore once, then drop UID."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from options import environment

sys.path.insert(0, '/app')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    os.umask(0o077)
    state = Path('/data/state')
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state.is_symlink():
        raise ValueError('State directory cannot be a symlink')
    options = json.loads(Path('/data/options.json').read_text())
    settings = environment(options, state)
    if os.getuid() == 0:
        # HA owns /data; allow the runtime to traverse to its private child even
        # when a fresh volume starts as 0700. Keep the parent owned by root so
        # UID 1000 cannot replace Supervisor's private options.json.
        Path('/data').chmod(0o711)
        os.chown(state, 1000, 1000)
        os.setgroups([])
        os.setgid(1000)
        os.setuid(1000)
    state.chmod(0o700)
    os.environ.pop('SUPERVISOR_TOKEN', None)
    os.environ.update(settings)
    from config import Config
    from state_transfer import MAX_EXPORT_BYTES, restore_state
    config = Config.from_env()
    url = options.get('state_import_url', '')
    if url and not any(state.glob('*.sqlite3')):
        origin = urlsplit(url)
        if origin.scheme != 'https' or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment:
            raise ValueError('State import requires an HTTPS export URL without query or credentials')
        request = Request(url, headers={'Authorization': 'Bearer ' + config.api_token,
                                       'User-Agent': 'cma-event-pipeline-ha/0.2.1'})
        with build_opener(NoRedirect).open(request, timeout=50) as response:
            raw = response.read(MAX_EXPORT_BYTES + 1)
        if len(raw) > MAX_EXPORT_BYTES:
            raise ValueError('State import exceeds the supported size')
        count = restore_state(json.loads(raw), state, config.pipeline)
        print('Restored %d pipeline database(s) into local storage.' % count, flush=True)
    os.chdir('/app')
    os.execv('/app/.venv/bin/uvicorn', [
        'uvicorn', 'service:app', '--host', '0.0.0.0', '--port', '8080', '--no-access-log', '--no-proxy-headers',
    ])


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Configuration can include credentials; do not dump it in add-on logs.
        print('CMA Event Pipeline startup failed (%s); check private options and upstream availability.' % type(exc).__name__, file=sys.stderr)
        sys.exit(1)
