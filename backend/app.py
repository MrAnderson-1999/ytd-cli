import os
import yt_dlp
import tempfile
import shutil
import zipfile
import time
from urllib.parse import quote
from logging.config import dictConfig

from flask import Flask, request, Response, stream_with_context, abort
from flask_cors import CORS

# 1) Structured logging configuration
# Configure console logging at DEBUG level with timestamps

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
# Enable CORS and expose Content-Disposition
CORS(app, resources={r"/download": {"origins": "*"}}, expose_headers=["Content-Disposition"])
app.logger.info("App startup complete")

@app.route('/health', methods=['GET'])
def health():
    app.logger.debug("Health check OK")
    return 'OK', 200

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    app.logger.exception("Unhandled exception during request")
    return {'error': 'Internal server error'}, 500

@app.route('/download', methods=['POST'])
def download():
    app.logger.info("=== New download request ===")
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    app.logger.debug(f"URL received: {url}")

    if not url:
        app.logger.warning("No URL provided")
        return {'error': 'No URL provided'}, 400

    # Create a temporary workspace
    tmpdir = tempfile.mkdtemp(prefix="ytdl_")
    app.logger.info(f"Created temp directory: {tmpdir}")

    # Progress hook for detailed logs
    def progress_hook(d):
        status = d.get('status')
        fname = d.get('filename') or d.get('_filename', '')
        if status == 'downloading':
            pct = d.get('_percent_str', '').strip()
            speed = d.get('_speed_str', '').strip()
            eta = d.get('_eta_str', '').strip()
            app.logger.info(f"Downloading {os.path.basename(fname)} — {pct} at {speed}, ETA {eta}")
        elif status == 'finished':
            app.logger.info(f"Finished downloading {os.path.basename(fname)}; now converting...")
        elif status == 'error':
            app.logger.error(f"Error downloading {os.path.basename(fname)}")

    # Configure yt-dlp options
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(tmpdir, '%(title)s.%(ext)s'),
        'quiet': True,
        'progress_hooks': [progress_hook],
    }
    app.logger.debug(f"yt-dlp options: {ydl_opts}")

    # Run download (handles single or playlist)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        app.logger.info("Starting yt-dlp download")
        info = ydl.extract_info(url, download=True)
        app.logger.info("yt-dlp download complete")

    # Detect playlist
    is_playlist = info.get('_type') == 'playlist'
    if is_playlist:
        playlist_title = info.get('title') or 'playlist'
        app.logger.info(f"Detected playlist: {playlist_title}")
        wav_files = [os.path.join(tmpdir, f)
                     for f in os.listdir(tmpdir) if f.lower().endswith('.wav')]
        app.logger.info(f"Found {len(wav_files)} WAV files for zipping")
        if not wav_files:
            app.logger.error("No WAVs found after playlist download")
            shutil.rmtree(tmpdir, ignore_errors=True)
            abort(500, "Playlist download failed")
        zip_name = f"{playlist_title}.zip"
        zip_path = os.path.join(tmpdir, zip_name)
        app.logger.info(f"Creating ZIP archive: {zip_name}")
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for wav in wav_files:
                app.logger.debug(f"Adding to zip: {wav}")
                zf.write(wav, arcname=os.path.basename(wav))
        stream_path = zip_path
        download_name = zip_name
        mime_type = 'application/zip'
    else:
        title = info.get('title') or 'audio'
        wav_path = os.path.join(tmpdir, f"{title}.wav")
        app.logger.info(f"Prepared single file: {title}.wav")
        if not os.path.exists(wav_path):
            app.logger.error("WAV file not found for single video")
            shutil.rmtree(tmpdir, ignore_errors=True)
            abort(500, "Download failed, file not found")
        stream_path = wav_path
        download_name = f"{title}.wav"
        mime_type = 'audio/wav'

    # Build Content-Disposition header
    ascii_name = download_name.encode('ascii', 'ignore').decode() or download_name
    encoded_name = quote(download_name)
    disposition = (
        f"attachment; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{encoded_name}"
    )
    app.logger.debug(f"Using Content-Disposition: {disposition}")

    # Streaming generator with low-level logs
    def generate():
        app.logger.info(f"Starting streaming: {stream_path}")
        start = time.monotonic()
        last = start
        part = 0
        try:
            with open(stream_path, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    part += 1
                    now = time.monotonic()
                    size = len(chunk)
                    app.logger.debug(
                        f"Chunk #{part}: {size} bytes | "
                        f"{now - start:.3f}s total | "
                        f"{now - last:.3f}s since last"
                    )
                    last = now
                    yield chunk
            total_time = time.monotonic() - start
            app.logger.info(f"Finished streaming {part} chunks in {total_time:.3f}s")
        finally:
            app.logger.info("Cleaning up temp directory")
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
