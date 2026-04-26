import os
import json
import re
import streamlit as st
from moviepy.editor import *
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ---------- SETUP ----------
USE_ELEVENLABS = os.getenv("ELEVEN_API_KEY") is not None
if USE_ELEVENLABS:
    from elevenlabs import generate, save, set_api_key
    set_api_key(os.getenv("ELEVEN_API_KEY"))
else:
    from gtts import gTTS

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.title("🎬 Training Recap Video Generator")

uploaded_files = st.file_uploader(
    "Upload transcripts (multiple days)",
    type=["txt"],
    accept_multiple_files=True
)

# ---------- REMOVE SPEAKER ----------
def remove_speaker(text, speaker="Ravi"):
    lines = text.split("\n")
    return "\n".join([
        l for l in lines
        if not l.strip().lower().startswith(
            (speaker.lower()+":", speaker.lower()+" -", speaker.lower()+"(")
        )
    ])

# ---------- CLEAN ----------
def clean_text(text):
    banned = ["speaker", "lecture", "session", "today"]
    for w in banned:
        text = text.replace(w, "")
    return text

# ---------- SUMMARY ----------
def summarize_day(text):
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": f"Summarize key topics and outcomes clearly:\n{text[:6000]}"
        }]
    )
    return res.choices[0].message.content

# ---------- RECAP ----------
def generate_recap(summaries):
    combined = "\n\n".join(summaries)
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": f"""
Create a simple corporate recap.

Do NOT use: speaker, lecture, session, today

Use short sentences.

Content:
{combined}
"""
        }]
    )
    return res.choices[0].message.content

# ---------- SEGMENTS ----------
def split_segments(text):
    sentences = text.split(". ")
    segments, current = [], ""

    for s in sentences:
        if len(current.split()) < 35:
            current += s + ". "
        else:
            segments.append(current.strip())
            current = s + ". "

    if current:
        segments.append(current.strip())

    return segments

# ---------- SLIDES ----------
def build_slides(segments):
    slides = []

    for seg in segments:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": f"""
Create slide + narration.

Return JSON:
{{
"title":"Short title",
"points":["short point","short point"],
"narration":"short spoken version"
}}

Rules:
- Short sentences
- Narration must match slide

Text:
{seg}
"""
            }]
        )
        slides.append(json.loads(res.choices[0].message.content))

    return slides

# ---------- AUDIO (FAST) ----------
def generate_audio(slides):
    files = []

    for i, s in enumerate(slides):
        fname = f"audio_{i}.mp3"
        text = s["narration"]

        try:
            if USE_ELEVENLABS:
                audio = generate(text=text, voice="Rachel")
                save(audio, fname)
            else:
                gTTS(text, slow=False).save(fname)

            # 🔥 SPEED FIX (1.2x)
            clip = AudioFileClip(fname)
            fast = clip.fx(vfx.speedx, 1.2)
            fast_name = f"fast_{i}.mp3"
            fast.write_audiofile(fast_name)

            files.append(fast_name)

        except:
            gTTS("Overview.", slow=False).save(fname)
            files.append(fname)

    return files

# ---------- IMAGE ----------
def create_slide(text):
    img = Image.new("RGB", (1280,720), (255,255,255))
    draw = ImageDraw.Draw(img)

    base = os.path.dirname(__file__)
    try:
        title_font = ImageFont.truetype(os.path.join(base,"fonts/DejaVuSans-Bold.ttf"),55)
        body_font = ImageFont.truetype(os.path.join(base,"fonts/DejaVuSans.ttf"),20)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    lines = text.split("\n")

    w = draw.textbbox((0,0),lines[0],font=title_font)[2]
    draw.text(((1280-w)//2,80),lines[0],font=title_font,fill=(0,0,0))

    y=180
    for l in lines[1:]:
        draw.text((100,y),l,font=body_font,fill=(0,0,0))
        y+=40

    return np.array(img)

# ---------- VIDEO ----------
def create_video(slides, audio_files):
    clips, audios = [], []

    for i, s in enumerate(slides):
        text = s["title"] + "\n\n" + "\n".join([f"• {p}" for p in s["points"]])
        img = create_slide(text)
        audio = AudioFileClip(audio_files[i])

        clip = ImageClip(img).set_duration(audio.duration)
        clip = clip.fadein(0.3).fadeout(0.3)

        clips.append(clip)
        audios.append(audio)

    video = concatenate_videoclips(clips, method="compose")
    audio = concatenate_audioclips(audios)

    video = video.set_audio(audio)

    # duration control
    dur = audio.duration
    if dur < 180:
        video = video.fx(vfx.speedx, dur/180)
    elif dur > 240:
        video = video.fx(vfx.speedx, dur/240)

    video.write_videofile(
        "final_video.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac"
    )

    return "final_video.mp4"

# ---------- MAIN ----------
if uploaded_files:
    if st.button("Generate Recap Video"):
        try:
            summaries = []

            for f in uploaded_files:
                text = f.read().decode("utf-8")
                text = remove_speaker(text, "Ravi")
                summaries.append(summarize_day(text))

            recap = clean_text(generate_recap(summaries))
            st.write(recap)

            segments = split_segments(recap)
            slides = build_slides(segments)
            audio_files = generate_audio(slides)

            video = create_video(slides, audio_files)

            st.success("✅ Video Ready")
            st.video(video)

        except Exception as e:
            st.error(str(e))
