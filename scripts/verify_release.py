"""Verify a complete CI release before making its draft public.

python scripts/verify_release.py v0.5.0 artifacts/packages-v0.5.0 \
    --source <full-commit> --run-id <successful-build-run> --publish
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True)


def api(path):
    return json.loads(gh('api', path))


def verify(release, packages, count, source):
    files = {p.name: p for p in packages.iterdir() if p.is_file()}
    if len(files) != count+1 or 'SHA256SUMS.txt' not in files:
        raise ValueError('Local directory must contain exactly all packages and SHA256SUMS.txt')
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}
    manifest = {}
    for line in files['SHA256SUMS.txt'].read_text().splitlines():
        digest, name = line.split('  ', 1)
        if name in manifest:
            raise ValueError('Duplicate checksum entry')
        manifest[name] = digest
    if manifest != {name: digest for name, digest in hashes.items() if name != 'SHA256SUMS.txt'}:
        raise ValueError('Local package checksum manifest mismatch')
    assets = release['assets']
    if len(assets) != len(files) or {a['name'] for a in assets} != set(files):
        raise ValueError('Release upload incomplete; keep the release as a draft')
    for asset in assets:
        if asset['state'] != 'uploaded' or asset.get('digest') != 'sha256:'+hashes[asset['name']]:
            raise ValueError('Server checksum/state mismatch: '+asset['name'])
    if release['target_commitish'] != source:
        raise ValueError('Release target commit differs from the verified CI source')
    return hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag')
    parser.add_argument('packages', type=Path)
    parser.add_argument('--repo', default='413180794/MouseShare')
    parser.add_argument('--source', required=True)
    parser.add_argument('--run-id', required=True, type=int)
    parser.add_argument('--package-count', type=int, default=8)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    base = 'repos/'+args.repo
    run = api(base+'/actions/runs/'+str(args.run_id))
    if run['status'] != 'completed' or run['conclusion'] != 'success' or run['head_sha'] != args.source:
        raise ValueError('CI must have succeeded for the exact binary source commit')
    releases = api(base+'/releases?per_page=100')
    matches = [r for r in releases if r['tag_name'] == args.tag]
    if len(matches) != 1:
        raise ValueError('Expected one existing release for this tag')
    release = api(base+'/releases/'+str(matches[0]['id']))
    hashes = verify(release, args.packages, args.package_count, args.source)
    if args.publish:
        if not release['draft']:
            raise ValueError('Publish requires a verified draft')
        subprocess.run(['gh', 'release', 'edit', args.tag, '--repo', args.repo, '--draft=false', '--prerelease'], check=True)
        public = api(base+'/releases/'+str(release['id']))
        try:
            verify(public, args.packages, args.package_count, args.source)
            if public['draft']:
                raise ValueError('Release remains a draft')
        except Exception:
            subprocess.run(['gh', 'release', 'edit', args.tag, '--repo', args.repo, '--draft=true'], check=True)
            raise
        release = public
    print(json.dumps(dict(tag=args.tag, draft=release['draft'], verifiedAssets=len(hashes),
                          source=args.source, ci=args.run_id), ensure_ascii=False))


if __name__ == '__main__':
    main()
