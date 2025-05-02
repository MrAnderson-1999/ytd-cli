import os
import tempfile
import shutil
import zipfile
import time
from urllib.parse import quote
from logging.config import dictConfig

from flask import Flask, request, jsonify, Response, stream_with_context, abort
from flask_cors import CORS
import yt_dlp
from yt_dlp.utils import DownloadError

# ———————————————————————————————————————————————
# 1) Logging Configuration
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
CORS(app,
     resources={r"/download": {"origins": "*"},
                r"/info":     {"origins": "*"}},
     expose_headers=["Content-Disposition"])

app.logger.info("App startup complete")

# ———————————————————————————————————————————————
# 2) Metadata-only endpoint
# ———————————————————————————————————————————————
@app.route('/info', methods=['POST'])
def info():
    """
    Returns JSON metadata for a given URL without downloading.
    {
      type: "video" | "playlist",
      title: "...",
      thumbnail: "...",
      formats: [ "wav","mp3","flac", ... ],        # for single
      entries: [                                  # for playlist
        { id, title, thumbnail, formats: [...] },
        ...
      ]
    }
    """
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify(error="No URL provided"), 400

    app.logger.info(f"Fetching metadata for URL: {url!r}")
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        # get all format info
        'format': 'bestaudio/best',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        app.logger.error(f"Metadata fetch error: {e}")
        return jsonify(error=str(e)), 502

    # common fields
    video_type = info.get('_type', 'video')
    if video_type == 'playlist':
        # Playlist/show: list entries
        title     = info.get('title') or 'playlist'
        thumbnail = info.get('thumbnails') and info['thumbnails'][-1].get('url')
        entries   = []
        for entry in info.get('entries', []):
            if not entry:
                continue
            e_title     = entry.get('title')
            e_id        = entry.get('id')
            # thumbnail fallback
            thumb       = (entry.get('thumbnails') and entry['thumbnails'][-1].get('url')) or thumbnail
            # collect available formats by extension
            exts        = sorted({f.get('ext') for f in entry.get('formats', []) if f.get('ext')})
            entries.append({
                'id':        e_id,
                'title':     e_title,
                'thumbnail': thumb,
                'formats':   exts,
            })
        return jsonify({
            'type':      'playlist',
            'title':     title,
            'thumbnail': thumbnail,
            'entries':   entries
        })
    else:
        # Single video/episode/track
        title     = info.get('title') or 'audio'
        thumbnail = info.get('thumbnails') and info['thumbnails'][-1].get('url')
        # available formats
        exts      = sorted({f.get('ext') for f in info.get('formats', []) if f.get('ext')})
        return jsonify({
            'type':      'video',
            'title':     title,
            'thumbnail': thumbnail,
            'formats':   exts
        })


# ———————————————————————————————————————————————
# 3) Download endpoint (as before)
# ———————————————————————————————————————————————
@app.route('/download', methods=['POST'])
def download():
    """
    Accepts:
      {
        items: [
          { id: "...", url: "...", format: "wav"|"mp3"|"flac" },
          ...
        ]
      }
    or (legacy):
      { url: "..." }
    Streams back a single .wav/.mp3/.zip based on selection.
    """
    data = request.get_json() or {}
    # backwards‐compat: single URL request
    if 'url' in data and 'items' not in data:
        # wrap single URL into items list
        data = {'items': [{ 'id': data['url'], 'url': data['url'], 'format': 'wav' }]}

    items = data.get('items') or []
    if not items:
        return jsonify(error="No download items provided"), 400

    app.logger.info(f"Download request for {len(items)} item(s)")

    # Create temp dir to store files
    tmpdir = tempfile.mkdtemp(prefix="ytdl_")
    app.logger.debug(f"Temp workspace: {tmpdir}")

    downloaded = []
    ydl_opts = {
        'quiet': True,
        'format': 'bestaudio/best',
        'ignoreerrors': True,
    }

    # Download each item separately into tmpdir
    for idx, it in enumerate(items, 1):
        item_url    = it.get('url')
        out_format  = it.get('format', 'wav')
        safe_title  = f"item_{idx}"
        ydl_opts['outtmpl'] = os.path.join(tmpdir, safe_title + '.%(ext)s')

        # Postprocessor for audio conversion
        # FLAC & MP3 via ffmpeg; WAV via postprocessor
        pp = []
        if out_format == 'wav':
            pp = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }]
        elif out_format in ('mp3','flac'):
            pp = [{ 'key': 'FFmpegExtractAudio', 'preferredcodec': out_format }]
        ydl_opts['postprocessors'] = pp

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                app.logger.info(f"Downloading item #{idx}: {item_url}")
                info = ydl.extract_info(item_url, download=True)
                # pick the resulting filename
                fname = ydl.prepare_filename(info).rsplit('.',1)[0] + f".{out_format}"
                downloaded.append(fname)
        except DownloadError as e:
            app.logger.error(f"Failed to download {item_url}: {e}")

    # If multiple items, zip them; else return the single file
    if len(downloaded) > 1:
        zip_name = "bundle.zip"
        zip_path = os.path.join(tmpdir, zip_name)
        with zipfile.ZipFile(zip_path,'w') as zf:
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
        mime_type     = download_name.lower().endswith('.wav') and 'audio/wav' or 'application/octet-stream'

    # Build safe Content-Disposition header
    ascii_name   = download_name.encode('ascii','ignore').decode() or download_name
    encoded_name = quote(download_name)
    disposition  = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded_name}"

    app.logger.info(f"Streaming back {download_name}")
    def generate():
        try:
            with open(stream_path,'rb') as f:
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
