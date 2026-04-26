import os
import json
import re
import streamlit as st
from moviepy.editor import *
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Voice setup
USE_ELEVENLABS = os.getenv("ELEVEN_API_KEY") is not None
if USE_ELEVENLABS:
    from elevenlabs import generate, save, set_api_key
    set_api_key(os.getenv("ELEVEN_API_KEY"))
else:
    from gtts import gTTS

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

st.title("🎬 Transcript → Summary → Video Generator")

uploaded_file = st.file_uploader("Upload transcript (.txt)", type=["txt"])


# -------- SAFE JSON --------
def safe_json_load(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(match.group())


# -------- SUMMARY --------
def generate_summary(transcript):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {
                "role": "user",
                "content": f"""
Summarize this transcript clearly.

Include:
- Key points
- Important insights
- Keep it concise and structured

Transcript:
{transcript[:8000]}
"""
            }
        ]
    )
    return response.choices[0].message.content


# -------- SLIDES --------
def generate_slides(summary):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": f"""
Convert summary into presentation slides.

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
- Clear bullet points

Summary:
{summary}
"""
            }
        ]
    )
    return response.choices[0].message.content


# -------- SCRIPT --------
def slides_to_script(slides_json):
    data = safe_json_load(slides_json)
    slides = data["slides"]

    script = ""
    for slide in slides:
        script += slide["title"] + ". "
        script += " ".join(slide["points"]) + ". "

    return script[:3500]


# -------- SLOW SCRIPT --------
def slow_script(script):
    return script.replace(".", ". ... ")


# -------- AUDIO --------
def text_to_audio(script):
    script = slow_script(script)

    if USE_ELEVENLABS:
        audio = generate(
            text=script,
            voice="Rachel",
            model="eleven_multilingual_v2"
        )
        save(audio, "audio.mp3")
    else:
        tts = gTTS(script)
        tts.save("audio.mp3")

    return "audio.mp3"


# -------- SLIDE IMAGE --------
def create_text_image(text):
    img = Image.new("RGB", (1280, 720), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 🔥 Use local fonts
    title_font_path = os.path.join("fonts", "DejaVuSans-Bold.ttf")
    body_font_path = os.path.join("fonts", "DejaVuSans.ttf")

    try:
        title_font = ImageFont.truetype(title_font_path, 60)
        body_font = ImageFont.truetype(body_font_path, 45)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    lines = text.split("\n")

    draw.text((80, 80), lines[0], font=title_font, fill=(0, 0, 0))

    y = 260
    for line in lines[1:]:
        draw.text((100, y), line, font=body_font, fill=(0, 0, 0))
        y += 110

    return np.array(img)


# -------- VIDEO --------
def create_video(slides_json, audio_file):
    data = safe_json_load(slides_json)
    slides = data["slides"]

    audio = AudioFileClip(audio_file).set_fps(44100)

    target_duration = max(180, min(audio.duration, 300))
    slide_duration = target_duration / len(slides)

    clips = []

    for slide in slides:
        text = slide["title"] + "\n\n" + "\n".join([f"• {p}" for p in slide["points"]])

        img = create_text_image(text)
        clip = ImageClip(img).set_duration(slide_duration)

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

    if st.button("Generate Summary + Video"):
        try:
            with st.spinner("Generating summary..."):
                summary = generate_summary(transcript)

            st.subheader("📄 Summary")
            st.write(summary)

            with st.spinner("Generating video..."):
                slides_json = generate_slides(summary)

                script = slides_to_script(slides_json)
                audio = text_to_audio(script)
                video = create_video(slides_json, audio)

            st.success("✅ Done!")
            st.video(video)

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
