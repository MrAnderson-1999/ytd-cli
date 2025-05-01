from flask import Flask, request, Response, stream_with_context
import yt_dlp
import os

app = Flask(__name__)

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return {'error': 'No URL provided'}, 400

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'outtmpl': 'audio.%(ext)s',
        'quiet': True,
    }

    def generate():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for chunk in ydl.download([url]):
                pass  # yt-dlp handles file creation
        # stream the file as it's created
        with open('audio.wav', 'rb') as f:
            while True:
                data = f.read(4096)
                if not data:
                    break
                yield data
        os.remove('audio.wav')

    headers = {
        'Content-Disposition': 'attachment; filename="audio.wav"',
        'Content-Type': 'audio/wav'
    }
    return Response(stream_with_context(generate()), headers=headers)
