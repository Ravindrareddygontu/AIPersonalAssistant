"""Speech-to-Text route using OpenAI Voice provider directly."""
import os
import logging

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import JSONResponse

from backend.ai_middleware.providers.openai.voice import OpenAIVoiceProvider

log = logging.getLogger(__name__)
speech_router = APIRouter()

# Initialize the voice provider (singleton)
_voice_provider = None


def get_voice_provider() -> OpenAIVoiceProvider:
    """Get or create the voice provider instance."""
    global _voice_provider
    if _voice_provider is None:
        api_key = os.environ.get('OPENAI_API_KEY')
        _voice_provider = OpenAIVoiceProvider(api_key=api_key)
    return _voice_provider


def _log_request(method: str, url: str, data=None):
    """Log incoming request."""
    if data:
        log.info(f"[REQUEST] {method} {url} | data: {data}")
    else:
        log.info(f"[REQUEST] {method} {url}")


def _log_response(method: str, url: str, status: int, data=None):
    """Log outgoing response."""
    log.info(f"[RESPONSE] {method} {url} | Status: {status}")


@speech_router.post('/api/speech-to-text')
async def speech_to_text(request: Request, audio: UploadFile = File(...)):
    """
    Convert speech audio to text using OpenAI Voice provider.

    Expects: multipart/form-data with 'audio' file
    Returns: { "text": "transcribed text", "success": true }
    """
    url = str(request.url)
    _log_request('POST', url)

    if not audio or audio.filename == '':
        _log_response('POST', url, 400)
        return JSONResponse(
            content={'success': False, 'error': 'No audio file provided'},
            status_code=400
        )

    try:
        # Read audio data
        audio_data = await audio.read()
        filename = audio.filename or 'recording.webm'

        # Determine audio format from filename
        audio_format = 'webm'
        if '.' in filename:
            audio_format = filename.rsplit('.', 1)[-1].lower()

        log.info(f"[SPEECH] Received audio: {len(audio_data)} bytes, format: {audio_format}")

        # Use OpenAI Voice provider directly
        provider = get_voice_provider()
        result = await provider.voice_to_text(
            audio_data=audio_data,
            audio_format=audio_format,
            language='en'
        )

        text = result.text.strip()
        log.info(f"[SPEECH] Transcribed: {text[:100]}...")
        _log_response('POST', url, 200)

        return {'success': True, 'text': text}

    except Exception as e:
        log.exception(f"[SPEECH] Error processing audio: {e}")
        _log_response('POST', url, 500)
        return JSONResponse(
            content={'success': False, 'error': str(e)},
            status_code=500
        )


@speech_router.get('/api/speech-to-text/status')
async def speech_service_status():
    """Check if speech service is available."""
    try:
        provider = get_voice_provider()
        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key:
            return {
                'available': True,
                'provider': 'openai-voice',
                'model': provider.default_stt_model
            }
    except Exception as e:
        log.warning(f"[SPEECH] Speech service check failed: {e}")

    return {
        'available': False,
        'error': 'OpenAI API key not configured'
    }

