import os
import yt_dlp
import logging
from logging.config import dictConfig
from urllib.parse import quote

from flask import Flask, request, Response, stream_with_context, abort
from flask_cors import CORS

# 1. Configure structured logging
dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S %z'
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
# 2. Enable CORS only on the /download route
CORS(app, resources={r"/download": {"origins": "*"}})

app.logger.info("Flask application startup complete")

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    app.logger.exception("Unhandled exception during request")
    return {'error': 'Internal server error'}, 500

@app.route('/health', methods=['GET'])
def health():
    app.logger.debug("Health check requested")
    return 'OK', 200

@app.route('/download', methods=['POST'])
def download():
    app.logger.info("===== New download request received =====")
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    app.logger.debug(f"Parsed URL from request: {url!r}")

    if not url:
        app.logger.warning("No URL provided in request payload")
        return {'error': 'No URL provided'}, 400

    # 3. Configure yt-dlp options
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'outtmpl': '%(title)s.%(ext)s',
        'quiet': True,
    }
    app.logger.debug(f"yt-dlp options: {ydl_opts}")

    # 4. Download and convert
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        app.logger.info("Starting download + conversion via yt-dlp")
        info = ydl.extract_info(url, download=True)
        app.logger.info(f"Download complete: title={info.get('title')}")

        # Compute the original filename and swap extension
        raw_path = ydl.prepare_filename(info)
    base, _ = os.path.splitext(raw_path)
    wav_path = base + '.wav'
    app.logger.debug(f"Computed WAV file path: {wav_path}")

    # 5. Verify file exists
    if not os.path.exists(wav_path):
        app.logger.error(f"Expected WAV file not found: {wav_path}")
        abort(500, f"Download failed, file not found: {wav_path!r}")

    # 6. Stream file contents back to the client
    def generate():
        app.logger.info(f"Beginning streaming of {wav_path}")
        try:
            with open(wav_path, 'rb') as f:
                chunk_num = 0
                for chunk in iter(lambda: f.read(8192), b''):
                    chunk_num += 1
                    app.logger.debug(f"Yielding chunk #{chunk_num} ({len(chunk)} bytes)")
                    yield chunk
            app.logger.info("Finished streaming file")
        except Exception:
            app.logger.exception("Error during streaming")
            raise
        finally:
            try:
                os.remove(wav_path)
                app.logger.info(f"Removed temporary file {wav_path}")
            except OSError:
                app.logger.exception(f"Failed to remove temporary file {wav_path}")

    # 7. Build RFC5987-compliant Content-Disposition header
    title = info.get('title', 'audio')
    ascii_title = title.encode('ascii', 'ignore').decode() or 'audio'
    encoded_title = quote(title)
    disposition = (
        f"attachment; "
        f'filename="{ascii_title}.wav"; '
        f"filename*=UTF-8''{encoded_title}.wav"
    )
    app.logger.debug(f"Using Content-Disposition header: {disposition}")

    return Response(
        stream_with_context(generate()),
        headers={
            'Content-Disposition': disposition,
            'Content-Type': 'audio/wav'
        },
        mimetype='audio/wav'
    )

if __name__ == '__main__':
    app.logger.info("Launching development server")
    app.run(host='0.0.0.0', port=5000)
