from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
import boto3
import base64
import json
import unicodedata
import random
import string
import io
import requests as req_lib
from datetime import datetime, timedelta
from typing import List, Optional
from auth import hash_password, verify_password, create_access_token, get_current_user, get_current_user_optional, validate_password
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()

app = FastAPI()
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse as _JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for e in exc.errors():
        safe_error = {k: str(v) if isinstance(v, bytes) else v for k, v in e.items()}
        errors.append(safe_error)
    return _JSONResponse(status_code=422, content={"detail": errors})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URL = os.getenv("MONGO_URL")
client = AsyncIOMotorClient(MONGO_URL)
db = client["tinytales"]
users_collection = db["users"]
profiles_collection = db["profiles"]

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

polly = boto3.client('polly', region_name='us-east-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

# ── ElevenLabs TTS configuration (primary provider, Polly as fallback) ──
USE_ELEVENLABS = True
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')

ELEVENLABS_VOICES = {
    'fr': {
        'narrator': 'ucMmKRQbfDEYyb2IIGax',
        'male':     'GFj5Qf6cNQ3Lgp8VKBwc',
        'female':   'F1toM6PcP54s45kOOAyV',
        'child':    'AqX3O1nij56oCicN2U6w',
    },
    'en': {
        'narrator': 'cVd39cx0VtXNC13y5Y7z',
        'male':     'sB7vwSCyX0tQmU24cW2C',
        'female':   'DODLEQrClDo8wCz460ld',
        'child':    'iukn3a1vSSNFmdi5NZS4',
    },
    'es': {
        'narrator': '1eHrpOW5l98cxiSRjbzJ',
        'male':     '1eHrpOW5l98cxiSRjbzJ',
        'female':   '1eHrpOW5l98cxiSRjbzJ',
        'child':    '1eHrpOW5l98cxiSRjbzJ',
    },
    'ar': {
        'narrator': 'mRdG9GYEjJmIzqbYTidv',
        'male':     'mRdG9GYEjJmIzqbYTidv',
        'female':   'mRdG9GYEjJmIzqbYTidv',
        'child':    'mRdG9GYEjJmIzqbYTidv',
    },
}

# Mapping from Polly voice names to ElevenLabs roles
POLLY_TO_ELEVENLABS_ROLE = {
    'Joanna':   'narrator', 'Lea':    'narrator',
    'Lupe':     'narrator', 'Zeina':  'narrator',
    'Matthew':  'male',     'Mathieu': 'male',     'Miguel': 'male',
    'Amy':      'female',   'Celine':  'female',   'Penelope': 'female',
}

POLLY_VOICES = {
    'en': {'narrator': 'Joanna', 'character1': 'Matthew', 'character2': 'Amy'},
    'fr': {'narrator': 'Lea',    'character1': 'Mathieu', 'character2': 'Celine'},
    'es': {'narrator': 'Lupe',   'character1': 'Miguel',  'character2': 'Penelope'},
    'ar': {'narrator': 'Zeina',  'character1': 'Zeina',   'character2': 'Zeina'},
}

STORY_OPENINGS = [
    "Once upon a time",
    "In a land not so far away",
    "Long ago, in a tiny village",
    "On a rainy Tuesday morning",
    "Deep in the heart of the forest",
    "High up on a golden hill",
    "Not far from the sea",
    "In a cozy little house at the edge of town",
    "On the day everything changed",
    "There was once",
    "Many moons ago",
    "In the smallest corner of a big wide world",
    "On a morning when the sky turned three colors at once",
    "Beneath a sky full of stars",
    "At the very edge of the meadow",
]

LANG_NAMES = {
    'fr': 'French',
    'en': 'English',
    'es': 'Spanish',
    'ar': 'Arabic'
}

FAIRY_TALE_PHRASES = {
    "fr": {
        "Once upon a time": "Il était une fois",
        "In a land not so far away": "Dans un pays pas si lointain",
        "Long ago, in a tiny village": "Il y a longtemps, dans un petit village",
        "On a rainy Tuesday morning": "Un mardi matin pluvieux",
        "Deep in the heart of the forest": "Au cœur de la forêt",
        "High up on a golden hill": "Sur une colline dorée",
        "Not far from the sea": "Non loin de la mer",
        "In a cozy little house at the edge of town": "Dans une petite maison chaleureuse au bord du village",
        "On the day everything changed": "Le jour où tout changea",
        "There was once": "Il y avait une fois",
        "Many moons ago": "Il y a bien des lunes",
        "In the smallest corner of a big wide world": "Dans le plus petit coin du vaste monde",
        "On a morning when the sky turned three colors at once": "Un matin où le ciel prit trois couleurs à la fois",
        "Beneath a sky full of stars": "Sous un ciel étoilé",
        "At the very edge of the meadow": "Au bord de la prairie",
        "happily ever after": "ils vécurent heureux",
        "The End": "Fin",
        "one day": "un beau jour",
    },
    "es": {
        "Once upon a time": "Érase una vez",
        "In a land not so far away": "En una tierra no muy lejana",
        "Long ago, in a tiny village": "Hace mucho tiempo, en un pequeño pueblo",
        "There was once": "Había una vez",
        "Many moons ago": "Hace muchas lunas",
        "happily ever after": "vivieron felices para siempre",
        "The End": "Fin",
        "one day": "un buen día",
    },
    "ar": {
        "Once upon a time": "كان يا ما كان",
        "There was once": "كان هناك",
        "Many moons ago": "منذ زمن بعيد",
        "happily ever after": "وعاشوا في سعادة وهناء",
        "The End": "النهاية",
    }
}

def post_process_translation(text: str, target_lang: str) -> str:
    phrases = FAIRY_TALE_PHRASES.get(target_lang, {})
    for english, translated in phrases.items():
        text = text.replace(english, translated)
        text = text.replace(english.lower(), translated)
    return text

ANIMALS = ['dog', 'cat', 'rabbit', 'bear', 'fox', 'horse', 'cow', 'sheep',
           'pig', 'chicken', 'duck', 'fish', 'butterfly', 'bee', 'giraffe',
           'elephant', 'lion', 'tiger', 'monkey', 'panda', 'penguin', 'owl',
           'frog', 'bird', 'canary', 'parrot', 'swan', 'hamster', 'turtle',
           'deer', 'goat', 'goose', 'ladybug', 'snail', 'dragon', 'unicorn']

PLACES = ['house', 'garden', 'forest', 'park', 'beach', 'mountain', 'river',
          'lake', 'castle', 'farm', 'school', 'market', 'city', 'village',
          'cave', 'island', 'meadow', 'barn', 'kitchen', 'bedroom', 'cottage']

OBJECTS = ['car', 'ball', 'book', 'doll', 'toy', 'kite', 'bicycle', 'train',
           'boat', 'umbrella', 'hat', 'balloon', 'chair', 'table', 'bed',
           'lamp', 'bag', 'shoe', 'clock', 'phone', 'bike']

FOODS = ['apple', 'banana', 'orange', 'strawberry', 'cherry', 'grape',
         'watermelon', 'pineapple', 'lemon', 'peach', 'pear', 'mango',
         'chocolate', 'candy', 'cake', 'ice cream', 'carrot', 'tomato',
         'cookie', 'bread', 'donut', 'cupcake']

NATURE = ['flower', 'tree', 'sun', 'moon', 'star', 'rainbow', 'cloud',
          'snow', 'rain', 'leaf', 'rose', 'sunflower']

ANIMAL_NAMES = [
    "Milo", "Luna", "Coco", "Theo", "Bella", "Max", "Nala", "Leo",
    "Rosie", "Felix", "Mimi", "Oscar", "Daisy", "Bruno", "Zara",
    "Pip", "Nino", "Lola", "Hugo", "Kiki", "Boo", "Finn", "Elsa",
    "Toto", "Sunny", "Peanut", "Ginger", "Hazel", "Cosmo", "Pearl"
]

CHILD_NAMES_BOY = [
    "Tom", "Sam", "Eli", "Ben", "Jake", "Kai", "Luca", "Noah",
    "Theo", "Owen", "Finn", "Max", "Hugo", "Zack", "Cole"
]

CHILD_NAMES_GIRL = [
    "Mia", "Zoe", "Eva", "Ivy", "Nora", "Aria", "Ruby", "Emma",
    "Cleo", "Nina", "Tess", "Jade", "Rose", "Faye", "Isla"
]

ANIMAL_ABILITIES = {
    'dog': 'can run, bark, wag tail, sniff, dig, jump, swim, fetch',
    'cat': 'can run, meow, purr, climb trees, jump, scratch, curl up',
    'rabbit': 'can hop, twitch nose, nibble, dig, hide in bushes',
    'bear': 'can walk, roar, climb trees, swim, dig, sniff',
    'fox': 'can run, bark, trot, dig, sniff, leap over obstacles',
    'horse': 'can gallop, trot, neigh, swish tail, nudge with nose',
    'cow': 'can walk, moo, graze, swish tail, nudge with nose',
    'bird': 'can fly, sing, peck, perch, flap wings, hop on ground',
    'fish': 'can swim, splash, blow bubbles, leap from water',
    'butterfly': 'can fly, flutter wings, land on flowers',
    'bee': 'can fly, buzz, collect pollen, sting',
    'elephant': 'can walk, trumpet, use trunk to grab, spray water',
    'monkey': 'can climb, swing, run, screech, grab with hands',
    'penguin': 'can waddle, swim, slide on belly, flap flippers',
    'owl': 'can fly, hoot, turn head, perch, swoop',
    'frog': 'can jump, croak, swim, catch insects with tongue',
    'duck': 'can waddle, quack, swim, fly, dip beak in water',
    'snail': 'can slide slowly, retract into shell, leave a trail',
    'turtle': 'can walk slowly, swim, retract into shell',
    'default': 'can move in ways natural to its species',
}

def generate_code():
    return ''.join(random.choices(string.digits, k=6))


def pick_name(character_type: str, used_names: list) -> str:
    if character_type == 'animal':
        pool = [n for n in ANIMAL_NAMES if n not in used_names]
        return random.choice(pool) if pool else random.choice(ANIMAL_NAMES)
    elif character_type == 'boy':
        pool = [n for n in CHILD_NAMES_BOY if n not in used_names]
        return random.choice(pool) if pool else random.choice(CHILD_NAMES_BOY)
    else:
        pool = [n for n in CHILD_NAMES_GIRL if n not in used_names]
        return random.choice(pool) if pool else random.choice(CHILD_NAMES_GIRL)


def get_animal_abilities(characters: list) -> str:
    rules = []
    for char in characters:
        char_lower = char.lower()
        for animal, abilities in ANIMAL_ABILITIES.items():
            if animal in char_lower:
                rules.append(f"- {char}: {abilities}")
                break
        else:
            rules.append(f"- {char}: moves naturally as their species allows")
    return '\n'.join(rules) if rules else "- Characters move as their real biology allows"


async def send_email(to_email: str, subject: str, body: str, html_body: str = None):
    try:
        gmail_user = os.getenv('GMAIL_USER')
        gmail_password = os.getenv('GMAIL_APP_PASSWORD')
        msg = MIMEMultipart('alternative')
        msg['From'] = f'TinyTales <{gmail_user}>'
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Reply-To'] = gmail_user
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        if html_body:
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.quit()
        print(f"✅ Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def elevenlabs_tts(text: str, voice_id: str, language: str = 'en') -> bytes:
    """Generate speech audio via ElevenLabs TTS. Returns MP3 bytes.

    Uses the multilingual v2 model with natural storytelling voice settings.
    Raises on HTTP error — caller is responsible for catching and falling back.
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text[:2900],
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True,
        },
    }
    response = req_lib.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.content


def polly_tts(text: str, voice_id: str, language: str = 'en') -> bytes:
    # ── Try ElevenLabs first if enabled and language supported ──
    if USE_ELEVENLABS and language in ELEVENLABS_VOICES and ELEVENLABS_API_KEY:
        try:
            # Pick the right ElevenLabs voice based on the Polly voice_id role
            role = POLLY_TO_ELEVENLABS_ROLE.get(voice_id, 'narrator')
            el_voice_id = ELEVENLABS_VOICES[language].get(role, ELEVENLABS_VOICES[language]['narrator'])
            audio_bytes = elevenlabs_tts(text, el_voice_id, language)
            print(f"✅ ElevenLabs TTS ({language}/{role}, voice {el_voice_id[:8]}…)")
            return audio_bytes
        except Exception as e:
            print(f"⚠️ ElevenLabs failed ({e}) — falling back to AWS Polly")

    # ── Original AWS Polly code (unchanged) ──
    engine = 'standard' if language == 'ar' else 'neural'
    neural_voices = ['Joanna', 'Matthew', 'Amy', 'Lea', 'Lupe']
    if voice_id not in neural_voices:
        engine = 'standard'
    response = polly.synthesize_speech(
        Text=text[:2900],
        OutputFormat='mp3',
        VoiceId=voice_id,
        Engine=engine
    )
    return response['AudioStream'].read()


def generate_speech_marks(text: str, voice_id: str, language: str = 'en') -> list:
    engine = 'standard' if language == 'ar' else 'neural'
    neural_voices = ['Joanna', 'Matthew', 'Amy', 'Lea', 'Lupe']
    if voice_id not in neural_voices:
        engine = 'standard'
    try:
        response = polly.synthesize_speech(
            Text=text[:2900],
            OutputFormat='json',
            VoiceId=voice_id,
            Engine=engine,
            SpeechMarkTypes=['word']
        )
        raw = response['AudioStream'].read().decode('utf-8')
        marks = []
        for line in raw.strip().split('\n'):
            if line.strip():
                marks.append(json.loads(line))
        return marks
    except Exception as e:
        print(f"Speech marks error: {e}")
        return []


def parse_story_segments(story: str, named_characters: list, language: str = 'en') -> list:
    import re
    lang_voices = POLLY_VOICES.get(language, POLLY_VOICES['en'])
    narrator_voice = lang_voices['narrator']
    char_voices_pool = [lang_voices['character1'], lang_voices['character2']]

    segments = []
    char_voice_map = {}
    voice_index = 0

    for char in named_characters:
        char_name = char.split()[0].lower()
        if char_name not in char_voice_map:
            char_voice_map[char_name] = char_voices_pool[voice_index % len(char_voices_pool)]
            voice_index += 1

    parts = re.split(r'(".*?"|\u201c.*?\u201d)', story)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        is_dialogue = (part.startswith('"') and part.endswith('"')) or \
                      (part.startswith('\u201c') and part.endswith('\u201d'))
        if is_dialogue:
            clean_text = part.strip('"').strip('\u201c').strip('\u201d')
            assigned_voice = char_voices_pool[0]
            for char_name, v in char_voice_map.items():
                assigned_voice = v
                break
            segments.append({"text": clean_text, "voice_id": assigned_voice, "language": language})
        else:
            if part:
                segments.append({"text": part, "voice_id": narrator_voice, "language": language})

    return segments if segments else [{"text": story, "voice_id": narrator_voice, "language": language}]


def merge_audio_with_marks(segments: list) -> tuple:
    try:
        from pydub import AudioSegment
        combined = AudioSegment.empty()
        silence = AudioSegment.silent(duration=300)
        all_marks = []
        time_offset = 0

        for seg in segments:
            if not seg["text"].strip():
                continue
            lang = seg.get("language", "en")
            voice = seg["voice_id"]
            try:
                audio_bytes = polly_tts(seg["text"], voice, lang)
                chunk = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
                marks = generate_speech_marks(seg["text"], voice, lang)
                for mark in marks:
                    all_marks.append({
                        "time":  mark["time"] + time_offset,
                        "value": mark["value"],
                        "start": mark.get("start", 0),
                        "end":   mark.get("end", 0),
                    })
                combined += chunk + silence
                time_offset += len(chunk) + 300
                print(f"  Segment OK — voice: {voice}, marks: {len(marks)}")
            except Exception as e:
                print(f"  Segment error: {e}")
                continue

        if len(combined) == 0:
            return "", []

        output = io.BytesIO()
        combined.export(output, format="mp3")
        return base64.b64encode(output.getvalue()).decode("utf-8"), all_marks

    except ImportError:
        print("pydub not installed — narrator fallback")
        try:
            lang = segments[0].get("language", "en") if segments else "en"
            narrator = POLLY_VOICES.get(lang, POLLY_VOICES['en'])['narrator']
            full_text = " ".join(s["text"] for s in segments)[:2900]
            audio_bytes = polly_tts(full_text, narrator, lang)
            marks = generate_speech_marks(full_text, narrator, lang)
            return base64.b64encode(audio_bytes).decode("utf-8"), marks
        except Exception as e:
            print(f"Fallback error: {e}")
            return "", []


# ── Models ────────────────────────────────────────────────

class UserData(BaseModel):
    email: str
    password: str

class GoogleAuthData(BaseModel):
    email: str
    name: str
    google_id: str
    avatar: Optional[str] = None

class VerifyCodeData(BaseModel):
    email: str
    code: str

class ForgotPasswordData(BaseModel):
    email: str

class ResetPasswordData(BaseModel):
    email: str
    code: str
    new_password: str

class ProfileRequest(BaseModel):
    name: str
    age: int
    gender: str
    avatar: str

class TranslateRequest(BaseModel):
    story: str
    language: str
    age: int


# ── Routes ────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "message": "TinyTales API running",
        "audio_provider": "ElevenLabs + AWS Polly (fallback)" if USE_ELEVENLABS else "AWS Polly"
    }


@app.post("/register")
async def register_user(data: UserData):
    validate_password(data.password)
    existing = await users_collection.find_one({"email": data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already used")
    hashed = hash_password(data.password)
    code = generate_code()
    expires = datetime.utcnow() + timedelta(minutes=10)
    await users_collection.insert_one({
        "email": data.email,
        "password": hashed,
        "verified": False,
        "verification_code": code,
        "verification_expires": expires.isoformat(),
        "created_at": datetime.utcnow().isoformat()
    })
    html_email = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TinyTales - Vérification</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #FFF8E7;">
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background: linear-gradient(135deg, #FFF8E7 0%, #FFE4B5 100%);">
            <tr>
                <td align="center" style="padding: 40px 20px;">
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px; background: #ffffff; border-radius: 24px; box-shadow: 0 10px 40px rgba(212, 168, 0, 0.2); overflow: hidden;">
                        <tr>
                            <td style="background: linear-gradient(135deg, #FFCC00 0%, #FFA500 100%); padding: 40px 20px; text-align: center;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 42px; font-weight: 900; letter-spacing: 1px; text-shadow: 0 2px 4px rgba(0,0,0,0.15);">
                                    ✨ TinyTales ✨
                                </h1>
                                <p style="color: #FFF8E7; margin: 8px 0 0 0; font-size: 14px; font-weight: 500;">
                                    Des histoires magiques pour les petits rêveurs
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px 40px 30px 40px;">
                                <h2 style="color: #2D5986; margin: 0 0 16px 0; font-size: 24px; font-weight: 700;">
                                    Bienvenue chez TinyTales ! 🎉
                                </h2>
                                <p style="color: #555; font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">
                                    Nous sommes ravis de vous accueillir dans l'univers magique de TinyTales. 
                                    Pour finaliser la création de votre compte, veuillez utiliser le code de vérification ci-dessous :
                                </p>
                                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                    <tr>
                                        <td align="center" style="padding: 20px 0;">
                                            <div style="display: inline-block; background: linear-gradient(135deg, #7DD9C8 0%, #50BCA8 100%); padding: 24px 48px; border-radius: 16px; box-shadow: 0 8px 20px rgba(80, 188, 168, 0.3);">
                                                <p style="color: #ffffff; margin: 0; font-size: 14px; font-weight: 500; letter-spacing: 2px; text-transform: uppercase;">
                                                    Votre code
                                                </p>
                                                <p style="color: #ffffff; margin: 8px 0 0 0; font-size: 42px; font-weight: 900; letter-spacing: 8px; font-family: 'Courier New', monospace;">
                                                    {code}
                                                </p>
                                            </div>
                                        </td>
                                    </tr>
                                </table>
                                <p style="color: #888; font-size: 14px; line-height: 1.6; margin: 24px 0 0 0; text-align: center;">
                                    ⏰ Ce code expire dans <strong>10 minutes</strong>
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 0 40px;">
                                <div style="border-top: 1px solid #eee;"></div>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 24px 40px;">
                                <p style="color: #999; font-size: 13px; line-height: 1.6; margin: 0;">
                                    🔒 Si vous n'êtes pas à l'origine de cette inscription, vous pouvez ignorer cet email en toute sécurité. 
                                    Aucun compte ne sera créé sans vérification.
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="background: #FFF8E7; padding: 24px 40px; text-align: center; border-top: 2px solid #FFE4B5;">
                                <p style="color: #D4A800; font-size: 14px; font-weight: 600; margin: 0 0 8px 0;">
                                    📚 TinyTales
                                </p>
                                <p style="color: #999; font-size: 12px; margin: 0;">
                                    L'imagination au bout des doigts des enfants
                                </p>
                            </td>
                        </tr>
                    </table>
                    <p style="color: #aaa; font-size: 11px; margin: 20px 0 0 0; text-align: center;">
                        Cet email a été envoyé automatiquement, merci de ne pas répondre.
                    </p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    text_email = f"""Bienvenue chez TinyTales !

Votre code de vérification est : {code}

Ce code expire dans 10 minutes.

Si vous n'êtes pas à l'origine de cette inscription, ignorez cet email.

— L'équipe TinyTales"""

    await send_email(
        data.email,
        "✨ TinyTales - Votre code de vérification",
        text_email,
        html_email
    )
    return {"message": "Account created. Check your email for verification code."}


@app.post("/verify-email")
async def verify_email(data: VerifyCodeData):
    user = await users_collection.find_one({"email": data.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("verified"):
        return {"message": "Already verified"}
    if user.get("verification_code") != data.code:
        raise HTTPException(status_code=400, detail="Invalid code")
    expires = datetime.fromisoformat(user.get("verification_expires", "2000-01-01"))
    if datetime.utcnow() > expires:
        raise HTTPException(status_code=400, detail="Code expired")
    await users_collection.update_one(
        {"email": data.email},
        {"$set": {"verified": True}, "$unset": {"verification_code": "", "verification_expires": ""}}
    )
    token = create_access_token({"sub": data.email}, expires_delta=timedelta(days=7))
    return {"message": "Email verified", "token": token}


@app.post("/login")
async def login_user(data: UserData):
    user = await users_collection.find_one({"email": data.email})
    if not user or not verify_password(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("verified", False):
        raise HTTPException(status_code=403, detail="Please verify your email first")
    token = create_access_token({"sub": data.email}, expires_delta=timedelta(days=7))
    return {"success": True, "token": token}


@app.post("/verify-login")
async def verify_login(data: VerifyCodeData):
    user = await users_collection.find_one({"email": data.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("login_code") != data.code:
        raise HTTPException(status_code=400, detail="Invalid code")
    expires = datetime.fromisoformat(user.get("login_code_expires", "2000-01-01"))
    if datetime.utcnow() > expires:
        raise HTTPException(status_code=400, detail="Code expired")
    await users_collection.update_one(
        {"email": data.email},
        {"$unset": {"login_code": "", "login_code_expires": ""}}
    )
    token = create_access_token({"sub": data.email}, expires_delta=timedelta(days=7))
    return {"token": token}


@app.post("/google-auth")
async def google_auth(data: GoogleAuthData):
    user = await users_collection.find_one({"email": data.email})
    if not user:
        await users_collection.insert_one({
            "email": data.email,
            "name": data.name,
            "google_id": data.google_id,
            "avatar": data.avatar,
            "verified": True,
            "auth_provider": "google",
            "created_at": datetime.utcnow().isoformat()
        })
    else:
        await users_collection.update_one(
            {"email": data.email},
            {"$set": {"google_id": data.google_id, "verified": True}}
        )
    token = create_access_token({"sub": data.email}, expires_delta=timedelta(days=7))
    return {"token": token}


@app.post("/forgot-password")
async def forgot_password(data: ForgotPasswordData):
    user = await users_collection.find_one({"email": data.email})
    if not user:
        return {"message": "If this email exists, a code has been sent"}
    code = generate_code()
    expires = datetime.utcnow() + timedelta(minutes=15)
    await users_collection.update_one(
        {"email": data.email},
        {"$set": {"reset_code": code, "reset_expires": expires.isoformat()}}
    )
    html_email = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TinyTales - Réinitialisation du mot de passe</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #FFF8E7;">
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background: linear-gradient(135deg, #FFF8E7 0%, #FFE4B5 100%);">
            <tr>
                <td align="center" style="padding: 40px 20px;">
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px; background: #ffffff; border-radius: 24px; box-shadow: 0 10px 40px rgba(212, 168, 0, 0.2); overflow: hidden;">
                        <tr>
                            <td style="background: linear-gradient(135deg, #FFCC00 0%, #FFA500 100%); padding: 40px 20px; text-align: center;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 42px; font-weight: 900; letter-spacing: 1px; text-shadow: 0 2px 4px rgba(0,0,0,0.15);">
                                    🔐 TinyTales 🔐
                                </h1>
                                <p style="color: #FFF8E7; margin: 8px 0 0 0; font-size: 14px; font-weight: 500;">
                                    Réinitialisation de votre mot de passe
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px 40px 30px 40px;">
                                <h2 style="color: #2D5986; margin: 0 0 16px 0; font-size: 24px; font-weight: 700;">
                                    Un petit oubli ? 🤔
                                </h2>
                                <p style="color: #555; font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">
                                    Pas de panique ! Vous avez demandé à réinitialiser votre mot de passe TinyTales. 
                                    Utilisez le code ci-dessous pour créer un nouveau mot de passe et retrouver vos histoires magiques :
                                </p>
                                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                    <tr>
                                        <td align="center" style="padding: 20px 0;">
                                            <div style="display: inline-block; background: linear-gradient(135deg, #E94B6F 0%, #C73E5C 100%); padding: 24px 48px; border-radius: 16px; box-shadow: 0 8px 20px rgba(233, 75, 111, 0.3);">
                                                <p style="color: #ffffff; margin: 0; font-size: 14px; font-weight: 500; letter-spacing: 2px; text-transform: uppercase;">
                                                    Code de réinitialisation
                                                </p>
                                                <p style="color: #ffffff; margin: 8px 0 0 0; font-size: 42px; font-weight: 900; letter-spacing: 8px; font-family: 'Courier New', monospace;">
                                                    {code}
                                                </p>
                                            </div>
                                        </td>
                                    </tr>
                                </table>
                                <p style="color: #888; font-size: 14px; line-height: 1.6; margin: 24px 0 0 0; text-align: center;">
                                    ⏰ Ce code expire dans <strong>15 minutes</strong>
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 0 40px;">
                                <div style="border-top: 1px solid #eee;"></div>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 24px 40px;">
                                <div style="background: #FFF3F5; border-left: 4px solid #E94B6F; padding: 16px; border-radius: 8px;">
                                    <p style="color: #C73E5C; font-size: 13px; line-height: 1.6; margin: 0; font-weight: 600;">
                                        🛡️ Vous n'avez pas demandé cette réinitialisation ?
                                    </p>
                                    <p style="color: #666; font-size: 13px; line-height: 1.6; margin: 8px 0 0 0;">
                                        Ignorez cet email — votre mot de passe actuel restera inchangé et votre compte est en sécurité.
                                    </p>
                                </div>
                            </td>
                        </tr>
                        <tr>
                            <td style="background: #FFF8E7; padding: 24px 40px; text-align: center; border-top: 2px solid #FFE4B5;">
                                <p style="color: #D4A800; font-size: 14px; font-weight: 600; margin: 0 0 8px 0;">
                                    📚 TinyTales
                                </p>
                                <p style="color: #999; font-size: 12px; margin: 0;">
                                    L'imagination au bout des doigts des enfants
                                </p>
                            </td>
                        </tr>
                    </table>
                    <p style="color: #aaa; font-size: 11px; margin: 20px 0 0 0; text-align: center;">
                        Cet email a été envoyé automatiquement, merci de ne pas répondre.
                    </p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    text_email = f"""Réinitialisation de votre mot de passe TinyTales

Votre code de réinitialisation est : {code}

Ce code expire dans 15 minutes.

Si vous n'avez pas demandé cette réinitialisation, ignorez cet email. 
Votre mot de passe actuel restera inchangé.
— L'équipe TinyTales"""

    await send_email(
        data.email,
        "🔐 TinyTales - Réinitialisation de votre mot de passe",
        text_email,
        html_email
    )
    return {"message": "If this email exists, a code has been sent"}


@app.post("/reset-password")
async def reset_password(data: ResetPasswordData):
    user = await users_collection.find_one({"email": data.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("reset_code") != data.code:
        raise HTTPException(status_code=400, detail="Invalid code")
    expires = datetime.fromisoformat(user.get("reset_expires", "2000-01-01"))
    if datetime.utcnow() > expires:
        raise HTTPException(status_code=400, detail="Code expired")
    validate_password(data.new_password)
    hashed = hash_password(data.new_password)
    await users_collection.update_one(
        {"email": data.email},
        {"$set": {"password": hashed}, "$unset": {"reset_code": "", "reset_expires": ""}}
    )
    return {"message": "Password reset successfully"}


@app.get("/profiles")
async def get_profiles(current_user: str = Depends(get_current_user)):
    cursor = profiles_collection.find({"owner": current_user}, {"_id": 0})
    profiles = await cursor.to_list(length=100)
    return profiles


@app.post("/profiles")
async def create_profile(data: ProfileRequest, current_user: str = Depends(get_current_user)):
    count = await profiles_collection.count_documents({"owner": current_user})
    if count >= 4:
        raise HTTPException(status_code=400, detail="Maximum 4 profiles")
    existing = await profiles_collection.find(
        {"owner": current_user}, {"id": 1}
    ).to_list(length=10)
    max_id = 0
    for p in existing:
        if p.get("id", 0) > max_id:
            max_id = p["id"]
    new_profile = {
        "id": max_id + 1,
        "name": data.name,
        "age": data.age,
        "gender": data.gender,
        "avatar": data.avatar,
        "owner": current_user,
    }
    await profiles_collection.insert_one(new_profile)
    new_profile.pop("_id", None)
    return {"message": "Profile created", "profile": new_profile}


@app.put("/profiles/{profile_id}")
async def update_profile(
    profile_id: int,
    data: ProfileRequest,
    current_user: str = Depends(get_current_user)
):
    await profiles_collection.update_one(
        {"id": profile_id, "owner": current_user},
        {"$set": {
            "name": data.name,
            "age": data.age,
            "gender": data.gender,
            "avatar": data.avatar,
        }}
    )
    return {"message": "Profile updated"}


@app.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: int, current_user: str = Depends(get_current_user)):
    await profiles_collection.delete_one({"id": profile_id, "owner": current_user})
    return {"message": "Profile deleted"}


@app.post("/favorites")
async def save_favorite(request: Request, current_user: str = Depends(get_current_user)):
    data = await request.json()
    favorite = {
        "story": data.get("story"),
        "labels": data.get("labels", []),
        "language": data.get("language", "en"),
        "age": data.get("age", 5),
        "profile_id": data.get("profile_id", 0),
        "cover_base64": data.get("cover_base64", ""),
        "created_at": datetime.utcnow().isoformat(),
        "owner": current_user,
    }
    result = await db["favorites"].insert_one(favorite)
    favorite.pop("_id", None)
    favorite["id"] = str(result.inserted_id)
    return {"success": True, "message": "Saved", "id": str(result.inserted_id), "favorite": favorite}


@app.get("/favorites")
async def get_favorites(profile_id: int = 0, current_user: str = Depends(get_current_user)):
    cursor = db["favorites"].find(
        {"owner": current_user, "profile_id": profile_id},
        {"_id": 1, "story": 1, "labels": 1, "language": 1, "created_at": 1, "cover_base64": 1}
    )
    favorites = await cursor.to_list(length=100)
    for f in favorites:
        f["id"] = str(f.pop("_id"))
    return favorites


@app.delete("/favorites/{favorite_id}")
async def delete_favorite(favorite_id: str, current_user: str = Depends(get_current_user)):
    from bson import ObjectId
    await db["favorites"].delete_one({"_id": ObjectId(favorite_id), "owner": current_user})
    return {"message": "Deleted"}


@app.post("/translate-story")
async def translate_story(
    data: TranslateRequest,
    current_user: Optional[str] = Depends(get_current_user_optional)
):
    if data.language == 'en':
        return {"story": data.story, "language": "en"}

    opening_used = "Once upon a time"
    for op in STORY_OPENINGS:
        if data.story.startswith(op):
            opening_used = op
            break

    opening_translations = FAIRY_TALE_PHRASES.get(data.language, {})
    translated_opening = opening_translations.get(opening_used, opening_translations.get("Once upon a time", opening_used))

    lang_instructions = {
        'fr': f"""Tu es un traducteur expert en littérature jeunesse francophone.
Traduis cette histoire en français naturel et fluide pour un enfant de {data.age} ans.

RÈGLES ABSOLUES :
- Traduis le sens et l'émotion, PAS mot à mot
- Utilise un français parlé naturel, comme on raconte une histoire à voix haute
- Garde exactement les noms des personnages (Milo reste Milo, Luna reste Luna)
- Conserve toute la magie, le rythme et les émotions de l'original
- Garde les dialogues entre guillemets
- La première phrase DOIT commencer par : {translated_opening}
- Même longueur que l'original — ne raccourcis pas""",

        'es': f"""Eres un traductor experto en literatura infantil hispanohablante.
Traduce esta historia al español natural y fluido para un niño de {data.age} años.

REGLAS ABSOLUTAS:
- Traduce el sentido y la emoción, NO palabra por palabra
- Usa un español hablado natural, como se cuenta un cuento en voz alta
- Conserva exactamente los nombres de los personajes
- Mantén toda la magia, el ritmo y las emociones del original
- La primera frase DEBE comenzar con: {translated_opening}""",

        'ar': f"""أنت مترجم خبير في أدب الأطفال العربي.
ترجم هذه القصة إلى عربية طبيعية وسلسة لطفل عمره {data.age} سنوات.

قواعد مطلقة:
- ترجم المعنى والمشاعر، وليس كلمة بكلمة
- استخدم عربية محكية طبيعية
- احتفظ بأسماء الشخصيات كما هي
- الجملة الأولى يجب أن تبدأ بـ: {translated_opening}"""
    }

    instruction = lang_instructions.get(data.language, f"Translate to {LANG_NAMES.get(data.language)}")

    translate_prompt = f"""{instruction}

RÈGLES DE FORMAT :
1. Retourne UNIQUEMENT le texte traduit
2. Zéro introduction ("Voilà", "Voici", "Here is"...)
3. Commence DIRECTEMENT par : {translated_opening}
4. Même structure de paragraphes que l'original

Histoire à traduire :
{data.story}"""

    prefill = translated_opening

    response = bedrock.invoke_model(
        modelId='anthropic.claude-3-haiku-20240307-v1:0',
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [
                {"role": "user", "content": translate_prompt},
                {"role": "assistant", "content": prefill}
            ]
        })
    )
    response_body = response['body'].read()
    response_text = json.loads(response_body)['content'][0]['text']
    translated = prefill + response_text
    translated = unicodedata.normalize('NFC', translated)
    translated = post_process_translation(translated, data.language)

    return JSONResponse(
        content={"story": translated, "language": data.language},
        media_type="application/json; charset=utf-8"
    )


@app.post("/generate-audio")
async def generate_audio(
    request: Request,
    current_user: Optional[str] = Depends(get_current_user_optional)
):
    data = await request.json()
    story = data.get("story", "")
    language = data.get("language", "en")
    named_characters = data.get("named_characters", [])
    story = unicodedata.normalize("NFC", story)

    audio_base64 = ""
    speech_marks = []
    try:
        segments = parse_story_segments(story, named_characters, language)
        print(f"Story split into {len(segments)} segments (lang: {language})")
        audio_base64, speech_marks = merge_audio_with_marks(segments)
        print(f"✅ Audio + {len(speech_marks)} speech marks generated")
    except Exception as e:
        print(f"Polly error: {e}")
        try:
            narrator_voice = POLLY_VOICES.get(language, POLLY_VOICES['en'])['narrator']
            audio_bytes = polly_tts(story[:2900], narrator_voice, language)
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
            speech_marks = generate_speech_marks(story[:2900], narrator_voice, language)
            print(f"✅ Fallback audio + {len(speech_marks)} marks generated")
        except Exception as e2:
            print(f"Fallback error: {e2}")

    return JSONResponse(
        content={
            "audio_base64": audio_base64,
            "speech_marks": speech_marks,
            "language": language
        },
        media_type="application/json; charset=utf-8"
    )


@app.post("/generate-story")
async def generate_story(
    images: List[UploadFile] = File(default=[]),
    age: int = Form(default=4),
    keywords: str = Form(default=""),
    spoken_phrase: str = Form(default=""),
    current_user: Optional[str] = Depends(get_current_user_optional)
):
    image_elements = []

    # ── Mode phrase complète (l'enfant a parlé) ─────────────
    if spoken_phrase and not images:
        print(f"🎤 Spoken phrase from child: \"{spoken_phrase}\"")
        try:
            intent_prompt = f"""A child around {age} years old just said this to create a story:
"{spoken_phrase}"

Extract ONLY the meaningful story elements from what the child said.
Keep: characters (animals, people), objects, places, colors, emotions, actions.
Ignore: filler words, repetitions, hesitations, grammatical words.

Children often:
- Use baby-talk or mispronounced words → interpret naturally (e.g. "toutou" → "dog")
- Mix languages → normalize to simple English nouns
- Say things like "I want..." → ignore that part
- Repeat words or hesitate → keep only unique meaningful words

Return ONLY a comma-separated list of 2-6 simple English words.
No explanation, no prefix, no quotes.

Examples:
Child: "je veux une histoire avec un chat qui vole et une princesse rose"
Output: cat, princess, pink, flying

Child: "un dragon méchant qui fait peur au lapin"
Output: dragon, rabbit, scary

Child: "euh... je sais pas... mon toutou et le jardin"
Output: dog, garden

Now extract from the child's words:"""

            intent_response = bedrock.invoke_model(
                modelId='anthropic.claude-3-haiku-20240307-v1:0',
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 50,
                    "messages": [{"role": "user", "content": intent_prompt}]
                })
            )
            extracted = json.loads(intent_response['body'].read())['content'][0]['text'].strip()
            image_elements = [
                w.strip().lower()
                for w in extracted.split(',')
                if w.strip() and len(w.strip()) > 1
            ]
            print(f"🧠 Claude extracted elements: {image_elements}")
        except Exception as e:
            print(f"Intent extraction error: {e}")
            if keywords:
                image_elements = [k.strip() for k in keywords.split(',') if k.strip()]
            else:
                image_elements = ["rabbit", "garden"]

    # ── Mode keywords vocaux (fallback) ──────────────────────
    elif keywords and not images:
        kw_list = [k.strip() for k in keywords.split(',') if k.strip()]
        image_elements = kw_list if kw_list else ["rabbit", "garden"]
        print(f"Keywords mode: {image_elements}")

    # ── Mode images ──────────────────────────────────────────
    else:
        for image in images:
            image_bytes = await image.read()
            if not image_bytes or len(image_bytes) < 10:
                continue
            try:
                media_type = "image/jpeg"
                if image.filename:
                    if image.filename.lower().endswith('.png'):
                        media_type = "image/png"
                    elif image.filename.lower().endswith('.webp'):
                        media_type = "image/webp"
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                vision_response = bedrock.invoke_model(
                    modelId='anthropic.claude-3-haiku-20240307-v1:0',
                    body=json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 30,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_base64
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": """What is in this image? Reply with ONE simple common word only.
Use the most basic word a child would use.
RULES:
- Any dog breed → 'dog'
- Any cat breed → 'cat'
- Any car type → 'car'
- Any flower type → 'flower'
- Any tree type → 'tree'
- Any bird type → 'bird'
- Any fish type → 'fish'
- Any horse type → 'horse'
- Any cake/dessert → 'cake'
- Any fruit → name simply (apple, banana, orange)
- Any house/building → 'house'
- Any ball → 'ball'
Just one simple word, nothing else."""
                                }
                            ]
                        }]
                    })
                )
                label = json.loads(vision_response['body'].read())['content'][0]['text'].strip().lower()
                label = label.replace('.', '').replace(',', '').strip()
                if label and len(label) < 30:
                    image_elements.append(label)
                    print(f"Claude Vision detected: {label}")
            except Exception as e:
                print(f"Vision error: {e}")

    if not image_elements:
        image_elements = ["rabbit", "garden"]

    # ── Classification des éléments ──────────────────────────
    characters = []
    places = []
    objects = []
    foods = []
    nature_elements = []

    for element in image_elements:
        el = element.lower()
        if any(a in el for a in ANIMALS):
            characters.append(element)
        elif any(p in el for p in PLACES):
            places.append(element)
        elif any(f in el for f in FOODS):
            foods.append(element)
        elif any(n in el for n in NATURE):
            nature_elements.append(element)
        else:
            objects.append(element)

    if not characters:
        characters = ['child']

    used_names = []
    named_characters = []
    for char in characters:
        if char == 'child':
            gender = random.choice(['boy', 'girl'])
            name = pick_name(gender, used_names)
        else:
            name = pick_name('animal', used_names)
        used_names.append(name)
        named_characters.append(f"{name} the {char}" if char != 'child' else name)

    print(f"Named characters: {named_characters}")

    if age <= 3:
        sentence_count = 6
        max_tokens = 200
        style = f"""Write EXACTLY {sentence_count} sentences. STOP after {sentence_count} sentences.
MAXIMUM 5 words per sentence. No exceptions.
Use only: mama, papa, warm, love, small, big, soft, run, play, sleep.
Tone: gentle lullaby. Very slow and soothing."""
        vocabulary = "Only words a 2-year-old knows. Ultra simple."

    elif age <= 5:
        sentence_count = 9
        max_tokens = 400
        style = f"""Write EXACTLY {sentence_count} sentences. STOP after {sentence_count} sentences.
Maximum 8 words per sentence.
Simple, warm, clear. One idea per sentence.
No complex words. No long descriptions."""
        vocabulary = "Simple words only. Nothing a 4-year-old wouldn't understand."

    elif age <= 7:
        sentence_count = 11
        max_tokens = 550
        style = f"""Write EXACTLY {sentence_count} sentences. STOP after {sentence_count} sentences.
Maximum 12 words per sentence.
Expressive and vivid. One moment of surprise or wonder."""
        vocabulary = "Words a 6-year-old knows. Simple adjectives allowed."

    elif age <= 9:
        sentence_count = 13
        max_tokens = 750
        style = f"""Write EXACTLY {sentence_count} sentences. STOP after {sentence_count} sentences.
Varied sentence lengths. Include one line of dialogue.
The character should feel something and grow."""
        vocabulary = "Age-appropriate vocabulary."

    else:
        sentence_count = 15
        max_tokens = 800
        style = f"""Write EXACTLY {sentence_count} sentences. STOP after {sentence_count} sentences.
Rich descriptions. Clear arc. Meaningful dialogue."""
        vocabulary = "Rich vocabulary for 10+ year olds."

    story_context = f"MAIN CHARACTER(S): {', '.join(named_characters)}"
    if places:
        story_context += f"\nSETTING: {', '.join(places)}"
    if objects:
        story_context += f"\nOBJECTS in the story: {', '.join(objects)}"
    if foods:
        story_context += f"\nFOODS in the story: {', '.join(foods)}"
    if nature_elements:
        story_context += f"\nNATURE elements: {', '.join(nature_elements)}"

    values = [
        "the joy of sharing with others",
        "kindness to animals and nature",
        "being brave when scared",
        "the importance of helping a friend",
        "gratitude for small beautiful things",
        "taking care of our planet",
        "being proud of being different",
        "the love between parent and child",
        "honesty is always the right choice",
        "patience leads to beautiful rewards"
    ]

    # ── 10 different ending types to force real diversity ──
    ending_types = [
        "The main character solves their problem ALONE, through their own courage, cleverness, or kindness. No friendship summary.",
        "The main character goes back home carrying a small precious souvenir (a feather, a stone, a seed, a drawing). End on that object in their hand.",
        "The main character learns something important about THEMSELVES (not about friendship). They feel quietly proud.",
        "The main character helps someone, then calmly walks away. No big thank you scene, no friendship declaration.",
        "The main character discovers a small magical secret and decides to keep it to themselves. End with a quiet smile.",
        "The main character returns home and tells their mom or dad about the adventure. End on the parent's reaction.",
        "The main character falls asleep peacefully, dreaming of the day. End on a soft image (moon, blanket, stars).",
        "The main character makes a quiet promise — to nature, to an animal, or to themselves — and keeps walking.",
        "The main character finds a lost object that was precious to them. End on the joy of holding it again.",
        "The main character stops and simply contemplates the beauty around them in a calm, silent moment. End on what they see.",
    ]
    chosen_ending = random.choice(ending_types)
    chosen_value = random.choice(values)
    chosen_opening = random.choice(STORY_OPENINGS)
    physical_rules = get_animal_abilities(named_characters)

    prompt = f"""You are writing a BEAUTIFUL, REALISTIC-FEELING children's story for a {age}-year-old.
Not an "AI story." A real, warm, joyful story — like a classic picture book.

═══════════════════════════════════════════════════════════
⚠️  RULE #1 — PHYSICAL REALITY  (MOST IMPORTANT RULE)
═══════════════════════════════════════════════════════════
Every character keeps the body it really has. NO EXCEPTIONS.

What your characters CAN do:
{physical_rules}

CONCRETE FORBIDDEN EXAMPLES — never write anything like these:
❌ "the snake hugged him"           → snakes have no arms
❌ "the fish held out a hand"       → fish have no hands
❌ "the rabbit clapped"             → rabbits don't clap
❌ "the bird kicked the ball"       → birds don't kick
❌ "the cow climbed the tree"       → cows cannot climb
❌ "the lion pointed at the door"   → lions don't point

NEVER use these expressions with an animal that has no hands:
— "holds out a hand"  /  "reaches out a hand"  /  "takes his hand"
— "grabs" / "points" / "waves" / "claps" / "writes" / "draws"

Instead use natural animal actions:
— a rabbit TWITCHES its nose, HOPS closer, NUDGES with its head
— a fish SWIMS in circles, BLOWS bubbles, FLICKS its tail
— a bird TILTS its head, HOPS on a branch, CHIRPS softly
— a cat PURRS, CURLS UP, RUBS against a leg

═══════════════════════════════════════════════════════════
⚠️  RULE #2 — COHERENT MAGIC  (SECOND MOST IMPORTANT)
═══════════════════════════════════════════════════════════
Things stay what they ARE. You can have a magical ADVENTURE,
but you CANNOT invent absurd fusions or impossible transformations.

CONCRETE FORBIDDEN EXAMPLES:
❌ "a lion with rainbow hair"              → a lion has fur, not rainbow hair
❌ "a dinosaur made of snow that became real" → snow is snow, dinosaurs are dinosaurs
❌ "the rabbit's ears were made of clouds"  → ears are ears
❌ "her hair turned into a river"           → hair is hair
❌ "the tree walked down the hill"          → trees don't walk
❌ "the cookie started singing"             → cookies are food, not alive

If the child's elements are "rainbow" + "lion":
✅ The lion SEES a beautiful rainbow after the rain.
✅ The lion WALKS toward the rainbow, wondering where it ends.
❌ The lion HAS rainbow-colored fur. (NO — absurd fusion)

If the child's elements are "dinosaur" + "snow":
✅ A small dinosaur plays in the first snow of winter.
❌ A dinosaur MADE OF snow comes to life. (NO — nonsense)

Magic is ALLOWED when it's clear and simple:
✅ Animals can talk (classic fairy tale magic)
✅ A small glowing flower, a friendly cloud, a talking star
✅ ONE clearly magical moment in the whole story

═══════════════════════════════════════════════════════════
📖  STORY FOUNDATION
═══════════════════════════════════════════════════════════
{story_context}

Characters (use the EXACT names given — zero substitutions):
{', '.join(named_characters)}

Length: EXACTLY {sentence_count} sentences. Count them.
Style: {style}
Vocabulary: {vocabulary} — simple, clear, easy for a {age}-year-old.
Tone: JOYFUL, warm, gentle. Never dark. Never sad ending.
Value to teach invisibly (never name it): {chosen_value}

═══════════════════════════════════════════════════════════
🎬  OPENING
═══════════════════════════════════════════════════════════
Start your FIRST sentence with EXACTLY this phrase: "{chosen_opening}"
Do NOT use "Once upon a time" unless that IS the chosen phrase.

═══════════════════════════════════════════════════════════
🎯  ENDING — MANDATORY TYPE FOR THIS STORY
═══════════════════════════════════════════════════════════
Your ending MUST be this specific type (NOT a friendship ending):

👉 {chosen_ending}

ABSOLUTELY BANNED ENDINGS:
❌ "they became best friends"
❌ "they lived happily ever after"
❌ "from that day on, they were inseparable"
❌ "they played together every day"
❌ "it was the best day ever"
❌ Any moral summary ("and so [X] learned that...")
❌ Any forced friendship between characters and objects
❌ Any forced friendship between predator and prey

═══════════════════════════════════════════════════════════
💬  DIALOGUE — MANDATORY (takes advantage of multiple voices)
═══════════════════════════════════════════════════════════
This story MUST include real spoken dialogue between characters.
Dialogue makes the story come alive and gives each character a real voice.

MANDATORY REQUIREMENTS:
✅ Include AT LEAST 2 lines of dialogue (3 is even better)
✅ Dialogue must feel NATURAL and fit the character's personality
✅ Each dialogue line MUST be wrapped in double quotes: "like this"
✅ Dialogue must MOVE THE STORY FORWARD (reveal emotion, start an action, solve the problem)
✅ Keep each line SHORT and simple — 4 to 12 words maximum per line
✅ Use age-appropriate vocabulary for a {age}-year-old

FORMAT EXAMPLES (follow this exact format):
✅ Luna whispered, "I can hear something in the bushes."
✅ "Wait for me!" called Milo, hopping behind her.
✅ The little girl looked up and said, "Thank you for finding it."

AVOID:
❌ Long speeches or monologues (more than 2 sentences in one quote)
❌ Dialogue that just describes what we already see
❌ Fake-sounding dialogue ("Oh what a wonderful day it is today indeed!")
❌ Adult/complex vocabulary
❌ Dialogue without quotes (REQUIRED for voice recognition)

WHY THIS MATTERS:
The app uses different voices for the narrator and the characters who speak.
Without dialogue wrapped in quotes, the child will only hear one voice.
With dialogue in quotes, the story becomes a real audiobook with multiple voices.

═══════════════════════════════════════════════════════════
🎭  CHARACTER DEPTH
═══════════════════════════════════════════════════════════
Give the main character ONE clear personality trait (pick one, not "curious"):
brave / shy / clumsy / stubborn / dreamy / silly / generous / 
mischievous / patient / daydreamer / kind-hearted / adventurous

This trait must be the REASON the problem gets solved.

Show emotions through ACTIONS, not labels:
❌ "she was sad"          → ✅ "she looked down at her feet"
❌ "he was happy"         → ✅ "he hummed as he walked"
❌ "she was scared"       → ✅ "her hands trembled a little"

═══════════════════════════════════════════════════════════
🌍  SETTING (make it feel real)
═══════════════════════════════════════════════════════════
Include AT LEAST one of each, woven naturally into the story:
• One SOUND (rustling leaves, a soft bell, distant water)
• One SMELL or TEXTURE (warm bread, soft moss, cool wind)
• One specific VISUAL detail (tiny yellow flowers, a crooked fence)

═══════════════════════════════════════════════════════════
🏗️  STRUCTURE  (distribute {sentence_count} sentences)
═══════════════════════════════════════════════════════════
• BEGINNING (~20%) — introduce character and world gently
• PROBLEM (~30%) — ONE clear problem for this character
• TURNING POINT (~25%) — one small moment of wonder or discovery
• ENDING (~25%) — execute the mandatory ending type above

═══════════════════════════════════════════════════════════
✍️  WRITING RULES
═══════════════════════════════════════════════════════════
• Simple sentences. One idea per sentence.
• Mix short and medium sentence lengths.
• Dialogue: 1 to 3 lines maximum, simple and sweet.
• BANNED WORDS: very, really, just, nice, beautiful, happy, sad, good, bad, curious
• Each action must be physically possible (see RULE #1).
• Each magical element must be coherent (see RULE #2).

═══════════════════════════════════════════════════════════
✅  FINAL SELF-CHECK  (before writing, silently verify)
═══════════════════════════════════════════════════════════
□ Does my story START with exactly: "{chosen_opening}"?
□ Does EVERY action respect real animal biology (RULE #1)?
□ Did I AVOID absurd fusions like rainbow-hair-lion (RULE #2)?
□ Does my ending match the MANDATORY type above (not a friendship ending)?
□ Did I include AT LEAST 2 lines of dialogue in "double quotes"?
□ Is my tone JOYFUL and warm throughout?
□ Did I count EXACTLY {sentence_count} sentences?

═══════════════════════════════════════════════════════════
🖊️  NOW WRITE  (story only, no title, no preamble)
═══════════════════════════════════════════════════════════
Start directly with "{chosen_opening}":"""

    bedrock_response = bedrock.invoke_model(
        modelId='anthropic.claude-3-haiku-20240307-v1:0',
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": chosen_opening}
            ]
        })
    )

    story_raw = json.loads(bedrock_response['body'].read())['content'][0]['text'].strip()
    story_en = chosen_opening + " " + story_raw

    lines = story_en.split('\n')
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(phrase in line.lower() for phrase in [
            'here is', 'voici', "here's", 'following', 'sure!', 'certainly',
            'elements', 'rules', 'story for', 'child of', 'requested', 'write'
        ]):
            continue
        clean_lines.append(line)
    story_en = ' '.join(clean_lines).strip()
    print(f"Story EN — opening: '{chosen_opening}' — {story_en[:100]}")

    audio_base64 = ""
    speech_marks = []
    try:
        segments = parse_story_segments(story_en, named_characters, 'en')
        print(f"Story split into {len(segments)} segments for audio")
        audio_base64, speech_marks = merge_audio_with_marks(segments)
        print(f"✅ Audio + {len(speech_marks)} speech marks generated")
    except Exception as e:
        print(f"Polly audio error: {e}")
        try:
            narrator_voice = POLLY_VOICES['en']['narrator']
            audio_bytes = polly_tts(story_en[:2900], narrator_voice, 'en')
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            speech_marks = generate_speech_marks(story_en[:2900], narrator_voice, 'en')
            print(f"✅ Fallback audio + {len(speech_marks)} marks generated")
        except Exception as e2:
            print(f"Audio fallback error: {e2}")

    return JSONResponse(
        content={
            "story": story_en,
            "named_characters": named_characters,
            "labels": image_elements,
            "audio_base64": audio_base64,
            "speech_marks": speech_marks,
            "language": "en"
        },
        media_type="application/json; charset=utf-8"
    )


@app.post("/generate-cover")
async def generate_cover(
    request: Request,
    current_user: Optional[str] = Depends(get_current_user_optional)
):
    data = await request.json()
    labels = data.get("labels", [])
    age = data.get("age", 5)

    if not labels:
        labels = ["magical creature"]

    animal_subjects = [l for l in labels if any(a in l.lower() for a in ANIMALS)]
    other_elements  = [l for l in labels if l not in animal_subjects]

    if animal_subjects:
        main_subject = animal_subjects[0]
        companions   = animal_subjects[1:]
    else:
        main_subject = labels[0]
        companions   = []
        other_elements = labels[1:]

    all_characters = [main_subject] + companions
    characters_str = " and ".join(all_characters)

    objects_str = ""
    if other_elements:
        objects_str = f"surrounded by {', '.join(other_elements[:3])}, "

    image_prompt = (
        f"Vintage children's book illustration featuring {characters_str}, "
        f"{objects_str}"
        f"classic storybook art style, hand-painted watercolor texture, "
        f"warm muted tones, golden yellows and soft greens, "
        f"detailed cross-hatching, reminiscent of 1950s-1970s picture books, "
        f"like original Babar, Charlotte's Web, or Winnie the Pooh illustrations, "
        f"all characters fully visible, expressive faces, "
        f"soft vignette edges, aged paper texture, painterly brushstrokes, "
        f"no text, no words, no letters, no watermark."
    )

    negative_prompt = (
        "scary, dark, violent, realistic photo, "
        "text, watermark, ugly, blurry, deformed, mutated, "
        "extra limbs, missing limbs, wrong anatomy, floating body parts, "
        "headless, decapitated, dismembered, disfigured, "
        "words, letters, title, caption, writing, typography, font, "
        "adult content, nsfw, humans, people"
    )

    print(f"Generating cover — characters: {characters_str}, objects: {other_elements}")

    try:
        import requests as req
        hf_token = os.getenv("HF_API_KEY")
        api_url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-dev"

        hf_response = req.post(
            api_url,
            headers={"Authorization": f"Bearer {hf_token}"},
            json={
                "inputs": image_prompt,
                "parameters": {
                    "num_inference_steps": 30,
                    "guidance_scale": 7.5,
                    "width": 768,
                    "height": 1024,
                    "negative_prompt": negative_prompt
                }
            },
            timeout=120
        )

        if hf_response.status_code == 200:
            image_base64 = base64.b64encode(hf_response.content).decode('utf-8')
            print("✅ Cover generated (FLUX.1-dev)")
            return JSONResponse(content={"success": True, "image_base64": image_base64})
        else:
            print(f"FLUX.1-dev failed ({hf_response.status_code}), trying schnell...")
            api_url_fallback = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
            hf_response2 = req.post(
                api_url_fallback,
                headers={"Authorization": f"Bearer {hf_token}"},
                json={"inputs": image_prompt},
                timeout=60
            )
            if hf_response2.status_code == 200:
                image_base64 = base64.b64encode(hf_response2.content).decode('utf-8')
                print("✅ Cover generated (fallback schnell)")
                return JSONResponse(content={"success": True, "image_base64": image_base64})
            else:
                raise Exception(f"HF Error {hf_response2.status_code}: {hf_response2.text}")

    except Exception as e:
        print(f"Cover generation error: {e}")
        return JSONResponse(content={"success": False, "image_base64": "", "error": str(e)})