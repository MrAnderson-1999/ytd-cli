import os
import yt_dlp
import tempfile
import shutil
import zipfile
import time
from urllib.parse import quote
from logging.config import dictConfig

from flask import Flask, request, jsonify, Response, stream_with_context, abort
from flask_cors import CORS
from yt_dlp.utils import DownloadError

# ———————————————————————————————————————————————
# 1) Structured logging configuration
# ———————————————————————————————————————————————
dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'level': 'DEBUG'
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    }
})

app = Flask(__name__)
# Expose both endpoints with proper CORS, including Content-Disposition header
CORS(app,
     resources={r"/info": {"origins": "*"},
                r"/download": {"origins": "*"}},
     expose_headers=["Content-Disposition"])
app.logger.info("App startup complete")

# ———————————————————————————————————————————————
# 2) Metadata-only endpoint for frontend preview
# ———————————————————————————————————————————————
@app.route('/info', methods=['POST'])
def info():
    data = request.get_json() or {}
    url  = data.get('url', '').strip()
    if not url:
        return jsonify(error="No URL provided"), 400

    app.logger.info(f"Fetching metadata for: {url!r}")
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'format': 'bestaudio/best',
        'ignoreerrors': True,  # skip DRM/unavailable entries :contentReference[oaicite:4]{index=4}
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)  # throws DownloadError on DRM :contentReference[oaicite:5]{index=5}
    except DownloadError as e:
        app.logger.error(f"Metadata fetch failed: {e}")
        return jsonify(error=str(e)), 502

    # Playlist vs single detection
    if info.get('_type') == 'playlist':
        title     = info.get('title') or 'playlist'
        thumbnail = (info.get('thumbnails') or [])[-1].get('url') if info.get('thumbnails') else None
        entries   = []
        for entry in info.get('entries') or []:
            if not entry:
                app.logger.warning("Skipping an unavailable playlist entry")  # DRM or removed :contentReference[oaicite:6]{index=6}
                continue
            e_title     = entry.get('title')
            e_id        = entry.get('id')
            thumb       = (entry.get('thumbnails') or [])[-1].get('url') if entry.get('thumbnails') else thumbnail
            exts        = sorted({f.get('ext') for f in entry.get('formats', []) if f.get('ext')})
            entries.append({
                'id':        e_id,
                'title':     e_title,
                'thumbnail': thumb,
                'formats':   exts
            })
        return jsonify({
            'type':      'playlist',
            'title':     title,
            'thumbnail': thumbnail,
            'entries':   entries
        })
    else:
        # Single video/track
        title     = info.get('title') or 'audio'
        thumbnail = (info.get('thumbnails') or [])[-1].get('url') if info.get('thumbnails') else None
        exts      = sorted({f.get('ext') for f in info.get('formats', []) if f.get('ext')})
        return jsonify({
            'type':      'video',
            'title':     title,
            'thumbnail': thumbnail,
            'formats':   exts
        })

# ———————————————————————————————————————————————
# 3) Download endpoint with DRM/error handling
# ———————————————————————————————————————————————
@app.route('/download', methods=['POST'])
def download():
    data = request.get_json() or {}
    # Legacy support: wrap single URL into items list
    if 'url' in data and 'items' not in data:
        data = {'items': [{'url': data['url'], 'format': 'wav'}]}

    items = data.get('items') or []
    if not items:
        return jsonify(error="No download items provided"), 400

    app.logger.info(f"Processing download of {len(items)} item(s)")
    tmpdir = tempfile.mkdtemp(prefix="ytdl_")
    downloaded = []

    # Loop through each requested item
    for idx, it in enumerate(items, 1):
        item_url   = it.get('url')
        out_format = it.get('format', 'wav')
        safe_name  = f"item_{idx}"
        ydl_opts   = {
            'format': 'bestaudio/best',
            'quiet': True,
            'ignoreerrors': True,     # skip DRM/unplayable items :contentReference[oaicite:7]{index=7}
            'outtmpl': os.path.join(tmpdir, safe_name + '.%(ext)s')
        }
        pp = []
        if out_format in ('wav','mp3','flac'):
            pp.append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': out_format,
                'preferredquality': '192',
            })
        ydl_opts['postprocessors'] = pp

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                app.logger.info(f"Downloading item #{idx}: {item_url}")
                info = ydl.extract_info(item_url, download=True)  # may raise DownloadError :contentReference[oaicite:8]{index=8}
        except DownloadError as e:
            app.logger.error(f"Error downloading {item_url}: {e}")
            continue

        if info is None:
            app.logger.warning(f"Skipping item #{idx}, no info returned (DRM or unsupported)")
            continue

        try:
            # Build filename from template, skip None info
            out_fname = ydl.prepare_filename(info).rsplit('.',1)[0] + f".{out_format}"
        except Exception as e:
            app.logger.error(f"Failed to prepare filename for item #{idx}: {e}")
            continue

        downloaded.append(out_fname)

    # No successful downloads?
    if not downloaded:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return jsonify(error="All items failed or were DRM-protected"), 502

    # Multiple vs single file response
    if len(downloaded) > 1:
        zip_name = "bundle.zip"
        zip_path = os.path.join(tmpdir, zip_name)
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for f in downloaded:
                path = os.path.join(tmpdir, f)
                if os.path.exists(path):
                    zf.write(path, arcname=f)
        stream_path   = zip_path
        download_name = zip_name
        mime_type     = 'application/zip'
    else:
        download_name = downloaded[0]
        stream_path   = os.path.join(tmpdir, download_name)
        mime_type     = (
            'audio/wav' if download_name.lower().endswith('.wav')
            else 'audio/mpeg'
        )

    # Build RFC5987 Content-Disposition
    ascii_name   = download_name.encode('ascii','ignore').decode() or download_name
    encoded_name = quote(download_name)
    disposition  = (
        f"attachment; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{encoded_name}"
    )
    app.logger.info(f"Streaming back: {download_name}")

    def generate():
        try:
            with open(stream_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    yield chunk
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return Response(
        stream_with_context(generate()),
        headers={
            'Content-Disposition': disposition,
            'Content-Type': mime_type
        },
        mimetype=mime_type
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
