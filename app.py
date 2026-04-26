import os
import json
import asyncio
import streamlit as st
from moviepy.editor import *
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import edge_tts

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.title("🎬 Training Recap Video Generator (Natural Voice)")

uploaded_files = st.file_uploader(
    "Upload transcripts",
    type=["txt"],
    accept_multiple_files=True
)

# ---------- REMOVE SPEAKER ----------
def remove_speaker(text, speaker="Ravi"):
    return "\n".join([
        l for l in text.split("\n")
        if not l.strip().lower().startswith(
            (speaker.lower()+":", speaker.lower()+" -", speaker.lower()+"(")
        )
    ])

# ---------- STRUCTURED SLIDES ----------
def generate_structured_slides(full_text):
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": f"""
Create a structured recap.

Return JSON:
{{
  "slides": [
    {{
      "title": "Topic",
      "points": ["point1", "point2"],
      "narration": "short clear explanation with example if available"
    }}
  ]
}}

Rules:
- Maintain correct topic order
- Do NOT miss key topics
- Use short sentences
- Avoid words: speaker, lecture, session, today
- Narration must match slide

Text:
{full_text[:12000]}
"""
        }]
    )

    return json.loads(res.choices[0].message.content)["slides"]

# ---------- EDGE TTS (FEMALE NATURAL) ----------
async def generate_edge_audio(text, filename):
    communicate = edge_tts.Communicate(
        text=text,
        voice="en-US-AriaNeural",   # 🔥 female natural voice
        rate="+15%"                 # 🔥 slightly faster
    )
    await communicate.save(filename)

def generate_audio(slides):
    files = []

    for i, slide in enumerate(slides):
        fname = f"audio_{i}.mp3"
        text = slide["narration"]

        try:
            asyncio.run(generate_edge_audio(text, fname))
            files.append(fname)
        except:
            # fallback (rare)
            from gtts import gTTS
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

    w = draw.textbbox((0,0), lines[0], font=title_font)[2]
    draw.text(((1280-w)//2,80), lines[0], font=title_font, fill=(0,0,0))

    y = 180
    for l in lines[1:]:
        draw.text((100,y), l, font=body_font, fill=(0,0,0))
        y += 40

    return np.array(img)

# ---------- VIDEO ----------
def create_video(slides, audio_files):
    clips = []
    audios = []

    for i, slide in enumerate(slides):
        text = slide["title"] + "\n\n" + "\n".join([f"• {p}" for p in slide["points"]])

        img = create_slide(text)
        audio = AudioFileClip(audio_files[i])

        clip = ImageClip(img).set_duration(audio.duration)
        clip = clip.fadein(0.3).fadeout(0.3)

        clips.append(clip)
        audios.append(audio)

    video = concatenate_videoclips(clips, method="compose")
    audio = concatenate_audioclips(audios)

    video = video.set_audio(audio)

    # duration control (3–5 min)
    dur = audio.duration
    if dur < 180:
        video = video.fx(vfx.speedx, dur/180)
    elif dur > 300:
        video = video.fx(vfx.speedx, dur/300)

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
            full_text = ""

            for f in uploaded_files:
                text = f.read().decode("utf-8")
                text = remove_speaker(text, "Ravi")
                full_text += "\n\n" + text

            slides = generate_structured_slides(full_text)
            audio_files = generate_audio(slides)
            video = create_video(slides, audio_files)

            st.success("✅ Video Ready")
            st.video(video)

        except Exception as e:
            st.error(str(e))
