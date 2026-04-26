import os
import json
import re
import streamlit as st
from gtts import gTTS
from moviepy.editor import *
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import numpy as np

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.title("🎬 Slide Video Generator (White Theme)")

uploaded_file = st.file_uploader("Upload transcript", type=["txt"])


# -------- SAFE JSON --------
def safe_json_load(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(match.group())


# -------- GENERATE SLIDES --------
def generate_slides(transcript):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": f"""
Convert transcript into slides for a 3–5 minute video.

Return JSON:
{{
  "slides": [
    {{
      "title": "Title",
      "points": ["point1", "point2"]
    }}
  ]
}}

Rules:
- 6–10 slides
- Short bullet points
- Clean structure

Transcript:
{transcript[:6000]}
"""
            }
        ]
    )

    return response.choices[0].message.content


# -------- SLIDES → SCRIPT --------
def slides_to_script(slides_json):
    data = safe_json_load(slides_json)
    slides = data["slides"]

    script = ""
    for slide in slides:
        script += slide["title"] + ". "
        script += " ".join(slide["points"]) + ". "

    return script[:3500]


# -------- AUDIO --------
def text_to_audio(script):
    tts = gTTS(script)
    tts.save("audio.mp3")
    return "audio.mp3"


# -------- CREATE SLIDE IMAGE --------
def create_text_image(text, size=(1280, 720)):
    img = Image.new("RGB", size, color=(255, 255, 255))  # WHITE BG
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 80)  # BIGGER
        body_font = ImageFont.truetype("DejaVuSans.ttf", 50)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    lines = text.split("\n")

    y = 120
    for i, line in enumerate(lines):
        font = title_font if i == 0 else body_font
        draw.text((80, y), line, font=font, fill=(0, 0, 0))  # BLACK TEXT
        y += 90

    return np.array(img)


# -------- VIDEO --------
def create_video(slides_json, audio_file):
    data = safe_json_load(slides_json)
    slides = data["slides"]

    audio = AudioFileClip(audio_file).set_fps(44100)

    # 🔥 Force 3–5 min duration
    target_duration = max(180, min(audio.duration, 300))

    slide_duration = target_duration / len(slides)

    clips = []

    for slide in slides:
        text = slide["title"] + "\n\n" + "\n".join([f"• {p}" for p in slide["points"]])

        img = create_text_image(text)

        clip = ImageClip(img).set_duration(slide_duration)
        clip = clip.fadein(0.5).fadeout(0.5)

        clips.append(clip)

    video = concatenate_videoclips(clips).set_audio(audio)

    video.write_videofile(
        "final_video.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac"
    )

    return "final_video.mp4"


# -------- MAIN --------
if uploaded_file:
    transcript = uploaded_file.read().decode("utf-8")

    if st.button("Generate Video"):
        with st.spinner("Creating video..."):
            slides_json = generate_slides(transcript)
            script = slides_to_script(slides_json)
            audio = text_to_audio(script)
            video = create_video(slides_json, audio)

        st.success("✅ Done!")
        st.video(video)
