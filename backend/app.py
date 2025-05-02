import os
import yt_dlp
import tempfile
import shutil
import zipfile
from urllib.parse import quote
from logging.config import dictConfig

from flask import Flask, request, Response, stream_with_context, abort
from flask_cors import CORS

# ———————————————————————————————————————————————
# 1) Structured logging (optional, but recommended)
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
            'level': 'INFO'
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    }
})

app = Flask(__name__)
CORS(app, resources={r"/download": {"origins": "*"}})
app.logger.info("App startup complete")

@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200

@app.route('/download', methods=['POST'])
def download():
    app.logger.info("Received /download request")
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        app.logger.warning("No URL provided")
        return {'error': 'No URL provided'}, 400

    # Create a temp workspace
    tmpdir = tempfile.mkdtemp(prefix="ytdl_")
    app.logger.debug(f"Using temp dir {tmpdir}")

    # Configure yt-dlp to drop files into our temp dir
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(tmpdir, '%(title)s.%(ext)s'),
        'quiet': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        app.logger.info("Starting yt-dlp.extract_info()")
        info = ydl.extract_info(url, download=True)
        app.logger.info("yt-dlp finished")

    # Determine whether we got a playlist or single
    is_playlist = info.get('_type') == 'playlist'
    if is_playlist:
        playlist_title = info.get('title') or 'playlist'
        app.logger.info(f"Detected playlist: {playlist_title!r}")
        # Collect all .wav files in tmpdir
        wav_files = [
            os.path.join(tmpdir, f)
            for f in os.listdir(tmpdir)
            if f.lower().endswith('.wav')
        ]
        if not wav_files:
            app.logger.error("No .wav files found after playlist download")
            shutil.rmtree(tmpdir)
            abort(500, "Playlist download failed")
        # Create a ZIP of them
        zip_name = f"{playlist_title}.zip"
        zip_path = os.path.join(tmpdir, zip_name)
        app.logger.info(f"Zipping {len(wav_files)} files into {zip_name}")
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for fpath in wav_files:
                zf.write(fpath, arcname=os.path.basename(fpath))
        stream_path = zip_path
        download_name = zip_name
        mime_type = 'application/zip'
    else:
        # Single-file case
        title = info.get('title') or 'audio'
        wav_path = os.path.join(tmpdir, f"{title}.wav")
        if not os.path.exists(wav_path):
            app.logger.error(f"Expected single WAV not found: {wav_path}")
            shutil.rmtree(tmpdir)
            abort(500, "Download failed, file not found")
        stream_path = wav_path
        download_name = f"{title}.wav"
        mime_type = 'audio/wav'
        app.logger.info(f"Prepared single file {download_name}")

    # Build a safe Content-Disposition header with RFC5987 fallback
    ascii_name = download_name.encode('ascii', 'ignore').decode() or download_name
    encoded_name = quote(download_name)
    disposition = (
        f"attachment; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{encoded_name}"
    )
    app.logger.debug(f"Content-Disposition: {disposition}")

    # Stream helper
    def generate():
        app.logger.info(f"Streaming file {stream_path}")
        try:
            with open(stream_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    yield chunk
        finally:
            app.logger.info("Cleaning up temporary files")
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
