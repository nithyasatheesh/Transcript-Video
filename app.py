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

st.title("🎬 Faculty Recap Video Generator")

uploaded_file = st.file_uploader("Upload transcript (.txt)", type=["txt"])


# -------- SAFE JSON --------
def safe_json_load(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(match.group())


# -------- FACULTY STYLE SUMMARY --------
def generate_summary(transcript):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[
            {
                "role": "user",
                "content": f"""
You are a faculty explaining a recorded lecture.

Create a recap like a teacher explaining to students.

Style:
- Natural conversational tone
- Explain clearly
- Add simple examples if needed
- Smooth flow (not bullet points)

Transcript:
{transcript[:8000]}
"""
            }
        ]
    )
    return response.choices[0].message.content


# -------- SLIDES FROM SUMMARY --------
def generate_slides(summary):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": f"""
Convert this teaching explanation into slides.

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
- 6–8 slides
- MAX 3 bullet points per slide
- Very short text (for big font)

Summary:
{summary}
"""
            }
        ]
    )
    return response.choices[0].message.content


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

    base_dir = os.path.dirname(__file__)
    title_font_path = os.path.join(base_dir, "fonts", "DejaVuSans-Bold.ttf")
    body_font_path = os.path.join(base_dir, "fonts", "DejaVuSans.ttf")

    try:
        title_font = ImageFont.truetype(title_font_path, 140)
        body_font = ImageFont.truetype(body_font_path, 90)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    lines = text.split("\n")

    # Center title
    bbox = draw.textbbox((0, 0), lines[0], font=title_font)
    text_width = bbox[2] - bbox[0]
    draw.text(((1280 - text_width) // 2, 80), lines[0], font=title_font, fill=(0, 0, 0))

    y = 300
    for line in lines[1:]:
        draw.text((120, y), line, font=body_font, fill=(0, 0, 0))
        y += 140

    return np.array(img)


# -------- VIDEO (SYNCED) --------
def create_video(slides_json, audio_file, narration_text):
    data = safe_json_load(slides_json)
    slides = data["slides"]

    audio = AudioFileClip(audio_file).set_fps(44100)

    clips = []
    current_time = 0

    # Split narration into parts
    sentences = narration_text.split(". ")

    for i, slide in enumerate(slides):
        text = slide["title"] + "\n\n" + "\n".join([f"• {p}" for p in slide["points"]])

        # Assign narration chunk
        chunk = " ".join(sentences[i::len(slides)])

        word_count = len(chunk.split())
        duration = max(6, word_count / 2.2)

        img = create_text_image(text)

        clip = ImageClip(img).set_start(current_time).set_duration(duration)

        clips.append(clip)
        current_time += duration

    video = CompositeVideoClip(clips).set_audio(audio)

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

    if st.button("Generate Recap Video"):
        try:
            with st.spinner("Generating explanation..."):
                summary = generate_summary(transcript)

            st.subheader("📄 Faculty Explanation")
            st.write(summary)

            with st.spinner("Creating video..."):
                slides_json = generate_slides(summary)

                audio = text_to_audio(summary)   # 🔥 use natural narration

                video = create_video(slides_json, audio, summary)

            st.success("✅ Video Ready!")
            st.video(video)

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
