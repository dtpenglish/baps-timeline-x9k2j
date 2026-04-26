#!/usr/bin/env python3
"""
rewrite-media-paths.py  v2.0
============================
Rewrites video and audio paths in events.json so large media points to
GitHub Releases (no per-file size limit, served via CDN), while photos
and small files remain inside the Pages-hosted folder.

Audio handling: only files larger than 24 MB go to Releases (one MP3 in
your case). Smaller audio stays local — keeping more files inside Pages
means fewer release-asset uploads.

Run BEFORE deploying. Produces events.v1.1.json next to the input
without overwriting the original.

Usage:
    python rewrite-media-paths.py events.json https://github.com/USER/REPO/releases/download/TAG

Example:
    python rewrite-media-paths.py events.json \\
        https://github.com/baps-pub/baps-timeline-x9k2j/releases/download/media-v1
"""
import sys
import json
import urllib.parse
from pathlib import Path

# Files in `files/` larger than this threshold go to Releases.
# Smaller stay local (i.e. shipped with the Pages site).
LARGE_FILE_THRESHOLD_MB = 24

def _encode_path_segment(name):
    """URL-encode a single filename so spaces/special chars work in URLs.
    We only encode the filename, not the whole URL, because the base URL
    already has its slashes and shouldn't be re-encoded."""
    return urllib.parse.quote(name, safe='')

def _rewrite_path(p, folder, base_url):
    """Rewrite 'video_files/foo.mp4' → '{base_url}/foo.mp4' (URL-encoded).

    GitHub Releases assets are flat (no subfolders). The asset name on
    the release is just the basename — we drop any folder prefix.

    Idempotent: if already an http(s) URL, returns unchanged."""
    if p.startswith('http://') or p.startswith('https://'):
        return p
    fname = p.lstrip('/').replace('\\', '/')
    # Strip the local folder prefix if present
    prefix = folder + '/'
    if fname.startswith(prefix):
        fname = fname[len(prefix):]
    # Use just the basename, encoded
    basename = fname.split('/')[-1]
    return f"{base_url}/{_encode_path_segment(basename)}"

def _rewrite_list(items, folder, base_url, size_lookup=None,
                  threshold_mb=LARGE_FILE_THRESHOLD_MB):
    """items can be either strings or dicts with a 'file' key.
    If size_lookup is provided (dict basename → size_bytes), only files
    larger than threshold_mb are rewritten; smaller ones kept local.
    """
    out = []
    rewritten = 0
    kept_local = 0
    for it in items:
        local_path = it if isinstance(it, str) else it.get('file', '')
        basename = local_path.split('/')[-1].split('\\')[-1]
        # Decide whether to rewrite
        rewrite_it = True
        if size_lookup is not None:
            sz = size_lookup.get(basename)
            if sz is not None and sz < threshold_mb * 1024 * 1024:
                rewrite_it = False
        if isinstance(it, str):
            if rewrite_it:
                out.append(_rewrite_path(it, folder, base_url))
                rewritten += 1
            else:
                out.append(it)
                kept_local += 1
        elif isinstance(it, dict) and 'file' in it:
            new_it = dict(it)
            if rewrite_it:
                new_it['file'] = _rewrite_path(it['file'], folder, base_url)
                rewritten += 1
            else:
                kept_local += 1
            out.append(new_it)
        else:
            out.append(it)
    return out, rewritten, kept_local

def _build_size_lookup(media_root, folder):
    """Walk media_root/folder/ and return {basename: bytes}. Used for
    audio files where we want to rewrite only the large ones."""
    if not media_root:
        return None
    p = Path(media_root) / folder
    if not p.exists():
        return None
    return {f.name: f.stat().st_size for f in p.iterdir() if f.is_file()}

def rewrite(events, base_url, media_root=None):
    base_url = base_url.rstrip('/')
    audio_size_lookup = _build_size_lookup(media_root, 'files')
    counts = {'video': 0, 'audio_to_releases': 0, 'audio_kept_local': 0,
              'photo_kept_local': 0, 'pdf_kept_local': 0, 'youtube_kept': 0}
    for ev in events:
        m = ev.get('media') or {}
        # Videos: ALL go to releases (every video is large)
        if 'video' in m:
            m['video'], n_rw, _ = _rewrite_list(m['video'], 'video_files', base_url)
            counts['video'] += n_rw
        # Audio: only the >24 MB ones, IF we have size info; otherwise rewrite all
        if 'audio' in m:
            m['audio'], n_rw, n_local = _rewrite_list(
                m['audio'], 'files', base_url, audio_size_lookup)
            counts['audio_to_releases'] += n_rw
            counts['audio_kept_local']  += n_local
        # Photos, PDFs, YouTube: leave alone
        counts['photo_kept_local'] += len(m.get('photos', []))
        counts['pdf_kept_local']   += len(m.get('pdf', []))
        counts['youtube_kept']     += len(m.get('youtube', []))
    return events, counts

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1])
    base_url = sys.argv[2]
    media_root = sys.argv[3] if len(sys.argv) > 3 else None

    if not src.exists():
        print(f"Not found: {src}")
        sys.exit(1)

    data = json.loads(src.read_text(encoding='utf-8'))
    if isinstance(data, list):
        events = data
        wrapped = False
    else:
        events = data.get('events', [])
        wrapped = True

    events, counts = rewrite(events, base_url, media_root)

    if wrapped:
        data['events'] = events
    else:
        data = events

    out = src.with_name(src.stem + '.v1.1' + src.suffix)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                   encoding='utf-8')

    print(f"Wrote: {out}")
    print(f"  Videos rewritten to Releases:     {counts['video']}")
    print(f"  Audio rewritten to Releases:      {counts['audio_to_releases']}")
    print(f"  Audio kept local (under {LARGE_FILE_THRESHOLD_MB} MB):    {counts['audio_kept_local']}")
    print(f"  Photos kept local:                {counts['photo_kept_local']}")
    print(f"  PDFs kept local:                  {counts['pdf_kept_local']}")
    print(f"  YouTube IDs kept:                 {counts['youtube_kept']}")
    print()
    if media_root is None:
        print("Note: ran without media_root, so ALL audio rewritten to Releases.")
        print("To keep small audio local, pass the media folder path as 3rd arg:")
        print("  python rewrite-media-paths.py events.json BASE_URL "
              "\"E:\\AVDWork\\AVD_Current\\For checking\\IT\\BAPS History\\BAPS Timeline\"")

if __name__ == "__main__":
    main()
