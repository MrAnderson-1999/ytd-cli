from flask import Flask, request, Response, stream_with_context, abort
import yt_dlp
import os

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return {'error': 'No URL provided'}, 400

    # 1) Use the original outtmpl pattern
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

    # 2) Download and capture the info dict to get the title
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Build the filename based on the downloaded title
    title = info.get('title')
    if not title:
        abort(500, 'Failed to determine output filename')
    filename = f"{title}.wav"

    # 3) Stream the file back to the client
    def generate():
        try:
            with open(filename, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    yield chunk
        finally:
            # Clean up the file even if the client disconnects
            try:
                os.remove(filename)
            except OSError:
                pass

    headers = {
        'Content-Disposition': f'attachment; filename="{title}.wav"',
        'Content-Type': 'audio/wav',
    }
    return Response(
        stream_with_context(generate()),
        headers=headers,
        mimetype='audio/wav'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
