#!/usr/bin/env python3
"""Prepare a new-identity HA backup without modifying the original or its data."""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import tarfile
import uuid

MAX_BYTES = 256 * 1024 * 1024
OLD_SLUG = 'cma-event-pipeline'
NEW_SLUG = 'video-event-monitor'
IMAGE = 'ghcr.io/chronoaiproject/video-event-monitor-ha'


def members(archive):
    rows, total = {}, 0
    for item in archive:
        name = item.name.removeprefix('./')
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or not (item.isfile() or item.isdir()):
            raise ValueError('Backup contains unsafe paths or unsupported member types')
        if name in rows or len(rows) >= 8192:
            raise ValueError('Backup contains duplicate or excessive members')
        total += item.size
        if total > MAX_BYTES:
            raise ValueError('Backup exceeds migration size limit')
        rows[name] = item
    return rows


def raw(archive, item):
    if not item.isfile():
        raise ValueError('Expected a regular backup file')
    with archive.extractfile(item) as stream:
        return stream.read(MAX_BYTES + 1)


def add_json(archive, name, value):
    content = json.dumps(value, ensure_ascii=False, indent=2).encode()
    item = tarfile.TarInfo(name)
    item.mode, item.size = 0o600, len(content)
    archive.addfile(item, io.BytesIO(content))


def prepare(source, target, version):
    """Return an unencrypted single-add-on backup; preserve every data byte."""
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-alpha\.\d+)?', version):
        raise ValueError('Invalid target version')
    source, target = Path(source), Path(target)
    if source.stat().st_size > MAX_BYTES:
        raise ValueError('Backup exceeds migration size limit')
    with tarfile.open(source, 'r:*') as outer:
        rows = members(outer)
        metadata = json.loads(raw(outer, rows['backup.json']))
        addons = metadata.get('addons', [])
        if (metadata.get('protected') or metadata.get('type') != 'partial'
                or metadata.get('homeassistant') or metadata.get('folders')
                or len(addons) != 1):
            raise ValueError('Use an unencrypted partial backup of only the old monitor')
        old = addons[0]['slug']
        if not old.endswith('_' + OLD_SLUG):
            raise ValueError('Backup is not the old monitor add-on')
        new = old[:-len(OLD_SLUG)] + NEW_SLUG
        suffix = '.tar.gz' if metadata.get('compressed') else '.tar'
        inner_bytes = raw(outer, rows[old + suffix])
    output = io.BytesIO()
    hashes = {}
    with tarfile.open(fileobj=io.BytesIO(inner_bytes), mode='r:*') as inner:
        rows = members(inner)
        addon = json.loads(raw(inner, rows['addon.json']))
        if addon['system']['slug'] not in (OLD_SLUG, old):
            raise ValueError('Inner and outer add-on identities differ')
        addon['version'] = addon['system']['version'] = addon['user']['version'] = version
        addon['system'].update(slug=NEW_SLUG, name='Video Event Monitor', image=IMAGE,
                               panel_title='Video Event Monitor',
                               url='https://github.com/ChronoAIProject/nyx-homeassistant-node/tree/main/' + NEW_SLUG)
        addon['user'].update(image=IMAGE, uuid=uuid.uuid4().hex, ingress_panel=False,
                             ingress_token=secrets.token_hex(32), access_token=secrets.token_hex(56))
        # Never auto-start a second writer or background worker during restoration.
        addon['state'] = 'stopped'
        with tarfile.open(fileobj=output, mode='w:gz' if metadata.get('compressed') else 'w') as staged:
            add_json(staged, './addon.json', addon)
            for name, item in rows.items():
                if name == 'addon.json':
                    continue
                if name in ('image.tar', 'apparmor.txt'):
                    raise ValueError('Custom image/AppArmor backups need manual review')
                if item.isdir():
                    staged.addfile(copy.copy(item))
                else:
                    content = raw(inner, item)
                    hashes[name] = hashlib.sha256(content).hexdigest()
                    staged.addfile(copy.copy(item), io.BytesIO(content))
    metadata.update(slug=secrets.token_hex(4), name='Video Event Monitor identity migration',
                    addons=[{**addons[0], 'slug':new, 'name':'Video Event Monitor', 'version':version}])
    # Exclusive creation also prevents accidental overwrite of the rollback backup.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream, tarfile.open(fileobj=stream, mode='w') as result:
            content = output.getvalue()
            item = tarfile.TarInfo(new + suffix)
            item.mode, item.size = 0o600, len(content)
            result.addfile(item, io.BytesIO(content))
            add_json(result, './backup.json', metadata)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {'source_slug':old, 'target_slug':new, 'backup_slug':metadata['slug'],
            'target_version':version, 'preserved_file_sha256':hashes, 'state':'stopped'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('--target-version', required=True)
    args = parser.parse_args()
    report = prepare(args.source, args.target, args.target_version)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
