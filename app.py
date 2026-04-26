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

st.title("🎬 Session Recap Video Generator (Synced)")

uploaded_file = st.file_uploader("Upload transcript (.txt)", type=["txt"])


# -------- SAFE JSON --------
def safe_json_load(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(match.group())


# -------- RECAP SUMMARY --------
def generate_summary(transcript):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[
            {
                "role": "user",
                "content": f"""
Create a recap in past tense.

Style:
- "In this session, we covered..."
- "We discussed..."
- "Then we explored..."
- "Finally..."

Natural, smooth narration.

Transcript:
{transcript[:8000]}
"""
            }
        ]
    )
    return response.choices[0].message.content


# -------- SPLIT INTO SEGMENTS --------
def split_into_segments(summary, num_slides=6):
    sentences = summary.split(". ")
    chunk_size = max(1, len(sentences) // num_slides)

    segments = []
    for i in range(0, len(sentences), chunk_size):
        segment = ". ".join(sentences[i:i+chunk_size])
        segments.append(segment)

    return segments[:num_slides]


# -------- GENERATE SLIDES --------
def generate_slides(segments):
    slides = []

    for seg in segments:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": f"""
Create ONE slide.

Return JSON:
{{
  "title": "Short title",
  "points": ["short point", "short point"]
}}

Max 3 bullet points.
Keep text very short.

Text:
{seg}
"""
                }
            ]
        )

        slide = safe_json_load(response.choices[0].message.content)
        slides.append(slide)

    return slides


# -------- AUDIO PER SEGMENT --------
def generate_audio_segments(segments):
    audio_files = []

    for i, seg in enumerate(segments):
        filename = f"audio_{i}.mp3"

        if USE_ELEVENLABS:
            audio = generate(
                text=seg,
                voice="Rachel",
                model="eleven_multilingual_v2"
            )
            save(audio, filename)
        else:
            tts = gTTS(seg)
            tts.save(filename)

        audio_files.append(filename)

    return audio_files


# -------- CREATE TEXT IMAGE --------
def create_text_image(text):
    img = Image.new("RGB", (1280, 720), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    base_dir = os.path.dirname(__file__)
    title_font_path = os.path.join(base_dir, "fonts", "DejaVuSans-Bold.ttf")
    body_font_path = os.path.join(base_dir, "fonts", "DejaVuSans.ttf")

    try:
        title_font = ImageFont.truetype(title_font_path, 60)
        body_font = ImageFont.truetype(body_font_path, 20)
    except:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    lines = text.split("\n")

    # Center title
    bbox = draw.textbbox((0, 0), lines[0], font=title_font)
    text_width = bbox[2] - bbox[0]
    draw.text(((1280 - text_width) // 2, 80), lines[0], font=title_font, fill=(0, 0, 0))

    # Bullets
    y = 300
    for line in lines[1:]:
        draw.text((120, y), line, font=body_font, fill=(0, 0, 0))
        y += 140

    return np.array(img)


# -------- CREATE VIDEO --------
def create_video(slides, audio_files):
    clips = []
    audio_clips = []
    current_time = 0

    for i, slide in enumerate(slides):
        text = slide["title"] + "\n\n" + "\n".join([f"• {p}" for p in slide["points"]])

        img = create_text_image(text)

        audio = AudioFileClip(audio_files[i])
        duration = audio.duration

        clip = ImageClip(img).set_start(current_time).set_duration(duration)

        clips.append(clip)
        audio_clips.append(audio)

        current_time += duration

    final_audio = concatenate_audioclips(audio_clips)

    video = CompositeVideoClip(clips).set_audio(final_audio)

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
            with st.spinner("Generating recap..."):
                summary = generate_summary(transcript)

            st.subheader("📄 Recap")
            st.write(summary)

            with st.spinner("Creating synced video..."):
                segments = split_into_segments(summary)
                slides = generate_slides(segments)
                audio_files = generate_audio_segments(segments)

                video = create_video(slides, audio_files)

            st.success("✅ Video Ready!")
            st.video(video)

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
