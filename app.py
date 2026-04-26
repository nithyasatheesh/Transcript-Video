import os
import json
import re
import streamlit as st
from gtts import gTTS
from moviepy.editor import *
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Init OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.set_page_config(page_title="Slide Video Generator")

st.title("🎬 AI Slide Video Generator")
st.write("Upload transcript → get slide-based recap video")

uploaded_file = st.file_uploader("Upload transcript (.txt)", type=["txt"])


# -------- SAFE JSON --------
def safe_json_load(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError("Invalid JSON from model")


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
Return ONLY valid JSON.

Format:
{{
  "slides": [
    {{
      "title": "Slide title",
      "points": ["point1", "point2"]
    }}
  ]
}}

Rules:
- 5–8 slides
- Max 5 bullet points
- Short text

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

    return script[:3000]


# -------- TEXT TO AUDIO --------
def text_to_audio(script):
    audio_file = "audio.mp3"

    tts = gTTS(script)
    tts.save(audio_file)

    if os.path.getsize(audio_file) < 1000:
        raise ValueError("Audio file corrupted")

    return audio_file


# -------- CREATE TEXT IMAGE (NO IMAGEMAGICK) --------
def create_text_image(text, size=(1280, 720)):
    img = Image.new("RGB", size, color=(30, 30, 30))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 60)
        body_font = ImageFont.truetype("DejaVuSans.ttf", 40)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    lines = text.split("\n")

    y = 100
    for i, line in enumerate(lines):
        font = title_font if i == 0 else body_font
        draw.text((60, y), line, font=font, fill=(255, 255, 255))
        y += 80

    return np.array(img)


# -------- CREATE VIDEO --------
def create_video(slides_json, audio_file):
    data = safe_json_load(slides_json)
    slides = data["slides"]

    audio = AudioFileClip(audio_file).set_fps(44100)
    duration = audio.duration
    slide_duration = duration / len(slides)

    clips = []

    for slide in slides:
        text = slide["title"] + "\n\n" + "\n".join([f"• {p}" for p in slide["points"]])

        img_array = create_text_image(text)

        slide_clip = ImageClip(img_array).set_duration(slide_duration)

        slide_clip = slide_clip.fadein(0.3).fadeout(0.3)

        clips.append(slide_clip)

    final_video = concatenate_videoclips(clips).set_audio(audio)

    output = "final_video.mp4"

    final_video.write_videofile(
        output,
        fps=24,
        codec="libx264",
        audio_codec="aac"
    )

    return output


# -------- MAIN --------
if uploaded_file:
    transcript = uploaded_file.read().decode("utf-8")

    if st.button("Generate Video"):
        try:
            with st.spinner("Processing... ⏳"):
                slides_json = generate_slides(transcript)

                script = slides_to_script(slides_json)
                st.write(f"Script length: {len(script)}")

                audio = text_to_audio(script)
                video = create_video(slides_json, audio)

            st.success("✅ Video Generated!")
            st.video(video)

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
